"""
LifeAI — Risk Agent
Évalue le risque de fatigue, burn-out et surentraînement en croisant tous les signaux.
"""

import numpy as np
from .base_agent import BaseAgent, AgentReport


class RiskAgent(BaseAgent):
    """
    Évalue les risques de santé en analysant les patterns multi-domaines.

    Données attendues dans user_data (résumé cross-agent) :
      - activity.steps_7d         : tendance activité
      - sleep.sleep_7d            : tendance sommeil
      - sleep.duration_hours      : sommeil récent
      - nutrition.calories_today  : apport calorique
      - nutrition.calories_goal   : objectif
      - risk.stress_level         : auto-évaluation stress (0-10)
      - risk.resting_hr           : fréquence cardiaque au repos
      - risk.resting_hr_baseline  : FC repos habituelle
      - risk.hrv                  : variabilité cardiaque (HRV, ms)
      - risk.hrv_baseline         : HRV habituelle
    """

    def __init__(self, verbose: bool = False, llm_insights: bool = False):
        super().__init__("RiskAgent", verbose, llm_insights)

    def _burnout_risk(self, activity_trend: float, sleep_avg: float,
                      sleep_var: float, stress: float, cal_deficit: float,
                      steps_avg: float, rhr_increase: float) -> tuple[float, str]:
        """Score de risque burn-out / fatigue (0 = aucun risque, 100 = risque maximal)."""
        risk = 0.0
        factors = []

        # Sédentarité absolue
        if steps_avg < 5000:
            r = min(25, (5000 - steps_avg) / 140)
            risk += r
            factors.append(f"sédentarité (moy. {steps_avg:.0f} pas/j)")

        # Baisse d'activité progressive
        if activity_trend < -0.2:
            r = min(20, abs(activity_trend) * 50)
            risk += r
            factors.append(f"baisse activité {activity_trend*100:.0f}%")

        # Sommeil insuffisant en moyenne
        if sleep_avg < 6.5:
            risk += min(35, (6.5 - sleep_avg) * 16)
            factors.append(f"sommeil moyen {sleep_avg:.1f}h")

        # Irrégularité du sommeil
        if sleep_var > 1.0:
            risk += min(10, sleep_var * 5)
            factors.append(f"sommeil irrégulier (σ={sleep_var:.1f}h)")

        # FC repos élevée = signe de fatigue accumulée
        if rhr_increase > 0.10:
            risk += min(20, rhr_increase * 40)
            factors.append(f"FC repos +{rhr_increase*100:.0f}%")

        # Stress déclaré
        if stress > 6:
            risk += (stress - 5) * 5
            factors.append(f"stress élevé ({stress}/10)")

        # Déficit ou surplus calorique marqué
        if cal_deficit < -0.25:
            risk += min(15, abs(cal_deficit) * 20)
            factors.append(f"déficit calorique {cal_deficit*100:.0f}%")
        elif cal_deficit > 0.30:
            risk += min(10, cal_deficit * 15)
            factors.append(f"surplus calorique +{cal_deficit*100:.0f}%")

        risk = min(100, risk)
        level = (
            "critique" if risk > 70
            else "élevé"  if risk > 45
            else "modéré" if risk > 25
            else "faible"
        )
        return risk, level, factors

    def _overtraining_risk(self, workouts_week: int, active_min: int,
                           hrv_drop: float) -> tuple[float, str]:
        """Score de risque surentraînement (0-100) : charge d'entraînement + récupération HRV."""
        risk = 0.0
        if workouts_week > 6:
            risk += (workouts_week - 6) * 10
        if active_min > 120:
            risk += (active_min - 120) / 10
        if hrv_drop > 0.15:   # >15% de baisse HRV vs baseline
            risk += hrv_drop * 80
        risk = min(100, risk)
        level = "élevé" if risk > 60 else "modéré" if risk > 35 else "faible"
        return risk, level

    def analyze(self, user_data: dict) -> AgentReport:
        activity  = user_data.get("activity",  {})
        sleep_d   = user_data.get("sleep",     {})
        nutrition = user_data.get("nutrition", {})
        risk_d    = user_data.get("risk",      {})

        # Données activity
        steps_7d    = activity.get("steps_7d", [])
        if isinstance(steps_7d, (int, float)):
            steps_7d = [steps_7d]
        workouts    = activity.get("workouts_this_week", 0)
        active_min  = activity.get("active_minutes", 30)

        # Données sleep
        sleep_7d    = sleep_d.get("sleep_7d", [7.0])
        if isinstance(sleep_7d, (int, float)):
            sleep_7d = [sleep_7d]
        duration    = sleep_d.get("duration_hours", 7.0)

        # Données nutrition
        cal_today   = nutrition.get("calories_today", 2000)
        cal_goal    = nutrition.get("calories_goal", 2000)

        # Données risque
        stress      = risk_d.get("stress_level", 5)
        rhr         = risk_d.get("resting_hr", 60)
        rhr_base    = risk_d.get("resting_hr_baseline", 60)
        hrv         = risk_d.get("hrv", 50)
        hrv_base    = risk_d.get("hrv_baseline", 50)

        # ── Calculs ────────────────────────────────────────────────────────
        # Tendance activité (delta % sur 7j)
        if len(steps_7d) >= 4:
            half = len(steps_7d) // 2
            old_avg = np.mean(steps_7d[:half]) or 1
            new_avg = np.mean(steps_7d[half:]) or 0
            activity_trend = (new_avg - old_avg) / old_avg
        else:
            activity_trend = 0.0

        steps_avg = float(np.mean(steps_7d)) if steps_7d else float(activity.get("steps_today", 5000))
        sleep_avg = float(np.mean(sleep_7d)) if sleep_7d else duration
        sleep_var = float(np.std(sleep_7d))  if len(sleep_7d) > 1 else 0.0
        cal_deficit = (cal_today - cal_goal) / cal_goal if cal_goal > 0 else 0.0

        hrv_drop     = (hrv_base - hrv) / hrv_base if hrv_base > 0 else 0.0
        rhr_increase = (rhr - rhr_base) / rhr_base if rhr_base > 0 else 0.0

        burnout_risk, burnout_level, burnout_factors = self._burnout_risk(
            activity_trend, sleep_avg, sleep_var, stress, cal_deficit, steps_avg, rhr_increase
        )
        over_risk, over_level = self._overtraining_risk(
            workouts, active_min, hrv_drop
        )

        # ── Pénalité nutrition (cross-domain) ─────────────────────────────
        nutrition_score = user_data.get("_nutrition_score")
        nutrition_penalty = 0.0
        if nutrition_score is not None:
            if nutrition_score < 30:
                nutrition_penalty = 20.0
                burnout_factors.append(f"nutrition très insuffisante ({nutrition_score:.0f}/100)")
            elif nutrition_score < 50:
                nutrition_penalty = 10.0
                burnout_factors.append(f"nutrition insuffisante ({nutrition_score:.0f}/100)")
            elif nutrition_score < 65:
                nutrition_penalty = 5.0

        # ── Score global de santé/risque (inversé : 100 = aucun risque) ──
        risk_composite = burnout_risk * 0.7 + over_risk * 0.3 + nutrition_penalty
        score = max(0, 100 - risk_composite)

        # ── Simulation prédictive 3 mois ──────────────────────────────────
        prediction = self._predict_3months(burnout_risk, sleep_avg, activity_trend, stress)

        # ── Anomalies ─────────────────────────────────────────────────────
        anomalies = []
        if burnout_level in ("élevé", "critique"):
            anomalies.append(f"⚠ Risque burn-out {burnout_level} ({burnout_risk:.0f}/100) — facteurs: {', '.join(burnout_factors)}")
        if over_level == "élevé":
            anomalies.append(f"⚠ Risque surentraînement {over_level} ({over_risk:.0f}/100)")
        if hrv_drop > 0.20:
            anomalies.append(f"HRV en baisse de {hrv_drop*100:.0f}% vs baseline → récupération insuffisante")
        if rhr_increase > 0.10:
            anomalies.append(f"FC repos +{rhr_increase*100:.0f}% vs baseline → signe de fatigue accumulée")

        # ── Insights ──────────────────────────────────────────────────────
        insights = [
            f"Risque burn-out : {burnout_level} ({burnout_risk:.0f}/100)",
            f"Risque surentraînement : {over_level} ({over_risk:.0f}/100)",
            f"Tendance activité 7j : {'+' if activity_trend >= 0 else ''}{activity_trend*100:.1f}%",
            f"Moyenne sommeil 7j : {sleep_avg:.1f}h (σ = {sleep_var:.1f}h)",
        ]
        if hrv_base > 0:
            insights.append(f"HRV : {hrv:.0f}ms (baseline : {hrv_base:.0f}ms, delta : {hrv_drop*100:+.0f}%)")
        insights.append(f"Prédiction 3 mois : {prediction}")

        # ── Recommandations ───────────────────────────────────────────────
        recs = []
        if burnout_risk > 45:
            recs.append("Intègre au moins 1 jour de repos complet (sans exercice ni stimulation intense) par semaine")
            recs.append("Pratique 10 min de cohérence cardiaque ou méditation quotidienne pour réguler le stress")
        if sleep_avg < 7.0:
            recs.append(f"Priorité récupération : vise {7.5 - sleep_avg:.1f}h de sommeil supplémentaire par nuit")
        if stress > 7:
            recs.append("Niveau de stress déclaré > 7/10 — considère une consultation avec un professionnel de santé")
        if hrv_drop > 0.15:
            recs.append("HRV basse → réduis l'intensité des entraînements cette semaine, priorise la récupération")
        if burnout_risk < 25 and over_risk < 25:
            recs.append("Excellent équilibre charge/récupération — maintiens ce rythme !")

        key_metrics = {
            "Risque burn-out":        f"{burnout_level} ({burnout_risk:.0f}/100)",
            "Risque surentraîn.":     f"{over_level} ({over_risk:.0f}/100)",
            "Stress déclaré":         f"{stress}/10",
            "FC repos":               f"{rhr} bpm (base: {rhr_base})",
            "HRV":                    f"{hrv:.0f} ms (base: {hrv_base:.0f})",
            "Tendance activité":      f"{activity_trend*100:+.1f}%",
            "Moyenne sommeil 7j":     f"{sleep_avg:.1f}h",
        }
        llm = self._llm_enrich("prévention burn-out et gestion du stress", key_metrics, anomalies)
        if llm:
            recs     = llm.get("recommendations", recs)
            insights = llm.get("insights", insights)

        return self._make_report(
            score=score,
            key_metrics=key_metrics,
            insights=insights,
            recommendations=recs,
            anomalies=anomalies,
            raw_data={**risk_d, "_computed": {
                "activity_trend": activity_trend,
                "sleep_avg": sleep_avg,
                "burnout_risk": burnout_risk,
            }},
        )

    def _predict_3months(self, burnout_risk: float, sleep_avg: float,
                          activity_trend: float, stress: float) -> str:
        """Génère une prédiction narrative pour les 3 prochains mois."""
        if burnout_risk > 60:
            return "⚠ Si le rythme actuel est maintenu → forte probabilité d'épisode de fatigue chronique"
        elif burnout_risk > 35:
            if activity_trend < -0.1:
                return "Baisse progressive d'énergie attendue → réajustement de charge recommandé maintenant"
            return "Risque modéré → des ajustements mineurs suffisent à stabiliser l'état de santé"
        elif sleep_avg >= 7.5 and activity_trend >= 0:
            return "✓ Trajectoire positive → amélioration des performances et de l'énergie probable"
        return "✓ Situation stable → maintien du niveau de santé actuel"
