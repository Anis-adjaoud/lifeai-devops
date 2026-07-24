"""
LifeAI — Activity Agent
Analyse l'activité physique : pas, sport, intensité, sédentarité.
Détecte les anomalies (baisse soudaine) et produit des recommandations.
"""

import numpy as np
from .base_agent import BaseAgent, AgentReport


class ActivityAgent(BaseAgent):
    """
    Analyse les données d'activité physique.

    Données attendues dans user_data['activity']:
      - steps_today        : int   — pas du jour
      - steps_7d           : list  — pas des 7 derniers jours
      - active_minutes     : int   — minutes d'activité modérée/intense aujourd'hui
      - workouts_this_week : int   — séances de sport cette semaine
      - sedentary_hours    : float — heures sédentaires aujourd'hui
      - calories_burned    : int   — calories dépensées
    """

    # Seuils OMS & guidelines santé
    STEPS_GOAL         = 10_000
    ACTIVE_MIN_GOAL    = 30      # minutes / jour
    WORKOUTS_WEEK_GOAL = 3
    SEDENTARY_MAX      = 8       # heures

    def __init__(self, verbose: bool = False, llm_insights: bool = False):
        super().__init__("ActivityAgent", verbose, llm_insights)

    def analyze(self, user_data: dict) -> AgentReport:
        data = user_data.get("activity", {})

        steps_today    = data.get("steps_today", 0)
        steps_7d       = data.get("steps_7d", [steps_today])
        if isinstance(steps_7d, (int, float)):
            steps_7d = [steps_7d]
        active_min     = data.get("active_minutes", 0)
        workouts       = data.get("workouts_this_week", 0)
        sedentary_h    = data.get("sedentary_hours", 10)
        calories       = data.get("calories_burned", 0)

        # ── Calcul du score (0-100) ────────────────────────────────────────
        s_steps    = min(steps_today / self.STEPS_GOAL, 1.0) * 100
        s_active   = min(active_min / self.ACTIVE_MIN_GOAL, 1.0) * 100
        s_workouts = min(workouts / self.WORKOUTS_WEEK_GOAL, 1.0) * 100
        s_sedent   = max(0, 1 - (sedentary_h - 6) / (self.SEDENTARY_MAX - 6)) * 100
        s_sedent   = max(0, min(100, s_sedent))

        score = (s_steps * 0.35 + s_active * 0.25 + s_workouts * 0.25 + s_sedent * 0.15)

        # ── Détection d'anomalies ─────────────────────────────────────────
        anomalies = []
        if len(steps_7d) >= 3:
            avg_7d = np.mean(steps_7d[:-1]) if len(steps_7d) > 1 else steps_today
            if avg_7d > 0 and (steps_today / avg_7d) < 0.6:
                drop_pct = (1 - steps_today / avg_7d) * 100
                anomalies.append(
                    f"Baisse d'activité de {drop_pct:.0f}% vs. moyenne 7j ({avg_7d:.0f} pas → {steps_today} pas)"
                )

        if sedentary_h > 10:
            anomalies.append(f"Temps sédentaire très élevé : {sedentary_h:.1f}h (max recommandé : 8h)")

        if workouts == 0 and len(steps_7d) >= 5:
            anomalies.append("Aucune séance de sport cette semaine")

        # ── Insights ──────────────────────────────────────────────────────
        insights = []
        pct_steps = (steps_today / self.STEPS_GOAL) * 100
        insights.append(f"Pas aujourd'hui : {steps_today:,} ({pct_steps:.0f}% de l'objectif {self.STEPS_GOAL:,})")
        insights.append(f"Minutes actives : {active_min} min ({active_min / self.ACTIVE_MIN_GOAL * 100:.0f}% de l'objectif)")

        if len(steps_7d) > 1:
            weekly_avg = np.mean(steps_7d)
            insights.append(f"Moyenne hebdomadaire : {weekly_avg:,.0f} pas/jour")

        # ── Recommandations ───────────────────────────────────────────────
        recs = []
        if steps_today < self.STEPS_GOAL * 0.7:
            remaining = self.STEPS_GOAL - steps_today
            recs.append(f"Il te reste {remaining:,} pas pour atteindre ton objectif — une marche de 20 min suffit")
        if active_min < self.ACTIVE_MIN_GOAL:
            recs.append(f"Ajoute {self.ACTIVE_MIN_GOAL - active_min} min d'activité modérée (vélo, natation, marche rapide)")
        if workouts < self.WORKOUTS_WEEK_GOAL:
            recs.append(f"Planifie {self.WORKOUTS_WEEK_GOAL - workouts} séance(s) de sport supplémentaire(s) cette semaine")
        if sedentary_h > self.SEDENTARY_MAX:
            recs.append("Pause debout/marche de 5 min toutes les heures pour casser la sédentarité")
        if not recs:
            recs.append("Excellent niveau d'activité — maintiens ce rythme !")

        key_metrics = {
            "Pas aujourd'hui":        f"{steps_today:,}",
            "Objectif pas":           f"{self.STEPS_GOAL:,}",
            "Minutes actives":        f"{active_min} min",
            "Séances/semaine":        workouts,
            "Heures sédentaires":     f"{sedentary_h:.1f}h",
            "Calories dépensées":     calories,
        }
        llm = self._llm_enrich("activité physique et sédentarité", key_metrics, anomalies)
        if llm:
            recs     = llm.get("recommendations", recs)
            insights = llm.get("insights", insights)

        return self._make_report(
            score=score,
            key_metrics=key_metrics,
            insights=insights,
            recommendations=recs,
            anomalies=anomalies,
            raw_data=data,
        )
