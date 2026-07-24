"""
LifeAI — Chief Agent (Orchestrateur LLM)
Synthétise les rapports des 4 agents spécialisés via Claude.
Produit un coaching personnalisé, tient compte de la mémoire long-terme.
"""

import json
from dataclasses import dataclass
from .base_agent import AgentReport
from .memory import LongTermMemory
from .llm_client import get_api_key


@dataclass
class ChiefReport:
    """Rapport final consolidé produit par le Chief Agent."""
    global_score: float
    scores: dict          # { agent_name: score }
    health_level: str     # "Excellent" | "Bon" | "Attention" | "Critique"
    synthesis: str        # Texte narratif LLM
    priority_action: str  # Action #1 à prendre immédiatement
    weekly_plan: list[str]
    alerts: list[str]
    prediction: str
    memory_context: str

    def to_dict(self) -> dict:
        return {
            "global_score": self.global_score,
            "scores": self.scores,
            "health_level": self.health_level,
            "synthesis": self.synthesis,
            "priority_action": self.priority_action,
            "weekly_plan": self.weekly_plan,
            "alerts": self.alerts,
            "prediction": self.prediction,
        }

    def display(self):
        """Affiche le rapport complet dans le terminal."""
        print("\n" + "═" * 70)
        print("  🏥  LIFEAI — RAPPORT SANTÉ COMPLET")
        print("═" * 70)

        # Score global
        bar_len = 40
        filled  = int(self.global_score / 100 * bar_len)
        bar     = "█" * filled + "░" * (bar_len - filled)
        print(f"\n  Score Global : {self.global_score:.1f}/100  [{bar}]  {self.health_level}")

        # Scores par domaine
        print("\n  ┌─ Scores par domaine ──────────────────────────────────┐")
        for agent, sc in self.scores.items():
            mini_filled = int(sc / 100 * 20)
            mini_bar    = "▓" * mini_filled + "░" * (20 - mini_filled)
            label       = agent.replace("Agent", "").strip().ljust(12)
            print(f"  │  {label}  [{mini_bar}]  {sc:5.1f}/100")
        print("  └───────────────────────────────────────────────────────┘")

        # Alertes
        if self.alerts:
            print("\n  ⚠  ALERTES ACTIVES")
            for a in self.alerts:
                print(f"     • {a}")

        # Action prioritaire
        print(f"\n  🎯  ACTION PRIORITAIRE\n     {self.priority_action}")

        # Synthèse LLM
        print(f"\n  🤖  ANALYSE IA\n")
        for line in self.synthesis.split("\n"):
            print(f"     {line}")

        # Plan semaine
        if self.weekly_plan:
            print(f"\n  📅  PLAN SEMAINE")
            for item in self.weekly_plan:
                print(f"     • {item}")

        # Prédiction
        print(f"\n  🔮  PRÉDICTION 3 MOIS\n     {self.prediction}")

        # Mémoire
        if self.memory_context:
            print(f"\n  💾  CONTEXTE MÉMOIRE\n     {self.memory_context}")

        print("\n" + "═" * 70 + "\n")


class ChiefAgent:
    """
    Orchestrateur principal.

    Reçoit les rapports des agents spécialisés → construit un prompt riche →
    appelle Claude via l'API Anthropic → produit un ChiefReport complet.
    """

    def __init__(self, memory: LongTermMemory = None, verbose: bool = False):
        self.memory  = memory or LongTermMemory()
        self.verbose = verbose
        self._client = None  # Lazy init

    def _get_client(self):
        """Initialise le client Groq une seule fois."""
        if self._client is None:
            try:
                from groq import Groq
                self._client = Groq(api_key=get_api_key())
            except Exception as e:
                raise RuntimeError(
                    f"Impossible d'initialiser le client Groq : {e}\n"
                    "Installe groq (pip install groq) et définis GROQ_API_KEY."
                )
        return self._client

    def _build_prompt(self, reports: dict[str, AgentReport], memory_ctx: dict) -> str:
        """Construit le prompt système + utilisateur pour le LLM."""
        # Résumés des agents
        agent_summaries = "\n\n".join(
            report.to_summary_text() for report in reports.values()
        )

        # Contexte mémoire
        mem_lines = []
        if memory_ctx.get("sessions_count", 0) > 0:
            mem_lines.append(f"Sessions analysées à ce jour : {memory_ctx['sessions_count']}")
        if memory_ctx.get("trend"):
            mem_lines.append(f"Tendance récente : {memory_ctx['trend']}")
        if memory_ctx.get("recurring_patterns"):
            patterns_str = "; ".join(
                f"{p['description']} (x{p['occurrences']})"
                for p in memory_ctx["recurring_patterns"]
            )
            mem_lines.append(f"Patterns récurrents détectés : {patterns_str}")
        if memory_ctx.get("goals"):
            mem_lines.append(f"Objectifs de l'utilisateur : {', '.join(memory_ctx['goals'])}")
        if memory_ctx.get("last_advice"):
            advice_str = " | ".join(memory_ctx["last_advice"][:2])
            mem_lines.append(f"Derniers conseils donnés : {advice_str}")

        memory_section = "\n".join(mem_lines) if mem_lines else "Première session — pas d'historique."

        # Scores pour référence rapide
        scores_str = " | ".join(
            f"{name.replace('Agent','').strip()}: {r.score:.0f}/100"
            for name, r in reports.items()
        )

        prompt = f"""Tu es LifeAI, un coach de santé IA expert et bienveillant.
Tu reçois les analyses détaillées de 4 agents spécialisés (Activité, Sommeil, Nutrition, Risque)
et tu dois produire une synthèse coaching personnalisée, actionnable et motivante.

══════════════════════════════════════════════════
SCORES RÉSUMÉS : {scores_str}
══════════════════════════════════════════════════

RAPPORTS DÉTAILLÉS DES AGENTS :

{agent_summaries}

══════════════════════════════════════════════════
MÉMOIRE LONG-TERME :

{memory_section}
══════════════════════════════════════════════════

INSTRUCTIONS :
Réponds en JSON valide avec exactement cette structure :
{{
  "synthesis": "Analyse narrative de 3-4 phrases : ce qui va bien, ce qui mérite attention, en quoi les données se recoupent. Ton direct, personnalisé, bienveillant.",
  "priority_action": "UNE seule action concrète à faire aujourd'hui ou cette semaine, la plus impactante.",
  "weekly_plan": ["Lundi: ...", "Mercredi: ...", "Vendredi: ...", "Week-end: ..."],
  "prediction": "Prédiction narrative sur 3 mois si le rythme actuel est maintenu.",
  "coaching_tone": "motivating|neutral|concerned"
}}

Règles :
- Sois précis et factuel (mentionne les vrais chiffres des rapports)
- Connecte les domaines entre eux (ex: sommeil → performance physique)
- Tiens compte de l'historique si disponible
- Réponds uniquement avec le JSON, sans markdown ni preamble
"""
        return prompt

    def synthesize(self, reports: dict[str, AgentReport]) -> ChiefReport:
        """
        Point d'entrée principal.
        Prend les rapports des agents spécialisés et retourne un ChiefReport.
        """
        if self.verbose:
            print("[ChiefAgent] Synthèse démarrée...")

        # Score global pondéré
        weights = {"ActivityAgent": 0.20, "SleepAgent": 0.25,
                   "NutritionAgent": 0.15, "RiskAgent": 0.20, "MLAgent": 0.20}
        scores = {name: r.score for name, r in reports.items()}
        global_score = sum(
            scores.get(name, 0) * w for name, w in weights.items()
        )

        # Niveau de santé
        health_level = (
            "Excellent" if global_score >= 80
            else "Bon"       if global_score >= 65
            else "Attention" if global_score >= 45
            else "Critique"
        )

        # Alertes critiques agrégées
        alerts = []
        for r in reports.values():
            alerts.extend(r.anomalies)

        # Contexte mémoire
        memory_ctx = self.memory.get_coaching_context()

        # ── Appel LLM ─────────────────────────────────────────────────────
        prompt = self._build_prompt(reports, memory_ctx)
        llm_data = self._call_llm(prompt)

        synthesis      = llm_data.get("synthesis", "Analyse non disponible.")
        priority_action= llm_data.get("priority_action", "Consulte tes recommandations détaillées.")
        weekly_plan    = llm_data.get("weekly_plan", [])
        prediction     = llm_data.get("prediction", "Données insuffisantes pour une prédiction.")

        # ── Mise à jour mémoire ───────────────────────────────────────────
        self.memory.add_session(scores=scores, global_score=global_score)
        if priority_action:
            self.memory.update_coaching_context(last_advice=[priority_action])

        # Patterns automatiques
        risk_report = reports.get("RiskAgent")
        if risk_report and risk_report.score < 50:
            self.memory.add_pattern("low_risk_score", "Score risque < 50 — signaux de fatigue répétés")
        sleep_report = reports.get("SleepAgent")
        if sleep_report and sleep_report.score < 55:
            self.memory.add_pattern("poor_sleep", "Qualité de sommeil insuffisante récurrente")

        memory_summary = self.memory.memory_summary()

        if self.verbose:
            print(f"[ChiefAgent] Score global: {global_score:.1f} | Niveau: {health_level}")

        return ChiefReport(
            global_score=round(global_score, 1),
            scores=scores,
            health_level=health_level,
            synthesis=synthesis,
            priority_action=priority_action,
            weekly_plan=weekly_plan,
            alerts=alerts,
            prediction=prediction,
            memory_context=memory_summary,
        )

    def _call_llm(self, prompt: str) -> dict:
        """Appelle l'API Groq et parse la réponse JSON."""
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content.strip()
            # Nettoie les éventuels blocs markdown
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            print(f"[ChiefAgent] ⚠ LLM indisponible ({e}) — fallback mode")
            return self._fallback_synthesis()

    def _fallback_synthesis(self) -> dict:
        """Réponse de secours si l'API LLM est indisponible."""
        return {
            "synthesis": (
                "Analyse multi-agents complétée. Consulte les scores et recommandations "
                "de chaque domaine pour une vue détaillée de ton état de santé. "
                "Le coaching IA complet nécessite une connexion à l'API."
            ),
            "priority_action": "Consulte les recommandations prioritaires de chaque agent.",
            "weekly_plan": [
                "Lundi: Activité physique modérée (30 min)",
                "Mercredi: Focus récupération + sommeil",
                "Vendredi: Bilan nutrition de la semaine",
                "Week-end: Repos actif — marche ou yoga",
            ],
            "prediction": "Prédiction disponible après 7+ sessions de données.",
            "coaching_tone": "neutral",
        }
