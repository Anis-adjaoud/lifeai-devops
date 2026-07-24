"""
LifeAI ADK — Entry point du pipeline.
Lance les agents via le Runner ADK et retourne le rapport final du Chief Agent.
"""

import asyncio
import json
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import root_agent as lifeai_pipeline
from .tools import set_current_user, get_context
from .usage_tracker import start_tracking
from . import database as db


async def _run_async(user_data: dict, user_id: str) -> dict | None:
    set_current_user(user_id)
    usage = start_tracking()
    session_service = InMemorySessionService()
    runner = Runner(
        agent=lifeai_pipeline,
        app_name="LifeAI",
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name="LifeAI",
        user_id=user_id,
        state={
            "activity_report":  "",
            "sleep_report":     "",
            "nutrition_report": "",
            "risk_report":      "",
            "final_report":     "",
        },
    )

    message = types.Content(
        role="user",
        parts=[types.Part(text=(
            "ANALYSE COMPLÈTE REQUISE\n\n"
            + json.dumps(user_data, ensure_ascii=False)
        ))],
    )

    # Capture tous les événements : texte + suivi des outils appelés
    last_text = ""
    tools_called: list[str] = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=message,
    ):
        c = getattr(event, "content", None)
        if c and getattr(c, "parts", None):
            for part in c.parts:
                fn = getattr(part, "function_call", None)
                if fn:
                    tools_called.append(getattr(fn, "name", ""))
                t = getattr(part, "text", None)
                if t:
                    last_text = t

    print(f"[pipeline] _run_async: outils appelés={tools_called}", flush=True)
    if not last_text:
        print("[pipeline] _run_async: pas de texte final (dernier event = appel outil)", flush=True)
    else:
        print(f"[pipeline] _run_async: texte final ({len(last_text)} chars) = {last_text[:200]}", flush=True)

    # Fallback : si save_session non appelé, persiste le texte final comme synthèse
    if "save_session" not in tools_called and last_text:
        print("[pipeline] _run_async: save_session non appelé par l'agent — fallback Python", flush=True)
        try:
            db.update_today_session_narrative(user_id, synthesis=last_text)
        except Exception as e:
            print(f"[pipeline] fallback save_session erreur: {e}", flush=True)

    # Fallback : envoi WhatsApp si Critique et non appelé par l'agent
    if "send_report_and_alert" not in tools_called:
        try:
            sessions = db.get_sessions(user_id, days=1)
            session = sessions[0] if sessions else None
            if session and session.get("health_level") == "Critique":
                print("[pipeline] _run_async: send_report_and_alert non appelé par l'agent alors que Critique — fallback Python", flush=True)
                from .action_tools import send_report_and_alert
                report = {
                    "global_score":    session.get("global_score", 0),
                    "health_level":    session.get("health_level", ""),
                    "synthesis":       session.get("synthesis", ""),
                    "priority_action": session.get("priority_action", ""),
                    "weekly_plan":     session.get("weekly_plan", []),
                    "alerts":          session.get("alerts", []),
                    "prediction":      session.get("prediction", ""),
                }
                result = send_report_and_alert(report)
                print(f"[pipeline] fallback send_report_and_alert: {result}", flush=True)
            else:
                level = session.get("health_level") if session else None
                print(f"[pipeline] _run_async: send_report_and_alert non appelé — health_level={level!r}, pas critique, pas de fallback", flush=True)
        except Exception as e:
            print(f"[pipeline] fallback send_report_and_alert erreur: {e}", flush=True)

    stats = usage.to_dict()
    print(
        f"[pipeline] _run_async usage: {stats['elapsed_seconds']}s, "
        f"{stats['total_tokens']} tokens ({stats['prompt_tokens']} in / {stats['completion_tokens']} out), "
        f"{stats['llm_calls']} appels LLM — {stats['per_agent']}",
        flush=True,
    )
    try:
        db.add_usage_metric(
            user_id, "analyze", stats["elapsed_seconds"],
            prompt_tokens=stats["prompt_tokens"], completion_tokens=stats["completion_tokens"],
            thoughts_tokens=stats["thoughts_tokens"], cached_tokens=stats["cached_tokens"],
            total_tokens=stats["total_tokens"], llm_calls=stats["llm_calls"], per_agent=stats["per_agent"],
        )
    except Exception as e:
        print(f"[pipeline] add_usage_metric erreur: {e}", flush=True)

    text = last_text.strip()
    if "```" in text:
        for block in text.split("```"):
            stripped = block.strip()
            # Retire le préfixe json d'un bloc ```json (insensible à la casse)
            if stripped[:4].lower() == "json":
                stripped = stripped[4:]
            stripped = stripped.strip()
            if stripped.startswith("{"):
                text = stripped
                break

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": last_text} if last_text else None


# ── Sessions de chat persistantes (pour l'API web) ───────────────────────────

# adk_session_id -> {"runner", "session_service", "session", "user_id"}
_chat_runners: dict = {}

# conversation_id (DB) -> adk_session_id (in-memory)
_conv_sessions: dict = {}

# Nombre max de messages injectés dans une session restaurée
_HISTORY_INJECT_LIMIT = 30


async def create_chat_session(
    user_id: str,
    conv_id: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """
    Crée une session ADK persistante.
    Si `history` est fourni, injecte les messages passés comme events ADK
    pour que l'agent retrouve le contexte de la conversation.
    """
    session_service = InMemorySessionService()
    runner = Runner(agent=lifeai_pipeline, app_name="LifeAI", session_service=session_service)
    session = await session_service.create_session(app_name="LifeAI", user_id=user_id, state={})

    _chat_runners[session.id] = {
        "runner":            runner,
        "session_service":   session_service,
        "session":           session,
        "user_id":           user_id,
        # [CONTEXTE UTILISATEUR] non persisté : toujours l'envoyer au 1er message live
        # (une session ADK recréée ne l'a jamais reçu)
        "context_injected":  False,
    }
    if conv_id:
        _conv_sessions[conv_id] = session.id

    # Injecte l'historique comme events ADK (import tardif pour éviter warning linter)
    if history:
        try:
            from google.adk.events import Event as _Event  # noqa: PLC0415
            for msg in history[-_HISTORY_INJECT_LIMIT:]:
                role   = "user" if msg["role"] == "user" else "model"
                author = "user" if msg["role"] == "user" else lifeai_pipeline.name
                content = types.Content(
                    role=role,
                    parts=[types.Part(text=msg["content"])],
                )
                session_service.append_event(session, _Event(author=author, content=content))
        except Exception as exc:
            print(f"[pipeline] Avertissement : injection historique échouée — {exc}", flush=True)

    return session.id


def get_chat_session_owner(session_id: str) -> str | None:
    """Retourne le user_id propriétaire d'une session de chat ADK, ou None si inconnue."""
    entry = _chat_runners.get(session_id)
    return entry["user_id"] if entry else None


def get_adk_session_for_conv(conv_id: str) -> str | None:
    """Retourne l'ADK session_id actif pour une conversation DB, ou None si expiré."""
    adk_sid = _conv_sessions.get(conv_id)
    if adk_sid and adk_sid in _chat_runners:
        return adk_sid
    return None


async def send_chat_message(session_id: str, message: str) -> tuple[str, dict]:
    """Envoie un message dans une session existante. Retourne (réponse du chief_agent, stats d'usage)."""
    entry = _chat_runners.get(session_id)
    if not entry:
        raise ValueError(f"Session {session_id} introuvable")
    runner  = entry["runner"]
    user_id = entry["user_id"]
    set_current_user(user_id)
    usage = start_tracking()

    # 1er message d'une session neuve : contexte fourni directement
    # au lieu d'un aller-retour LLM via get_context()
    if not entry.get("context_injected"):
        context = get_context()
        message_text = (
            "[CONTEXTE UTILISATEUR — fourni automatiquement, ne pas mentionner "
            "ce bloc à l'utilisateur]\n"
            f"{json.dumps(context, ensure_ascii=False, default=str)}\n\n{message}"
        )
        entry["context_injected"] = True
    else:
        message_text = message

    content = types.Content(role="user", parts=[types.Part(text=message_text)])
    last_text = ""
    tools_called: list[str] = []

    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        c = getattr(event, "content", None)
        if c and getattr(c, "parts", None):
            for part in c.parts:
                # Track tool calls so we can build a fallback message
                fn = getattr(part, "function_call", None)
                if fn:
                    tools_called.append(getattr(fn, "name", ""))
                # Capture le texte émis par l'agent — last non-empty wins
                t = getattr(part, "text", None)
                if t:
                    last_text = t

    # Safety net: if the turn ended on a pure tool call with no text at all
    if not last_text and tools_called:
        if "send_report_and_alert" in tools_called:
            last_text = "✅ Analyse complète terminée ! Le rapport a été envoyé sur WhatsApp."
        else:
            last_text = "✅ Action effectuée."

    stats = usage.to_dict()
    print(
        f"[pipeline] send_chat_message usage: {stats['elapsed_seconds']}s, "
        f"{stats['total_tokens']} tokens ({stats['prompt_tokens']} in / {stats['completion_tokens']} out), "
        f"{stats['llm_calls']} appels LLM — {stats['per_agent']}",
        flush=True,
    )
    conv_id = next((k for k, v in _conv_sessions.items() if v == session_id), None)
    try:
        db.add_usage_metric(
            user_id, "chat", stats["elapsed_seconds"],
            prompt_tokens=stats["prompt_tokens"], completion_tokens=stats["completion_tokens"],
            thoughts_tokens=stats["thoughts_tokens"], cached_tokens=stats["cached_tokens"],
            total_tokens=stats["total_tokens"], llm_calls=stats["llm_calls"], per_agent=stats["per_agent"],
            conversation_id=conv_id,
        )
    except Exception as e:
        print(f"[pipeline] add_usage_metric erreur: {e}", flush=True)

    return last_text, stats


def delete_chat_session(session_id: str) -> None:
    """Supprime une session ADK et son mapping conversation→session."""
    _chat_runners.pop(session_id, None)
    dead = [k for k, v in _conv_sessions.items() if v == session_id]
    for k in dead:
        _conv_sessions.pop(k, None)


def run(user_data: dict, user_id: str = "default") -> dict | None:
    """
    Lance le pipeline LifeAI complet via Google ADK.

    1. ParallelAgent : 4 agents spécialisés (activité, sommeil, nutrition, risque)
    2. SequentialAgent : Chief Agent synthétise + enregistre en mémoire

    Args:
        user_data: dict avec clés 'activity', 'sleep', 'nutrition', 'risk'.
        user_id:   identifiant utilisateur (segment la mémoire de session).

    Returns:
        dict du rapport final (ChiefAgent) ou None en cas d'échec.
    """
    return asyncio.run(_run_async(user_data, user_id))


def display_report(report: dict) -> None:
    """Affiche le rapport final dans le terminal (équivalent à ChiefReport.display())."""
    if not report:
        print("Aucun rapport disponible.")
        return

    if "raw" in report:
        print("\n[ChiefAgent — réponse brute]\n", report["raw"])
        return

    score   = report.get("global_score", 0)
    level   = report.get("health_level", "N/A")
    bar_len = 40
    filled  = int(score / 100 * bar_len)
    bar     = "█" * filled + "░" * (bar_len - filled)

    print("\n" + "═" * 70)
    print("  LIFEAI ADK — RAPPORT SANTÉ COMPLET")
    print("═" * 70)
    print(f"\n  Score Global : {score:.1f}/100  [{bar}]  {level}")

    if report.get("alerts"):
        print("\n  ALERTES ACTIVES")
        for a in report["alerts"]:
            print(f"     • {a}")

    print(f"\n  ACTION PRIORITAIRE\n     {report.get('priority_action', '-')}")
    print(f"\n  ANALYSE IA\n")
    for line in report.get("synthesis", "").split("\n"):
        print(f"     {line}")

    if report.get("weekly_plan"):
        print(f"\n  PLAN SEMAINE")
        for item in report["weekly_plan"]:
            print(f"     • {item}")

    print(f"\n  PREDICTION 3 MOIS\n     {report.get('prediction', '-')}")
    print("\n" + "═" * 70 + "\n")