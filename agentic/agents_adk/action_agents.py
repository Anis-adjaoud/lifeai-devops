"""
LifeAI — Agents d'action.

AlertAgent       : envoie un message WhatsApp quand un score est Critique.
ReportAgent      : envoie le rapport complet par WhatsApp (+ génère un PDF local).
WeeklyCoachAgent : envoie chaque semaine un bilan WhatsApp personnalisé.
"""

from google.adk.agents import LlmAgent
from google.adk.planners import BuiltInPlanner
from google.genai import types as genai_types
from .model_config import MODEL_CHIEF

from .action_tools import (
    send_report_and_alert,
    get_weekly_summary,
    send_whatsapp,
    format_weekly_message,
)
from .tools import get_context, save_profile
from .usage_tracker import log_model_response


# Agents légers : pas de raisonnement étendu. Thinking config via
# LlmAgent.planner (un BuiltInPlanner par agent).
def _no_thinking_planner() -> BuiltInPlanner:
    return BuiltInPlanner(
        thinking_config=genai_types.ThinkingConfig(thinking_budget=0)
    )

# ── AlertAgent ────────────────────────────────────────────────────────────────

alert_agent = LlmAgent(
    name="alert_agent",
    model=MODEL_CHIEF,
    planner=_no_thinking_planner(),
    description="Envoie une alerte WhatsApp quand un score est Critique. Passe le rapport complet.",
    instruction="""Agent d'alerte LifeAI.
Reçois un rapport d'analyse et appelle send_report_and_alert(report).
La fonction gère automatiquement l'alerte et le rapport WhatsApp.
Si le numéro manque dans le profil, demande-le à l'utilisateur puis appelle save_profile.
Français.""",
    tools=[send_report_and_alert, get_context, save_profile],
    after_model_callback=log_model_response,
)

# ── ReportAgent ───────────────────────────────────────────────────────────────

report_agent = LlmAgent(
    name="report_agent",
    model=MODEL_CHIEF,
    planner=_no_thinking_planner(),
    description="Envoie le rapport complet par WhatsApp et génère un PDF.",
    instruction="""Agent de rapport LifeAI.
Reçois un rapport d'analyse et appelle send_report_and_alert(report).
La fonction envoie le WhatsApp et génère le PDF automatiquement.
Si le numéro manque dans le profil, demande-le à l'utilisateur puis appelle save_profile.
Français.""",
    tools=[send_report_and_alert, get_context, save_profile],
    after_model_callback=log_model_response,
)

# ── WeeklyCoachAgent ──────────────────────────────────────────────────────────

weekly_coach_agent = LlmAgent(
    name="weekly_coach_agent",
    model=MODEL_CHIEF,
    planner=_no_thinking_planner(),
    description="Envoie chaque semaine un bilan WhatsApp personnalisé.",
    instruction="""Agent coaching hebdomadaire LifeAI.
1. Appelle get_weekly_summary() pour les données de la semaine.
2. Appelle get_context() pour le profil (numéro, prénom).
3. Appelle format_weekly_message(summary) pour le message.
4. Appelle send_whatsapp(phone, message) avec le numéro du profil.
Si numéro absent, demande-le puis save_profile.
Français.""",
    tools=[get_weekly_summary, format_weekly_message, get_context, save_profile, send_whatsapp],
    after_model_callback=log_model_response,
)
