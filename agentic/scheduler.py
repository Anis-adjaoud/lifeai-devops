"""
LifeAI — Scheduler automatique.

Lance chaque matin une analyse Google Fit pour chaque utilisateur enregistré :
  1. Récupère les données depuis Google Fit (7 derniers jours)
  2. Passe les données au chief_agent via le pipeline ADK (Gemini)
  3. Le chief_agent gère : scores, save_session, WhatsApp, PDF

Démarrage :
    from agentic.scheduler import start_scheduler
    scheduler = start_scheduler()

Lancement manuel (test) :
    from agentic.scheduler import run_all_users
    run_all_users()
"""

from __future__ import annotations

import traceback
from datetime import datetime

from .agents_adk import database as db
from .google_fit import fetch_fitness_data


# ── Analyse d'un utilisateur ──────────────────────────────────────────────────

def _analyze_user(user_id: str, tokens: dict) -> None:
    """Fetch Google Fit + pipeline ADK complet pour un utilisateur."""
    print(f"[scheduler] -> {user_id} ...", end=" ", flush=True)
    try:
        from .agents_adk.pipeline import run as adk_run

        user_data = fetch_fitness_data(tokens["access_token"], tokens["refresh_token"])

        # Sauvegarde directe des métriques brutes — indépendant du LLM
        act   = user_data.get("activity", {})
        sleep = user_data.get("sleep", {})
        db.add_health_metrics(
            user_id=user_id,
            steps_today    = act.get("steps_today", 0),
            steps_7d       = act.get("steps_7d", []),
            active_minutes = act.get("active_minutes", 0),
            sleep_hours    = sleep.get("duration_hours", 0),
            sleep_7d       = sleep.get("sleep_7d", []),
            calories       = act.get("calories_burned", 0),
            heart_rate     = user_data.get("_resting_hr"),
            weight_kg      = user_data.get("_weight_kg"),
        )

        # Pipeline ADK pour scoring, notes, alertes WhatsApp
        adk_run(user_data, user_id=user_id)

        sessions = db.get_sessions(user_id, days=1)
        if sessions:
            g     = sessions[0]["global_score"]
            level = "Excellent" if g >= 80 else "Bon" if g >= 65 else "Attention" if g >= 45 else "Critique"
            print(f"{level} ({g})", flush=True)
        else:
            print("métriques sauvegardées", flush=True)

    except Exception:
        print("ERREUR")
        traceback.print_exc()


# ── Analyse de tous les utilisateurs ─────────────────────────────────────────

def run_all_users() -> None:
    """Lance l'analyse pour tous les utilisateurs connectés à Google Fit."""
    tokens_by_user = db.get_all_oauth_tokens(provider="google_fit")
    if not tokens_by_user:
        print("[scheduler] Aucun utilisateur connecté à Google Fit.")
        return
    print(f"[scheduler] {datetime.now().strftime('%Y-%m-%d %H:%M')} — {len(tokens_by_user)} utilisateur(s)")
    for user_id, tokens in tokens_by_user.items():
        _analyze_user(user_id, tokens)


# ── Démarrage du scheduler ────────────────────────────────────────────────────

def start_scheduler(hour: int = 21, minute: int = 7):
    """
    Démarre le scheduler en arrière-plan.
    Déclenche run_all_users() chaque jour à l'heure définie (défaut : 7h00).

    Args:
        hour:   Heure du déclenchement (0-23).
        minute: Minute du déclenchement (0-59).

    Returns:
        L'instance APScheduler (pour l'arrêter avec scheduler.shutdown()).
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(timezone="Europe/Paris")
    scheduler.add_job(
        run_all_users,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_analysis",
        name=f"Analyse quotidienne Google Fit ({hour:02d}:{minute:02d})",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    job = scheduler.get_job("daily_analysis")
    next_run = job.next_run_time if job else "inconnu"
    print(f"[scheduler] Démarré — prochain run : {next_run}")
    print(f"[scheduler] Heure système locale : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return scheduler
