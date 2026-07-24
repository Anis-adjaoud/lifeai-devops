"""
LifeAI — Sleep Agent
Analyse la qualité du sommeil : durée, efficacité, cycles, régularité.
"""

import numpy as np
from .base_agent import BaseAgent, AgentReport


class SleepAgent(BaseAgent):
    """
    Analyse les données de sommeil.

    Données attendues dans user_data['sleep']:
      - duration_hours    : float — durée de sommeil cette nuit
      - sleep_7d          : list  — durées des 7 dernières nuits
      - efficiency_pct    : float — % temps au lit passé à dormir (0-100)
      - deep_sleep_pct    : float — % sommeil profond (idéal : 15-25%)
      - rem_pct           : float — % sommeil REM (idéal : 20-25%)
      - awakenings        : int   — nombre de réveils nocturnes
      - bedtime_regularity: float — écart-type heure de coucher en minutes (idéal < 30)
    """

    DURATION_MIN  = 7.0   # heures minimum
    DURATION_OPT  = 8.0   # heures optimales
    EFFICIENCY_OK = 85    # % minimum
    DEEP_MIN, DEEP_MAX = 15, 25
    REM_MIN,  REM_MAX  = 20, 25
    AWAKENINGS_MAX = 2

    def __init__(self, verbose: bool = False, llm_insights: bool = False):
        super().__init__("SleepAgent", verbose, llm_insights)

    def analyze(self, user_data: dict) -> AgentReport:
        data = user_data.get("sleep", {})

        duration    = data.get("duration_hours", 7.0)
        sleep_7d    = data.get("sleep_7d", [duration])
        if isinstance(sleep_7d, (int, float)):
            sleep_7d = [sleep_7d]
        efficiency  = data.get("efficiency_pct", 85.0)
        deep_pct    = data.get("deep_sleep_pct", 20.0)
        rem_pct     = data.get("rem_pct", 22.0)
        awakenings  = data.get("awakenings", 1)
        regularity  = data.get("bedtime_regularity", 25.0)  # écart-type minutes

        # ── Score ─────────────────────────────────────────────────────────
        # Durée : courbe en cloche centrée sur 8h
        if duration < self.DURATION_MIN:
            s_duration = (duration / self.DURATION_MIN) * 65
        elif duration <= self.DURATION_OPT:
            s_duration = 65 + (duration - self.DURATION_MIN) / (self.DURATION_OPT - self.DURATION_MIN) * 35
        else:
            # Légère pénalité au-delà de 9.5h (oversleeping)
            excess = max(0, duration - 9.5)
            s_duration = max(70, 100 - excess * 10)

        s_efficiency = min(efficiency / self.EFFICIENCY_OK, 1.0) * 100
        s_deep       = 100 if self.DEEP_MIN <= deep_pct <= self.DEEP_MAX else \
                       max(0, 100 - abs(deep_pct - 20) * 5)
        s_rem        = 100 if self.REM_MIN <= rem_pct <= self.REM_MAX else \
                       max(0, 100 - abs(rem_pct - 22) * 5)
        s_awakenings = max(0, 100 - awakenings * 20)
        s_regularity = max(0, 100 - max(0, regularity - 15) * 2)

        score = (
            s_duration   * 0.30 +
            s_efficiency * 0.20 +
            s_deep       * 0.20 +
            s_rem        * 0.15 +
            s_awakenings * 0.10 +
            s_regularity * 0.05
        )

        # ── Anomalies ─────────────────────────────────────────────────────
        anomalies = []
        if duration < 6.0:
            anomalies.append(f"Durée de sommeil critique : {duration:.1f}h (minimum recommandé : {self.DURATION_MIN}h)")

        if len(sleep_7d) >= 3:
            avg_7d = np.mean(sleep_7d[:-1])
            if avg_7d > 0 and abs(duration - avg_7d) > 1.5:
                diff = duration - avg_7d
                direction = "de moins" if diff < 0 else "de plus"
                anomalies.append(
                    f"Variation atypique : {abs(diff):.1f}h {direction} que ta moyenne habituelle ({avg_7d:.1f}h)"
                )

        if efficiency < 75:
            anomalies.append(f"Efficacité du sommeil faible : {efficiency:.0f}% (objectif ≥ {self.EFFICIENCY_OK}%)")

        if awakenings > 4:
            anomalies.append(f"Sommeil très fragmenté : {awakenings} réveils nocturnes")

        # ── Insights ──────────────────────────────────────────────────────
        insights = []
        insights.append(f"Durée cette nuit : {duration:.1f}h (objectif : {self.DURATION_OPT}h)")
        if len(sleep_7d) > 1:
            insights.append(f"Moyenne 7j : {np.mean(sleep_7d):.1f}h/nuit")

        # Corrélation sommeil-performance (feature LifeAI)
        if duration < self.DURATION_MIN:
            deficit = self.DURATION_MIN - duration
            perf_impact = deficit * 15  # ~15% de baisse par heure manquante
            insights.append(
                f"Déficit de {deficit:.1f}h → impact estimé de -{perf_impact:.0f}% sur les performances cognitives"
            )

        insights.append(f"Sommeil profond : {deep_pct:.0f}% | REM : {rem_pct:.0f}% | Réveils : {awakenings}")

        if regularity > 45:
            insights.append(f"Horaires de coucher irréguliers (σ = {regularity:.0f} min) — nuit le rythme circadien")

        # ── Recommandations ───────────────────────────────────────────────
        recs = []
        if duration < self.DURATION_MIN:
            recs.append(f"Couche-toi {(self.DURATION_MIN - duration) * 60:.0f} min plus tôt ce soir pour récupérer")
        if deep_pct < self.DEEP_MIN:
            recs.append("Augmente l'activité physique dans la journée pour favoriser le sommeil profond")
        if rem_pct < self.REM_MIN:
            recs.append("Évite l'alcool et les écrans 1h avant de dormir pour préserver le sommeil REM")
        if efficiency < self.EFFICIENCY_OK:
            recs.append("Lève-toi si tu n'arrives pas à dormir après 20 min — ne reste pas au lit éveillé")
        if regularity > 30:
            recs.append(f"Fixe une heure de coucher régulière (±15 min) pour stabiliser ton rythme circadien")
        if awakenings > self.AWAKENINGS_MAX:
            recs.append("Vérifie température de chambre (idéal 16-19°C) et limite la caféine après 14h")
        if not recs:
            recs.append("Excellente qualité de sommeil — continue ce rythme !")

        key_metrics = {
            "Durée cette nuit":   f"{duration:.1f}h",
            "Efficacité":         f"{efficiency:.0f}%",
            "Sommeil profond":    f"{deep_pct:.0f}%",
            "Sommeil REM":        f"{rem_pct:.0f}%",
            "Réveils nocturnes":  awakenings,
            "Régularité (σ)":     f"{regularity:.0f} min",
        }
        llm = self._llm_enrich("sommeil et récupération", key_metrics, anomalies)
        if llm:
            recs    = llm.get("recommendations", recs)
            insights = llm.get("insights", insights)

        return self._make_report(
            score=score,
            key_metrics=key_metrics,
            insights=insights,
            recommendations=recs,
            anomalies=anomalies,
            raw_data=data,
        )
