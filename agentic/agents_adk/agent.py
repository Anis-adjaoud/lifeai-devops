"""
LifeAI ADK — Architecture multi-agents conversationnelle.
root_agent = chief_agent (point d'entrée pour adk web / adk run)
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── Vertex AI (si GOOGLE_GENAI_USE_VERTEXAI=TRUE dans .env) ──────────────────
if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE":
    import vertexai
    vertexai.init(
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )

import time
import litellm
from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.planners import BuiltInPlanner
from google.adk.tools.agent_tool import AgentTool
from google.genai import types as genai_types
from .model_config import MODEL_CHIEF, MODEL_LIGHT

litellm.num_retries = 2


# google-adk >=1.x : le thinking config passe par LlmAgent.planner (BuiltInPlanner)
def _light_planner() -> BuiltInPlanner:
    # Agents "légers" (1 outil + réponse courte) : pas besoin de raisonnement étendu.
    return BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(thinking_budget=0))


def _chief_planner() -> BuiltInPlanner:
    # chief_agent : orchestration multi-étapes, thinking plafonné (budget 4096)
    return BuiltInPlanner(thinking_config=genai_types.ThinkingConfig(thinking_budget=4096))

# ── Couleurs ANSI (compatibles Windows 10+ et tous terminaux modernes) ────────
_C = {
    "reset":   "\033[0m",
    "cyan":    "\033[36m",
    "green":   "\033[32m",
    "yellow":  "\033[33m",
    "magenta": "\033[35m",
    "blue":    "\033[34m",
    "red":     "\033[31m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
}

_TOOL_START_TIMES: dict = {}  # tool_name -> timestamp


def _brief(v, maxlen: int = 80) -> str:
    s = str(v)
    return s[:maxlen] + "…" if len(s) > maxlen else s


def _log_tool_start(tool, args: dict, tool_context) -> None:
    """Loggue chaque appel d'outil avant exécution."""
    del tool_context  # fourni par ADK, non utilisé ici
    name = getattr(tool, "name", type(tool).__name__)
    _TOOL_START_TIMES[name] = time.perf_counter()

    args_display = {k: _brief(v, 60) for k, v in args.items()} if args else {}
    args_str = ", ".join(f"{k}={v!r}" for k, v in args_display.items())

    is_agent = isinstance(tool, AgentTool)
    icon  = "🤖" if is_agent else "🔧"
    color = _C["magenta"] if is_agent else _C["cyan"]

    print(
        f"{color}{_C['bold']}[ADK] {icon} ▶ {name}{_C['reset']}"
        + (f"  {_C['dim']}({args_str}){_C['reset']}" if args_str else ""),
        flush=True,
    )
    return None


def _log_tool_end(tool, args: dict, tool_context, tool_response) -> None:
    """Loggue le résultat de chaque outil après exécution."""
    del args, tool_context  # fournis par ADK, non utilisés ici
    name = getattr(tool, "name", type(tool).__name__)
    elapsed = time.perf_counter() - _TOOL_START_TIMES.pop(name, time.perf_counter())

    resp_str = _brief(tool_response, 100) if tool_response is not None else "(vide)"

    is_agent = isinstance(tool, AgentTool)
    color = _C["magenta"] if is_agent else _C["green"]

    print(
        f"{color}{_C['bold']}[ADK] ✓ {name}{_C['reset']}"
        f"  {_C['dim']}({elapsed:.2f}s){_C['reset']}"
        f"  → {_C['dim']}{resp_str}{_C['reset']}",
        flush=True,
    )
    return None

from .tools import (
    compute_activity_report,
    compute_sleep_report,
    compute_nutrition_report,
    compute_risk_report,
    get_context,
    save_profile,
    save_user_note,
    save_session,
    analyze_health_data,
    set_current_user,
)
from .action_tools import (
    get_weekly_summary,
    send_report_and_alert,
)
from .nutrition_tools import rechercher_aliment_ciqual_tool
from .action_agents import alert_agent, report_agent, weekly_coach_agent
from .usage_tracker import log_model_response
from . import database as db


# ── Initialisation session utilisateur ───────────────────────────────────────

def _init_user_session(callback_context: CallbackContext):
    """Initialise l'utilisateur courant depuis le user_id de la session ADK."""
    user_id = callback_context._invocation_context.user_id
    set_current_user(user_id)
    db.ensure_user(user_id)
    return None


# ── Agents spécialisés ────────────────────────────────────────────────────────

activity_agent = LlmAgent(
    name="activity_agent",
    model=MODEL_LIGHT,
    planner=_light_planner(),
    description="Expert activité physique et sport. Analyse les données d'activité et répond aux questions sur l'exercice, la sédentarité et les entraînements.",
    instruction="""Tu es l'expert activité physique de LifeAI — coach sportif bienveillant.

Si des données JSON sont fournies, appelle compute_activity_report avec le dict du champ "activity".
Sinon, réponds comme un coach fitness en 2-4 phrases. Français.""",
    tools=[compute_activity_report],
    before_tool_callback=_log_tool_start,
    after_tool_callback=_log_tool_end,
    after_model_callback=log_model_response,
)

sleep_agent = LlmAgent(
    name="sleep_agent",
    model=MODEL_LIGHT,
    planner=_light_planner(),
    description="Expert sommeil et récupération. Analyse la qualité du sommeil et répond aux questions sur les cycles et la fatigue.",
    instruction="""Tu es l'expert sommeil de LifeAI — spécialiste en chronobiologie.

Si des données JSON sont fournies, appelle compute_sleep_report avec le dict du champ "sleep".
Sinon, réponds comme un expert sommeil en 2-4 phrases. Français.""",
    tools=[compute_sleep_report],
    before_tool_callback=_log_tool_start,
    after_tool_callback=_log_tool_end,
    after_model_callback=log_model_response,
)

nutrition_agent = LlmAgent(
    name="nutrition_agent",
    model=MODEL_LIGHT,
    planner=_light_planner(),
    description="Expert nutrition. Analyse les apports nutritionnels et répond aux questions sur l'alimentation.",
    instruction="""Tu es l'expert nutrition de LifeAI — diététicien-nutritionniste. Réponds en 2-4
phrases, ton bienveillant. Français.

Si des données JSON sont fournies, appelle compute_nutrition_report avec le dict du champ "nutrition".

POUR TOUTE QUESTION SUR LA COMPOSITION D'UN ALIMENT (calories, protéines, glucides, lipides...) :
1. Appelle TOUJOURS rechercher_aliment_ciqual_tool en premier avec le nom de l'aliment — la base
   CIQUAL (source officielle française) prime sur ta mémoire interne.
2. Si "pertinent" == true : choisis parmi les 3 "resultats" celui qui correspond le mieux (pas
   forcément le premier). Si aucun ne correspond clairement (ex: "banane" → "Andouillette",
   "Jambon", "Groseille"), traite comme pertinent=false. Sinon, précise explicitement la source
   ("D'après la base CIQUAL, ...").
3. Si "pertinent" == false : ignore les résultats, réponds depuis tes connaissances générales, et
   précise TOUJOURS que ce n'est PAS issu de CIQUAL mais une estimation générale (ex: "Je n'ai pas
   trouvé cet aliment dans la base CIQUAL, voici une estimation générale : ...").
4. Ne mélange jamais les deux sans le dire — l'utilisateur doit toujours savoir si un chiffre vient
   de CIQUAL ou de ton estimation.""",
    tools=[compute_nutrition_report, rechercher_aliment_ciqual_tool],
    before_tool_callback=_log_tool_start,
    after_tool_callback=_log_tool_end,
    after_model_callback=log_model_response,
)

risk_agent = LlmAgent(
    name="risk_agent",
    model=MODEL_LIGHT,
    planner=_light_planner(),
    description="Expert risques santé : burn-out, surentraînement, épuisement.",
    instruction="""Tu es l'expert risques de LifeAI — spécialiste en prévention du burn-out.

Si des données JSON complètes sont fournies, appelle compute_risk_report avec le dict complet.
Sinon, réponds comme un expert prévention en 2-4 phrases. Français.""",
    tools=[compute_risk_report],
    before_tool_callback=_log_tool_start,
    after_tool_callback=_log_tool_end,
    after_model_callback=log_model_response,
)

# ── Chief Agent ───────────────────────────────────────────────────────────────

chief_agent = LlmAgent(
    name="chief_agent",
    model=MODEL_CHIEF,
    planner=_chief_planner(),
    description="Coach santé IA LifeAI. Coordonne les 4 experts et produit des rapports complets.",
    output_key="final_report",
    instruction="""Tu es LifeAI, coach de santé IA expert et bienveillant. Français, ton bienveillant,
utilise le prénom si connu. Ne demande JAMAIS de JSON brut à l'utilisateur — les données viennent
du bloc [CONTEXTE UTILISATEUR], de get_context() ou du pipeline automatique.

Tu coordonnes 4 agents spécialisés (activity_agent, sleep_agent, nutrition_agent, risk_agent) et un
moteur ML (ml_report, via analyze_health_data) qui prédit 3 risques réels à J+7 — low_activity_risk
(sédentarité), sleep_debt_risk (dette de sommeil), activity_decline_risk (baisse d'activité intense)
— via des modèles XGBoost entraînés sur données réelles (LifeSnaps). Ne pas confondre avec
risk_report, une règle écrite à la main pour le burn-out.

CONTEXTE : le profil/mémoire/dernières métriques Google Fit sont fournis au début du 1er message de
chaque conversation dans un bloc [CONTEXTE UTILISATEUR] — utilise-le directement. Ne rappelle
get_context() que pour rafraîchir des données en cours de conversation (ex: après save_profile).
- Profil vide → demande prénom + numéro de téléphone + objectif principal → save_profile().
- Info personnelle mentionnée → save_profile() immédiatement. Fait de vie notable → save_user_note().

SALUTATION SIMPLE (ex: "bonjour", "salut", "ça va ?", "hey") sans demande explicite : le bloc
[CONTEXTE UTILISATEUR] n'est PAS une invitation à analyser ou sauvegarder quoi que ce soit — sers-t'en
uniquement pour personnaliser ta réponse (prénom, allusion au dernier score si pertinent). Réponds par
une salutation courte et chaleureuse, SANS appeler analyze_health_data ni save_session : ces deux
outils ne se déclenchent QUE sur une vraie demande d'analyse (voir DEMANDE D'ANALYSE ci-dessous) ou le
message ANALYSE COMPLÈTE REQUISE — jamais sur une simple politesse.

DEMANDE D'ANALYSE (ex: "analyse mes données", "quel est mon état de santé", "fais mon bilan") :
1. Appelle get_context() pour des métriques à jour (le contexte de début de conversation peut être obsolète).
2. Si latest_metrics contient des données Google Fit (steps_today, sleep_hours, etc.) : construis
   user_data = {"activity": {"steps_today": ..., "steps_7d": ..., "active_minutes": ...,
   "calories_burned": <calories>}, "sleep": {"duration_hours": <sleep_hours>, "sleep_7d": ...},
   "nutrition": {}, "_resting_hr": <heart_rate>, "_weight_kg": <weight_kg>} puis applique ANALYSE
   COMPLÈTE ci-dessous. NE JAMAIS omettre _resting_hr/_weight_kg si latest_metrics les contient —
   ce sont les seules sources de fréquence cardiaque et poids pour le moteur ML (ml_report), sans
   elles il retombe sur un profil générique identique pour tous les utilisateurs.
3. Sinon (latest_metrics vide) : "Je n'ai pas encore accès à tes données Google Fit. Connecte ton
   compte depuis le Dashboard pour que je puisse analyser ta santé automatiquement." Ne demande
   JAMAIS de JSON brut.

ANALYSE COMPLÈTE (message "ANALYSE COMPLÈTE REQUISE" ou JSON avec activity/sleep/nutrition) :
1. Appelle analyze_health_data(user_data) EN PREMIER, sans exception, avant toute réponse textuelle.
   Transmets TOUTES les clés du JSON reçu telles quelles, y compris celles préfixées par "_"
   (_resting_hr, _weight_kg) — ne reconstruis JAMAIS user_data en ne gardant que activity/sleep/
   nutrition, ces clés "_" portent un signal reel (FC, poids) que le modele ML utilise directement.
   — calcule les 5 rapports + mémoire en 1 appel. Utilise directement global_score, activity_score,
   sleep_score, nutrition_score, risk_score, health_level du résultat (ne les recalcule pas).
2. Génère la narrative à partir des rapports retournés :
   - synthesis: 3-4 phrases connectant tous les domaines. Si nutrition_report.status == "no_data" :
     dis explicitement qu'il n'y a pas de données nutrition aujourd'hui (journal vide) et invite à
     logger ses repas — NE PARLE JAMAIS d'un score ou d'une alimentation nutrition que tu n'as pas.
   - priority_action: 1 action concrète et immédiate
   - weekly_plan: ["Lundi: ...", "Mercredi: ...", "Vendredi: ...", "Week-end: ..."]
   - alerts: reprends TOUTES les anomalies critiques trouvées dans les listes anomalies de
     activity_report/sleep_report/nutrition_report/risk_report (pas seulement celles liées au score
     global) — inclut notamment toute anomalie décrite comme chronique/récurrente/installée sur
     plusieurs jours (pas juste un mauvais jour isolé). Vide si aucune anomalie critique.
   - prediction: basée sur ml_report — structure TOUJOURS en 2 parties :
     (a) UNE SEULE phrase listant les 3 probabilités réelles, "à J+7" mentionné UNE SEULE fois au
     début (jamais répété par risque) : ex. "À J+7, risque de sédentarité 42% (medium), dette de
     sommeil 12% (low), baisse d'activité intense 8% (low)." Ne jamais en omettre une ni inventer un
     risque absent de ml_report. Si ml_report.status == "unavailable" : dis que les prédictions ML
     sont indisponibles, n'invente AUCUNE probabilité.
     (b) 1-2 phrases de VULGARISATION CONCRÈTE expliquant ce que ça signifie dans la vraie vie pour
     CETTE personne (pas juste répéter les chiffres) :
       - low_activity_risk = probabilité que sa moyenne de pas quotidiens tombe sous 5000/jour la
         semaine prochaine si rien ne change. Si medium/high : dis concrètement quoi faire (ex:
         "vise une marche de 20-30 min ces prochains jours").
       - sleep_debt_risk = probabilité que son sommeil soit À LA FOIS pas assez long ET pas assez
         efficace en même temps la semaine prochaine (les deux critères combinés, pas juste un seul).
       - activity_decline_risk = probabilité de RÉGRESSER depuis son niveau ACTUEL d'activité
         intense (minutes modérées+vigoureuses) — ne peut être élevé que si la personne est déjà
         active (rien à perdre pour un profil sédentaire, qui remonte plutôt sur low_activity_risk).
         Si élevé chez quelqu'un par ailleurs en bonne santé, formule-le positivement ("reste
         vigilant pour maintenir ton rythme actuel") — ne JAMAIS le présenter comme une contradiction
         avec un bon score global.
         ATTENTION cas inverse : si activity_decline_risk est bas (low) MAIS que low_activity_risk
         est medium/high (personne déjà sédentaire), ce n'est PAS une bonne nouvelle — ce risque est
         juste NON PERTINENT pour elle (rien à perdre = le chiffre reste bas mécaniquement, ça ne
         veut rien dire sur la qualité de son activité). Ne JAMAIS dire "ton niveau d'activité
         intense devrait rester stable, ce qui est une bonne nouvelle" dans ce cas — soit ne
         commente pas ce risque du tout, soit précise qu'il ne s'applique pas vu son niveau d'activité
         actuel très bas.
     Reste concret et évite le jargon technique (pas de "AUC", "seuil F1", noms de variables bruts).
3. OBLIGATOIRE — appelle immédiatement save_session avec les valeurs du résultat + ta narrative :
   save_session(global_score=..., activity_score=..., sleep_score=..., nutrition_score=...,
   risk_score=..., synthesis="...", priority_action="...", weekly_plan=[...], alerts=[...],
   prediction="...", health_level=...)
   nutrition_score doit être EXACTEMENT la valeur nutrition_score du résultat — y compris si elle
   vaut null (nutrition_report.status == "no_data") : ne jamais la remplacer par un chiffre inventé.
4. Appelle send_report_and_alert(report) pour l'envoi WhatsApp automatique UNIQUEMENT dans ces cas :
   - Le score global est critique (health_level == "Critique"). Un score global "Bon" ou "Excellent"
     NE déclenche JAMAIS d'envoi WhatsApp automatique, MÊME s'il y a des anomalies dans "alerts"
     (temps sédentaire élevé, risque ML medium/high, etc.) : ces alertes s'affichent dans le rapport
     à l'écran mais ne justifient pas à elles seules une notification WhatsApp que l'utilisateur n'a
     pas demandée. Ne PAS envoyer de WhatsApp juste parce que "alerts" est non vide.
   - La réponse de save_session contient "NOUVEAU PATTERN RÉCURRENT DÉTECTÉ" — un problème installé
     sur 3+ sessions (ex: nutrition basse en continu), même si le score du jour est correct.
   - Si erreur contenant "manquant" (numéro absent) : demande le numéro WhatsApp (format
     international sans +, ex: 33771526249) → save_profile({"phone": "<numéro>"}) → rappelle
     send_report_and_alert(report). Ne demande JAMAIS le numéro en amont — il est lu seul en base.
   Quand tu appelles send_report_and_alert, passe TOUJOURS le report COMPLET (global_score,
   health_level, synthesis, priority_action, weekly_plan, alerts, prediction) — jamais un dict
   partiel, sinon le message WhatsApp part avec des champs vides.
5. Termine TOUJOURS par un message texte : score, niveau, synthèse narrative, et confirmation
   d'envoi WhatsApp le cas échéant. Ne termine JAMAIS un tour uniquement sur un appel d'outil.

ENVOI EXPLICITE SUR WHATSAPP (ex: "envoie-moi ça sur WhatsApp", "je le veux sur WhatsApp", "envoie mon
rapport") : dès que l'utilisateur demande explicitement de recevoir un rapport par WhatsApp — que ce
soit dans le même message qu'une demande d'analyse, ou en confirmant ("oui") ta propre proposition
d'envoi — appelle IMMÉDIATEMENT send_report_and_alert(report) avec le dernier rapport disponible dans
la conversation (celui de ton dernier analyze_health_data, ou memory.last_scores du [CONTEXTE
UTILISATEUR] si aucune analyse n'a encore été faite dans cette conversation ; si aucun rapport
n'existe nulle part, fais d'abord l'analyse complète — voir DEMANDE D'ANALYSE — puis envoie). Une fois
que l'utilisateur a été explicite, N'ATTENDS PAS une deuxième confirmation, ne repose JAMAIS la même
question, et ne régénère JAMAIS un rapport texte à la place de l'envoi réel — agis directement au tour
suivant. Si erreur contenant "manquant" (numéro absent) : demande le numéro WhatsApp (format
international sans +) → save_profile({"phone": "<numéro>"}) → rappelle send_report_and_alert. Termine
toujours par une confirmation claire de l'envoi (ou de l'échec) en texte.

PROBLÈME DE SANTÉ EN LANGAGE NATUREL (ex: "je dors mal", "j'ai pris du poids", "je suis épuisé") :
Pas de JSON. Identifie les domaines concernés (sommeil/activité/nutrition/risque), délègue à chaque
agent spécialisé concerné avec le contexte décrit, synthétise en plan d'action bienveillant.
ALERTE AUTOMATIQUE : si sévère (sommeil < 4h, épuisement extrême, symptômes critiques, risque
burn-out élevé), appelle send_report_and_alert avec {"global_score": <estimation 0-45>,
"health_level": "Critique", "synthesis": "...", "priority_action": "...", "weekly_plan": [],
"alerts": ["<symptôme critique>"], "prediction": ""} (même règle téléphone qu'au point 4), puis
confirme par texte.

QUESTION PAR DOMAINE : délègue à l'agent spécialisé concerné.
QUESTION GÉNÉRALE : réponds directement en 2-4 phrases.

RÈGLE ABSOLUE : tu dois TOUJOURS terminer chaque tour par un message texte destiné à l'utilisateur,
jamais uniquement un appel d'outil.""",
    tools=[
        # Analyse groupée — 1 seul appel Python remplace 4 AgentTool + get_memory_context
        analyze_health_data,
        save_session,
        send_report_and_alert,
        get_weekly_summary,
        # Agents spécialisés pour les questions conversationnelles
        AgentTool(agent=activity_agent),
        AgentTool(agent=sleep_agent),
        AgentTool(agent=nutrition_agent),
        AgentTool(agent=risk_agent),
        # Agents d'action
        AgentTool(agent=alert_agent),
        AgentTool(agent=report_agent),
        AgentTool(agent=weekly_coach_agent),
        # Mémoire utilisateur
        get_context,
        save_profile,
        save_user_note,
    ],
    before_agent_callback=_init_user_session,
    before_tool_callback=_log_tool_start,
    after_tool_callback=_log_tool_end,
    after_model_callback=log_model_response,
)

root_agent = chief_agent
