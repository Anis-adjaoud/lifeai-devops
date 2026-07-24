"""
LifeAI — API FastAPI.
Expose les endpoints pour le frontend web (dashboard + chat).

Démarrage :
    uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
import os
import secrets
import uuid

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
from urllib.parse import urlparse

from agentic.agents_adk import database as db
from agentic.agents_adk.tools import _enrich_user_data
from agentic.agents_adk.pipeline import (
    _run_async,
    create_chat_session,
    send_chat_message,
    delete_chat_session,
    get_adk_session_for_conv,
    get_chat_session_owner,
)
from agentic.google_fit import fetch_fitness_data

# Modules nutrition (CIQUAL, journal, extraction chat)
from nutrition import import_foods, nutrition_store, nutrition_mapping, food_extraction


@asynccontextmanager
async def lifespan(app):
    nutrition_store.init_diary_tables()
    try:
        import_foods.seed_foods_if_empty()
    except Exception as e:
        # CIQUAL absent/corrompu : dégrade la nutrition sans bloquer le démarrage
        print(f"[lifespan] ATTENTION : import CIQUAL échoué, fonctionnalités nutrition "
              f"dégradées — {e}", flush=True)

    scheduler = None
    if os.environ.get("ENABLE_LOCAL_SCHEDULER", "true").lower() == "true":
        from agentic.scheduler import start_scheduler
        scheduler = start_scheduler()

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="LifeAI API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Secret aléatoire par process si SESSION_SECRET non configuré
_session_secret = os.environ.get("SESSION_SECRET")
if not _session_secret:
    print("[api] ATTENTION : SESSION_SECRET non configuré — secret aléatoire généré pour ce process "
          "(les sessions ne survivront pas à un redémarrage).", flush=True)
    _session_secret = secrets.token_hex(32)

app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    same_site="lax",
    https_only=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
    max_age=60 * 60 * 24 * 30,  # 30 jours
)


# ── URL canonique unique ──────────────────────────────────────────────────────
# URL canonique unique : redirige vers l'origine OAuth (cookie/login cohérents
# malgré les 2 URLs Cloud Run). Source de vérité : OAUTH_REDIRECT_URI.
_oauth_parsed     = urlparse(os.environ.get("OAUTH_REDIRECT_URI", ""))
_CANONICAL_HOST   = _oauth_parsed.netloc
_CANONICAL_SCHEME = _oauth_parsed.scheme or "https"


@app.middleware("http")
async def _canonical_host_redirect(request: Request, call_next):
    host = request.headers.get("host", "")
    # Redirige les navigations HTML vers l'URL canonique (pas /api ni health checks)
    if (
        _CANONICAL_HOST
        and "localhost" not in _CANONICAL_HOST
        and host
        and host != _CANONICAL_HOST
        and request.method == "GET"
        and "text/html" in request.headers.get("accept", "")
    ):
        target = request.url.replace(scheme=_CANONICAL_SCHEME, netloc=_CANONICAL_HOST)
        return RedirectResponse(str(target), status_code=307)
    return await call_next(request)


# ── Autorisation ──────────────────────────────────────────────────────────────
# Modèle d'accès :
#  - PUBLIC_DEMO_USERS : consultables sans connexion
#  - utilisateur connecté : son compte ; ADMIN_EMAILS : tous les comptes

ADMIN_EMAILS = {
    e.strip() for e in os.environ.get("ADMIN_EMAILS", "adjaoudanis2021@gmail.com").split(",") if e.strip()
}
PUBLIC_DEMO_USERS = {"lucas.martin@lifeai.demo", "emma.rousseau@lifeai.demo"}


def _session_user(request: Request) -> str | None:
    return request.session.get("user_id")


def require_self_or_admin(user_id: str, request: Request) -> str | None:
    """Autorise l'accès à `user_id` : profil démo public, propre compte, ou admin."""
    if user_id in PUBLIC_DEMO_USERS:
        return _session_user(request)
    session_uid = _session_user(request)
    if not session_uid:
        raise HTTPException(status_code=401, detail="Non authentifié — connectez-vous via Google Fit.")
    if session_uid != user_id and session_uid not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Accès refusé à ce compte.")
    return session_uid


def require_self_or_admin_strict(user_id: str, request: Request) -> str:
    """Comme require_self_or_admin mais sans le bypass démo public : exige toujours
    une session réelle (écritures et actions coûteuses : analyse, chat, journal, profil)."""
    session_uid = _session_user(request)
    if not session_uid:
        raise HTTPException(status_code=401, detail="Non authentifié — connectez-vous via Google Fit.")
    if session_uid != user_id and session_uid not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Accès refusé à ce compte.")
    return session_uid


def require_conversation_access(conv_id: str, request: Request) -> None:
    owner = db.get_conversation_owner(conv_id)
    if owner is not None:
        require_self_or_admin(owner, request)


def require_log_access(entry_id: int, request: Request) -> None:
    owner = nutrition_store.get_log_owner(entry_id)
    if owner is not None:
        require_self_or_admin(owner, request)


def require_log_access_strict(entry_id: int, request: Request) -> None:
    """Variante stricte de require_log_access (suppression) : 404 si l'entrée n'existe pas."""
    owner = nutrition_store.get_log_owner(entry_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Entrée introuvable.")
    require_self_or_admin_strict(owner, request)


def require_chat_session_access(session_id: str, request: Request) -> None:
    owner = get_chat_session_owner(session_id)
    if owner is not None:
        require_self_or_admin(owner, request)


# ── OAuth Google Fit ──────────────────────────────────────────────────────────

_pending_auth: dict[str, str] = {}   # state -> code_verifier

def _html_ok(user_id: str) -> str:
    import json
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>LifeAI</title></head>
<body style="margin:0;background:#07071a;display:flex;align-items:center;justify-content:center;height:100vh;font-family:-apple-system,sans-serif;color:#f1f5f9">
  <div style="text-align:center">
    <div style="font-size:64px;margin-bottom:20px">✅</div>
    <h2 style="margin:0 0 10px;color:#10b981;font-size:22px">Connexion réussie !</h2>
    <p style="color:#94a3b8;margin:0">Fermeture automatique…</p>
  </div>
  <script>
    setTimeout(function() {{
      try {{ window.opener.postMessage({{type:'lifeai_auth_success', userId:{json.dumps(user_id)}}}, '*'); }} catch(e){{}}
      window.close();
    }}, 1200);
  </script>
</body></html>"""

_HTML_ERR = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>LifeAI</title></head>
<body style="margin:0;background:#07071a;display:flex;align-items:center;justify-content:center;height:100vh;font-family:-apple-system,sans-serif;color:#f1f5f9">
  <div style="text-align:center">
    <div style="font-size:64px;margin-bottom:20px">❌</div>
    <h2 style="margin:0 0 10px;color:#ef4444;font-size:22px">Erreur d'autorisation</h2>
    <p style="color:#94a3b8;margin:0">Veuillez réessayer.</p>
  </div>
  <script>setTimeout(function(){ window.close(); }, 2500);</script>
</body></html>"""


@app.get("/auth/start")
def auth_start():
    """Lance le flow OAuth Google Fit dans une fenêtre popup."""
    from agentic.google_fit import get_auth_url
    state = uuid.uuid4().hex
    auth_url, code_verifier = get_auth_url(state=state)
    _pending_auth[state] = code_verifier
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
def auth_callback(request: Request, background_tasks: BackgroundTasks, code: str | None = None, state: str | None = None):
    """Callback OAuth Google Fit — reçoit la redirection du navigateur après consentement."""
    html = _HTML_ERR
    if code and state in _pending_auth:
        code_verifier = _pending_auth.pop(state)
        try:
            from agentic.google_fit import exchange_code, get_user_info
            tokens = exchange_code(code, code_verifier)
            info = get_user_info(tokens["access_token"], tokens.get("refresh_token"))
            uid  = info.get("email")
            if not uid:
                # Pas d'email : échec propre plutôt que de fusionner les comptes sous "user"
                raise ValueError("Réponse Google userinfo sans email exploitable")
            name = info.get("name") or uid
            db.ensure_user(uid, name)
            db.save_oauth_token(
                uid, "google_fit",
                tokens["access_token"],
                tokens.get("refresh_token"),
                tokens.get("token_expiry"),
            )
            request.session["user_id"] = uid
            html = _html_ok(uid)
            print(f"[oauth] Nouvel utilisateur connecté : {uid} ({name})")

            # Récupère les métriques Google Fit et lance l'analyse en tâche de fond
            try:
                user_data = _fetch_and_save_fit_metrics(uid, tokens)
                nutrition_source = _nutrition_source_for(uid, user_data)
                background_tasks.add_task(_run_full_analysis, uid, user_data, nutrition_source)
                print(f"[oauth] Analyse complète lancée en arrière-plan pour {uid}")
            except Exception as exc:
                print(f"[oauth] Avertissement : échec récupération métriques initiales — {exc}")
        except Exception as exc:
            print(f"[oauth] Erreur : {exc}")

    return HTMLResponse(content=html)


@app.get("/api/me")
def get_me(request: Request):
    """Identité de la session courante — utilisé par le frontend pour savoir qui est connecté."""
    session_uid = _session_user(request)
    if not session_uid:
        return {"user_id": None, "name": None, "is_admin": False}
    users = db.get_all_users()
    name = next((u["name"] for u in users if u["user_id"] == session_uid), session_uid)
    return {"user_id": session_uid, "name": name, "is_admin": session_uid in ADMIN_EMAILS}


@app.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


# ── Sync quotidienne (déclenchée par Cloud Scheduler en prod) ─────────────────

@app.post("/internal/sync-all")
async def sync_all(x_scheduler_key: str | None = Header(default=None)):
    """Lance l'analyse Google Fit de tous les utilisateurs. Appelé par Cloud Scheduler."""
    expected = os.environ.get("SCHEDULER_SECRET")
    if not expected or x_scheduler_key != expected:
        raise HTTPException(status_code=401, detail="Clé de scheduler invalide")

    from agentic.scheduler import run_all_users
    await asyncio.to_thread(run_all_users)
    return {"status": "ok"}


# ── Utilisateurs ──────────────────────────────────────────────────────────────

@app.get("/api/users")
def list_users(request: Request):
    """Liste accessible selon la session :
    - admin : tous les comptes, le sien en premier (sélectionné par défaut).
    - connecté (non-admin) : son compte + les profils démo, son compte en premier.
    - anonyme : profils démo uniquement."""
    session_uid = _session_user(request)
    all_users = db.get_all_users()
    if session_uid in ADMIN_EMAILS:
        own = [u for u in all_users if u["user_id"] == session_uid]
        others = [u for u in all_users if u["user_id"] != session_uid]
        return own + others
    if session_uid:
        own  = [u for u in all_users if u["user_id"] == session_uid]
        demo = [u for u in all_users if u["user_id"] in PUBLIC_DEMO_USERS]
        return own + demo
    return [u for u in all_users if u["user_id"] in PUBLIC_DEMO_USERS]


@app.get("/api/profile/{user_id}")
def get_profile(user_id: str, _: str | None = Depends(require_self_or_admin)):
    profile = db.get_profile(user_id)
    return profile or {}


@app.put("/api/profile/{user_id}")
def update_profile(user_id: str, data: dict, _: str | None = Depends(require_self_or_admin_strict)):
    db.update_profile(user_id, **data)
    return {"status": "ok"}


# ── Sessions / historique ─────────────────────────────────────────────────────

@app.get("/api/sessions/{user_id}")
def get_sessions(user_id: str, days: int = 30, _: str | None = Depends(require_self_or_admin)):
    return db.get_sessions(user_id, days=days)


@app.get("/api/patterns/{user_id}")
def get_patterns(user_id: str, _: str | None = Depends(require_self_or_admin)):
    return db.get_patterns(user_id, min_occurrences=1)


@app.get("/api/metrics/{user_id}")
def get_health_metrics(user_id: str, days: int = 30, _: str | None = Depends(require_self_or_admin)):
    return db.get_health_metrics(user_id, days=days)


@app.get("/api/notes/{user_id}")
def get_notes_endpoint(user_id: str, _: str | None = Depends(require_self_or_admin)):
    return db.get_notes(user_id)


@app.get("/api/trend/{user_id}")
def get_trend(user_id: str, days: int = 7, _: str | None = Depends(require_self_or_admin)):
    sessions = db.get_sessions(user_id, days=60)
    trend_str = db.get_score_trend(user_id, window=days)
    delta = None
    if len(sessions) >= 2:
        delta = round(sessions[0]["global_score"] - sessions[1]["global_score"], 1)
    return {
        "trend": trend_str or "Pas assez de données",
        "delta": delta,
        "sessions_count": len(sessions),
        "last_date": sessions[0]["date"] if sessions else None,
    }


# ── Analyse (pipeline complet) ────────────────────────────────────────────────


def _fetch_and_save_fit_metrics(user_id: str, tokens: dict) -> dict:
    """Récupère les données Google Fit et sauvegarde les métriques brutes en base.
    Utilisé à la fois par /api/analyze et /auth/callback (dès la connexion)."""
    user_data = fetch_fitness_data(tokens["access_token"], tokens["refresh_token"])
    act   = user_data.get("activity", {})
    sleep = user_data.get("sleep", {})
    db.add_health_metrics(
        user_id        = user_id,
        steps_today    = act.get("steps_today", 0),
        steps_7d       = act.get("steps_7d", []),
        active_minutes = act.get("active_minutes", 0),
        sleep_hours    = sleep.get("duration_hours", 0),
        sleep_7d       = sleep.get("sleep_7d", []),
        calories       = act.get("calories_burned", 0),
        heart_rate     = user_data.get("_resting_hr"),
        weight_kg      = user_data.get("_weight_kg"),
    )
    return user_data


def _user_data_from_metrics(user_id: str) -> dict | None:
    """Reconstruit un user_data depuis les health_metrics stockées (profils demo ou hors-ligne).
    La nutrition, la qualité du sommeil et la FC repos sont enrichies par analyze_health_data
    via _enrich_user_data (tools.py) à l'exécution.
    """
    metrics = db.get_health_metrics(user_id, days=7)
    if not metrics:
        return None
    m = metrics[0]  # entrée la plus récente
    steps_7d      = m.get("steps_7d") or []
    sleep_7d      = m.get("sleep_7d")  or []
    steps_today   = m.get("steps_today", 0)
    sleep_tonight = m.get("sleep_hours", 7.0)
    active_min    = m.get("active_minutes", 0)
    calories      = m.get("calories", 0)
    hr            = float(m.get("heart_rate") or 65.0)
    weight        = m.get("weight_kg")
    return {
        "activity": {
            "steps_today":        steps_today,
            "steps_7d":           steps_7d or [steps_today],
            "active_minutes":     active_min,
            "workouts_this_week": sum(1 for s in (steps_7d or []) if s >= 7000),
            "sedentary_hours":    max(0.0, round(16 - active_min / 60, 1)),
            "calories_burned":    calories,
        },
        "sleep": {
            "duration_hours": sleep_tonight,
            "sleep_7d":       sleep_7d or [sleep_tonight],
            # Pas de champs de qualité → analyze_health_data les estimera depuis la durée
        },
        # Pas de nutrition ni risk → analyze_health_data les lira depuis le profil et _resting_hr
        "_resting_hr": hr,
        "_weight_kg":  weight,
    }


def _nutrition_source_for(user_id: str, user_data: dict) -> str:
    """Fusionne la nutrition du journal du jour dans user_data (mutation en place).
    Google Fit ne fournit pas la nutrition → on remplace le stub à zéro UNIQUEMENT
    si le user a des aliments au journal AUJOURD'HUI. Sinon on laisse les valeurs
    Google Fit (zéros) : pas de report de la veille — un jour non rempli = nutrition
    vide, volontairement."""
    diary = nutrition_store.get_diary(user_id)
    if diary["totals"]["entries"] > 0:
        water_ml = nutrition_store.get_water(user_id)
        goal     = nutrition_store.get_goal(user_id)
        user_data["nutrition"] = nutrition_mapping.diary_to_contract(diary, water_ml, goal)
        return "today"
    return "none"


async def _run_full_analysis(user_id: str, user_data: dict, nutrition_source: str) -> dict:
    """Pipeline complet : scores Python + chief_agent ADK (synthesis, WhatsApp si critique).

    Le pipeline ADK (étape 2, via analyze_health_data) sauvegarde lui-même sa
    propre session en base. Les scores Python de l'étape 1 ne sont donc
    sauvegardés que comme FILET DE SÉCURITÉ si l'étape 2 échoue à en produire
    une — sinon chaque analyse créait 2 lignes de session en base (bug corrigé),
    ce qui faussait silencieusement /api/trend (delta jour-sur-jour calculé
    entre deux lignes de la même exécution)."""
    sessions_before = len(db.get_sessions(user_id, days=1))

    # ── 1. Scores calculés en Python (indépendants du LLM) — toujours calculés
    #      (nécessaires pour save_nutrition_analysis dans tous les cas), mais
    #      sauvegardés en session seulement si l'étape 2 n'en sauvegarde aucune. ──
    g_score = a_score = s_score = n_score = r_score = h_level = None
    try:
        from agentic.agents.activity_agent  import ActivityAgent
        from agentic.agents.sleep_agent     import SleepAgent
        from agentic.agents.nutrition_agent import NutritionAgent
        from agentic.agents.risk_agent      import RiskAgent
        from agentic.agents_adk.tools import set_current_user as _set_uid
        _set_uid(user_id)  # nécessaire pour que _enrich_user_data lise le bon profil

        enriched = _enrich_user_data(user_data)
        a_score = float(ActivityAgent().analyze({"activity":   enriched.get("activity",  {})}).score)
        s_score = float(SleepAgent().analyze({"sleep":         enriched.get("sleep",     {})}).score)
        nut_report = NutritionAgent().analyze({"nutrition": enriched.get("nutrition", {})})
        n_score = nut_report.score  # None si pas de journal du jour ni profil renseigné
        n_score = float(n_score) if n_score is not None else None
        r_score = float(RiskAgent().analyze({**enriched, "_nutrition_score": n_score}).score)
        if n_score is None:
            # Pas de nutrition fiable : poids redistribué au prorata
            g_score = round(a_score * (0.25 / 0.80) + s_score * (0.30 / 0.80) + r_score * (0.25 / 0.80), 1)
        else:
            g_score = round(a_score * 0.25 + s_score * 0.30 + n_score * 0.20 + r_score * 0.25, 1)
        h_level = ("Excellent" if g_score >= 80 else "Bon" if g_score >= 65
                   else "Attention" if g_score >= 45 else "Critique")

        # Persiste l'analyse nutrition seulement si données déclarées aujourd'hui
        if nutrition_source == "today":
            nutrition_store.save_nutrition_analysis(
                user_id, nut_report.score, nut_report.insights,
                nut_report.recommendations, nut_report.anomalies,
            )
        print(f"[analyze] Scores Python calculés : {g_score}/100 ({h_level})", flush=True)
    except Exception as e:
        print(f"[analyze] Avertissement calcul scores : {e}", flush=True)

    # ── 2. ADK chief_agent — scores + narrative (synthesis, conseils, plan),
    #      sauvegarde sa propre session via analyze_health_data/save_session. ──
    try:
        await _run_async(user_data, user_id)
    except Exception as e:
        print(f"[analyze] Avertissement ADK : {e}", flush=True)

    # Filet de sécurité : sauvegarde les scores Python si l'ADK n'a rien sauvé
    if g_score is not None and len(db.get_sessions(user_id, days=1)) == sessions_before:
        db.add_session(user_id, g_score, a_score, s_score, n_score, r_score, health_level=h_level)
        print(f"[analyze] Filet de sécurité déclenché (ADK n'a sauvegardé aucune session) : {g_score}/100", flush=True)

    sessions = db.get_sessions(user_id, days=1)
    if sessions:
        print(f"[analyze] Session retournée : score={sessions[0].get('global_score')}, synthesis={bool(sessions[0].get('synthesis'))}", flush=True)
    result = sessions[0] if sessions else {"status": "analyse terminee"}
    result["nutrition_source"] = nutrition_source

    usage_metrics = db.get_usage_metrics(user_id=user_id, kind="analyze", days=1)
    if usage_metrics:
        result["usage"] = usage_metrics[0]

    return result


@app.post("/api/analyze/{user_id}")
async def analyze(user_id: str, _: str | None = Depends(require_self_or_admin_strict)):
    """Lance le pipeline complet : Google Fit -> chief_agent -> save_session -> WhatsApp."""
    tokens = db.get_oauth_token(user_id, "google_fit")

    if not tokens:
        # Pas de token Google Fit → fallback sur les métriques stockées (profils demo)
        user_data = _user_data_from_metrics(user_id)
        if not user_data:
            raise HTTPException(
                status_code=400,
                detail="Aucun token Google Fit pour cet utilisateur et aucune métrique stockée disponible.",
            )
    else:
        try:
            user_data = _fetch_and_save_fit_metrics(user_id, tokens)
        except Exception as e:
            if "invalid_grant" in str(e).lower():
                db.delete_oauth_token(user_id, "google_fit")
                raise HTTPException(
                    status_code=401,
                    detail="Session Google Fit expirée — reconnectez-vous via la page d'accueil pour re-autoriser l'accès.",
                )
            raise HTTPException(status_code=502, detail=f"Erreur Google Fit : {e}")

    nutrition_source = _nutrition_source_for(user_id, user_data)
    print(f"[analyze] Source nutrition : {nutrition_source}", flush=True)

    return await _run_full_analysis(user_id, user_data, nutrition_source)


# ── Nutrition (journal alimentaire façon YAZIO) ───────────────────────────────


class FoodLogInput(BaseModel):
    """Ajout d'un aliment à un repas du journal."""
    meal:       str      # 'breakfast' | 'lunch' | 'dinner' | 'snack'
    food_code:  str
    quantity_g: float = Field(gt=0, le=5000)  # borne haute généreuse (5 kg) pour éviter les valeurs aberrantes


class WaterInput(BaseModel):
    ml: int = Field(ge=0, le=10000)  # 10 L/jour, largement au-dessus de tout besoin réel


class GoalInput(BaseModel):
    kcal_goal: int = Field(ge=800, le=6000)


def _diary_payload(user_id: str) -> dict:
    """Journal du jour enrichi (objectif, eau, calories sport Google Fit)."""
    diary = nutrition_store.get_diary(user_id)
    metrics = db.get_health_metrics(user_id, days=1)
    exercise_kcal = int(metrics[0]["calories"]) if metrics and metrics[0].get("calories") else 0
    return {
        **diary,
        "goal":          nutrition_store.get_goal(user_id),
        "water_ml":      nutrition_store.get_water(user_id),
        "exercise_kcal": exercise_kcal,
        "analysis":      nutrition_store.get_nutrition_analysis(user_id),
    }


@app.get("/api/foods/search")
def search_foods(q: str = ""):
    """Recherche d'aliments dans le catalogue CIQUAL local."""
    return nutrition_store.search_foods(q)


@app.get("/api/nutrition/{user_id}/diary")
def get_diary(user_id: str, _: str | None = Depends(require_self_or_admin)):
    """Journal alimentaire du jour : repas, totaux, objectif, eau, calories sport."""
    return _diary_payload(user_id)


@app.post("/api/nutrition/{user_id}/log")
def add_food_log(user_id: str, data: FoodLogInput, _: str | None = Depends(require_self_or_admin_strict)):
    """Ajoute un aliment à un repas ; renvoie le journal à jour."""
    if data.meal not in nutrition_store.MEALS:
        raise HTTPException(status_code=422, detail=f"Repas invalide : {data.meal}")
    entry_id = nutrition_store.add_log(user_id, data.meal, data.food_code, data.quantity_g)
    if entry_id is None:
        raise HTTPException(status_code=404, detail="Aliment introuvable")
    return _diary_payload(user_id)


@app.delete("/api/nutrition/log/{entry_id}")
def delete_food_log(entry_id: int, _: None = Depends(require_log_access_strict)):
    """Supprime une entrée du journal."""
    nutrition_store.delete_log(entry_id)
    return {"status": "ok"}


@app.post("/api/nutrition/{user_id}/water")
def set_water(user_id: str, data: WaterInput, _: str | None = Depends(require_self_or_admin_strict)):
    """Fixe l'hydratation du jour (en ml)."""
    nutrition_store.set_water(user_id, data.ml)
    return {"status": "ok", "water_ml": nutrition_store.get_water(user_id)}


@app.put("/api/nutrition/{user_id}/goal")
def set_goal(user_id: str, data: GoalInput, _: str | None = Depends(require_self_or_admin_strict)):
    """Fixe l'objectif calorique quotidien."""
    nutrition_store.set_goal(user_id, data.kcal_goal)
    return {"status": "ok", "goal": nutrition_store.get_goal(user_id)}


# ── Conversations ─────────────────────────────────────────────────────────────

@app.get("/api/conversations/{user_id}")
def list_conversations(user_id: str, _: str | None = Depends(require_self_or_admin)):
    """Liste toutes les conversations d'un utilisateur (ordre antichronologique)."""
    return db.get_conversations(user_id)


@app.get("/api/conversations/{conv_id}/messages")
def get_messages(conv_id: str, _: None = Depends(require_conversation_access)):
    """Retourne les messages d'une conversation."""
    return db.get_conv_messages(conv_id)


@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str, _: None = Depends(require_conversation_access)):
    """Supprime une conversation et ses messages."""
    db.delete_conversation(conv_id)
    return {"status": "ok"}


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


@app.post("/api/chat/{user_id}")
async def chat(user_id: str, body: ChatRequest, request: Request, _: str | None = Depends(require_self_or_admin_strict)):
    """
    Envoie un message au chief_agent.
    - Si conversation_id absent → nouvelle conversation.
    - Si conversation_id présent et session ADK vivante → reprise directe.
    - Si conversation_id présent mais session expirée → rechargement historique + nouvelle session ADK.
    """
    conv_id    = body.conversation_id
    session_id = None

    if conv_id:
        owner = db.get_conversation_owner(conv_id)
        if owner is not None and owner != user_id:
            require_self_or_admin(owner, request)
        # Tente de retrouver la session ADK en mémoire
        session_id = get_adk_session_for_conv(conv_id)
        if not session_id:
            # Session expirée (redémarrage serveur) : recharge l'historique depuis la DB
            history = db.get_conv_messages(conv_id)
            session_id = await create_chat_session(user_id, conv_id=conv_id, history=history)
    else:
        # Nouvelle conversation — la DB génère l'UUID
        title   = body.message[:60].strip()
        conv_id = db.create_conversation(user_id, title)
        session_id = await create_chat_session(user_id, conv_id=conv_id)

    # Sauvegarde le message utilisateur
    db.add_conv_message(conv_id, "user", body.message)

    # Réponse de l'agent + détection d'aliments consommés en parallèle
    try:
        (response, usage), logged_foods = await asyncio.gather(
            send_chat_message(session_id, body.message),
            asyncio.to_thread(food_extraction.extract_and_log, user_id, body.message),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Sauvegarde la réponse de l'assistant
    db.add_conv_message(conv_id, "assistant", response)
    db.update_conversation(conv_id)  # met à jour updated_at

    return {
        "response": response,
        "session_id": session_id,
        "conversation_id": conv_id,
        "logged_foods": logged_foods,
        "usage": usage,
    }


@app.delete("/api/chat/session/{session_id}")
def reset_chat(session_id: str, _: None = Depends(require_chat_session_access)):
    """Supprime une session de chat ADK."""
    delete_chat_session(session_id)
    return {"status": "ok"}


# ── Serve frontend statique (prod) ────────────────────────────────────────────

dist = Path(__file__).parent / "frontend_web" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")
