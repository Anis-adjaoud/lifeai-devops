"""
LifeAI — Google Fit integration.
OAuth2 flow + récupération automatique des données de santé.

Données récupérées :
  - Pas quotidiens (7 derniers jours)
  - Minutes actives
  - Calories brûlées
  - Fréquence cardiaque (pour le score risque)
  - Sommeil (durée par nuit sur 7j)
  - Poids (pour le profil)
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/fitness.activity.read",
    "https://www.googleapis.com/auth/fitness.sleep.read",
    "https://www.googleapis.com/auth/fitness.body.read",
    "https://www.googleapis.com/auth/fitness.heart_rate.read",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]

_DEFAULT_SECRETS_FILE = Path(__file__).parent.parent / "google_client_secrets.json"
SECRETS_FILE = Path(os.environ.get("GOOGLE_OAUTH_CLIENT_SECRETS_FILE", _DEFAULT_SECRETS_FILE))
REDIRECT_URI  = os.environ.get("OAUTH_REDIRECT_URI", "http://localhost:8000/auth/callback")


# ── OAuth2 ────────────────────────────────────────────────────────────────────

def get_auth_url(state: str = "lifeai") -> tuple[str, str]:
    """
    Retourne (auth_url, code_verifier).
    Passer code_verifier à exchange_code() pour compléter le flow PKCE.
    """
    import secrets as _secrets
    import hashlib
    import base64
    from google_auth_oauthlib.flow import Flow

    code_verifier = _secrets.token_urlsafe(96)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    flow = Flow.from_client_secrets_file(SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
        code_challenge=code_challenge,
        code_challenge_method="S256",
    )
    return auth_url, code_verifier


def exchange_code(code: str, code_verifier: str = None) -> dict:
    """Échange le code d'autorisation contre les tokens (access + refresh)."""
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    fetch_kwargs = {"code": code}
    if code_verifier:
        fetch_kwargs["code_verifier"] = code_verifier
    flow.fetch_token(**fetch_kwargs)
    creds = flow.credentials
    return {
        "access_token":  creds.token,
        "refresh_token": creds.refresh_token,
        "token_expiry":  creds.expiry.isoformat() if creds.expiry else None,
    }


def get_user_info(access_token: str, refresh_token: str) -> dict:
    """Récupère l'email et le nom de l'utilisateur Google."""
    creds = _build_credentials(access_token, refresh_token)
    from googleapiclient.discovery import build
    service = build("oauth2", "v2", credentials=creds)
    info = service.userinfo().get().execute()
    return {
        "email": info.get("email", ""),
        "name":  info.get("name", ""),
    }


def _build_credentials(access_token: str, refresh_token: str):
    """Construit les credentials Google et les rafraîchit si expirés."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    secrets = json.loads(SECRETS_FILE.read_text())
    cfg = secrets.get("web", secrets.get("installed", {}))

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"],
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


# ── Fetch données Google Fit ──────────────────────────────────────────────────

def fetch_fitness_data(access_token: str, refresh_token: str) -> dict:
    """
    Récupère les 7 derniers jours de données Google Fit.
    Retourne un dict compatible avec analyze_health_data().
    """
    from googleapiclient.discovery import build

    creds   = _build_credentials(access_token, refresh_token)
    service = build("fitness", "v1", credentials=creds)

    now         = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = datetime(now.year, now.month, now.day)
    week_ago    = today_start - timedelta(days=7)

    def ms(dt): return int(dt.timestamp() * 1000)

    # ── Activité : pas, calories, minutes actives (datasources par défaut garantis)
    activity_body = {
        "aggregateBy": [
            {"dataTypeName": "com.google.step_count.delta"},
            {"dataTypeName": "com.google.calories.expended"},
            {"dataTypeName": "com.google.active_minutes"},
        ],
        "bucketByTime": {"durationMillis": 86_400_000},  # 1 jour
        "startTimeMillis": ms(week_ago),
        "endTimeMillis":   ms(now),
    }
    activity_resp = service.users().dataset().aggregate(userId="me", body=activity_body).execute()

    # ── Fréquence cardiaque (optionnel — absent si jamais enregistré)
    hr_resp = None
    try:
        hr_resp = service.users().dataset().aggregate(
            userId="me",
            body={
                "aggregateBy": [{"dataTypeName": "com.google.heart_rate.bpm"}],
                "bucketByTime": {"durationMillis": 86_400_000},
                "startTimeMillis": ms(week_ago),
                "endTimeMillis":   ms(now),
            },
        ).execute()
    except Exception:
        pass

    # ── Poids (optionnel — absent si jamais enregistré)
    weight_resp = None
    try:
        weight_resp = service.users().dataset().aggregate(
            userId="me",
            body={
                "aggregateBy": [{"dataTypeName": "com.google.weight"}],
                "bucketByTime": {"durationMillis": 86_400_000},
                "startTimeMillis": ms(week_ago),
                "endTimeMillis":   ms(now),
            },
        ).execute()
    except Exception:
        pass

    # ── Sommeil : sessions séparées (API différente d'aggregate)
    sleep_resp = service.users().sessions().list(
        userId="me",
        startTime=week_ago.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        endTime=now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        activityType=72,  # 72 = sommeil
    ).execute()

    # ── Phases de sommeil (optionnel — absent si l'appareil ne fait pas de
    # sleep staging) : sert à calculer une vraie efficacité de sommeil au
    # lieu d'une estimation basée sur la durée uniquement.
    sleep_segment_resp = None
    try:
        sleep_segment_resp = service.users().dataset().aggregate(
            userId="me",
            body={
                "aggregateBy": [{"dataTypeName": "com.google.sleep.segment"}],
                "bucketByTime": {"durationMillis": 86_400_000},
                "startTimeMillis": ms(week_ago),
                "endTimeMillis":   ms(now),
            },
        ).execute()
    except Exception:
        pass

    return _parse(activity_resp, sleep_resp, hr_resp, weight_resp, sleep_segment_resp)


SLEEP_STAGE_ASLEEP = {2, 4, 5, 6}   # sleep générique, léger, profond, REM
SLEEP_STAGE_TRACKED = {1, 2, 3, 4, 5, 6}  # + awake(1), out-of-bed(3) : compte dans le temps "au lit"


def _compute_sleep_efficiency(segment_response: dict) -> float | None:
    """
    Calcule l'efficacité de sommeil réelle (% temps endormi / temps suivi)
    depuis les phases de sommeil (com.google.sleep.segment) sur la semaine.
    Retourne None si l'appareil ne fait pas de sleep staging (aucun point
    exploitable) — le fallback (_enrich_user_data) prend alors le relais.
    """
    asleep_nanos = tracked_nanos = 0
    for bucket in (segment_response or {}).get("bucket", []):
        for dataset in bucket.get("dataset", []):
            for p in dataset.get("point", []):
                start = p.get("startTimeNanos")
                end   = p.get("endTimeNanos")
                if start is None or end is None:
                    continue
                start, end = int(start), int(end)
                if end <= start:
                    continue
                stage = next((v.get("intVal") for v in p.get("value", []) if "intVal" in v), None)
                if stage not in SLEEP_STAGE_TRACKED:
                    continue
                duration = end - start
                tracked_nanos += duration
                if stage in SLEEP_STAGE_ASLEEP:
                    asleep_nanos += duration
    if tracked_nanos <= 0:
        return None
    return round(asleep_nanos / tracked_nanos * 100, 1)


def _parse(
    activity_response: dict,
    sleep_response: dict = None,
    hr_response: dict = None,
    weight_response: dict = None,
    sleep_segment_response: dict = None,
) -> dict:
    """Convertit les réponses Google Fit en format agent LifeAI."""

    steps_7d      = []
    calories_7d   = []
    active_min_7d = []

    for bucket in activity_response.get("bucket", []):
        bucket_steps = bucket_calories = bucket_active = 0

        for dataset in bucket.get("dataset", []):
            src    = dataset.get("dataSourceId", "")
            points = dataset.get("point", [])
            if not points:
                continue

            if "step_count" in src:
                bucket_steps = sum(
                    v.get("intVal", 0) for p in points for v in p.get("value", [])
                )
            elif "calories" in src:
                bucket_calories = round(
                    sum(v.get("fpVal", 0) for p in points for v in p.get("value", []))
                )
            elif "active_minutes" in src:
                bucket_active = sum(
                    v.get("intVal", 0) for p in points for v in p.get("value", [])
                )

        steps_7d.append(bucket_steps)
        calories_7d.append(bucket_calories)
        active_min_7d.append(bucket_active)

    # ── Fréquence cardiaque depuis la réponse dédiée ──────────────────────────
    heart_rates = []
    for bucket in (hr_response or {}).get("bucket", []):
        for dataset in bucket.get("dataset", []):
            for p in dataset.get("point", []):
                heart_rates += [v["fpVal"] for v in p.get("value", []) if v.get("fpVal")]

    # ── Poids depuis la réponse dédiée ────────────────────────────────────────
    weights = []
    for bucket in (weight_response or {}).get("bucket", []):
        for dataset in bucket.get("dataset", []):
            for p in dataset.get("point", []):
                weights += [v["fpVal"] for v in p.get("value", []) if v.get("fpVal")]

    # ── Sommeil depuis les sessions ───────────────────────────────────────────
    sleep_by_day: dict[str, float] = {}
    for session in (sleep_response or {}).get("session", []):
        start_ms = int(session.get("startTimeMillis", 0))
        end_ms   = int(session.get("endTimeMillis",   0))
        if start_ms and end_ms:
            hours = (end_ms - start_ms) / 3_600_000
            day   = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            sleep_by_day[day] = sleep_by_day.get(day, 0) + hours

    sleep_7d = [round(h, 1) for h in sleep_by_day.values()]

    # ── Valeurs du jour le plus récent ────────────────────────────────────────
    steps_today    = steps_7d[-1]      if steps_7d      else 0
    calories_today = calories_7d[-1]   if calories_7d   else 0
    active_today   = active_min_7d[-1] if active_min_7d else 0
    sleep_tonight  = sleep_7d[-1]      if sleep_7d      else 7.0

    avg_hr = round(sum(heart_rates) / len(heart_rates), 1) if heart_rates else 60.0
    weight = round(weights[-1], 1) if weights else None
    sleep_efficiency = _compute_sleep_efficiency(sleep_segment_response)

    print(
        f"[google_fit] steps={steps_today} | cal={calories_today} | "
        f"active={active_today}min | sleep={sleep_tonight}h | hr={avg_hr} | weight={weight} | "
        f"sleep_efficiency={sleep_efficiency if sleep_efficiency is not None else 'estimée (pas de staging)'}",
        flush=True,
    )

    activity = {
        "steps_today":        steps_today,
        "steps_7d":           steps_7d or [steps_today],
        "active_minutes":     active_today,
        "workouts_this_week": sum(1 for m in active_min_7d if m >= 30),
        "sedentary_hours":    max(0.0, round(16 - active_today / 60, 1)),
        "calories_burned":    calories_today,
    }

    sleep = {
        "duration_hours":     sleep_tonight,
        "sleep_7d":           sleep_7d or [sleep_tonight],
        # efficiency_pct : réelle si sleep staging, sinon estimée depuis la durée (tools.py)
        **({"efficiency_pct": sleep_efficiency} if sleep_efficiency is not None else {}),
    }

    nutrition = {
        "calories_today":     calories_today,
        "calories_goal":      2000,
        "protein_g":          0,
        "carbs_g":            0,
        "fat_g":              0,
        "fiber_g":            0,
        "water_ml":           0,
        "meals_count":        0,
        "processed_food_pct": 0,
    }

    return {
        "activity":    activity,
        "sleep":       sleep,
        "nutrition":   nutrition,
        "_resting_hr": avg_hr,
        "_weight_kg":  weight,
    }
