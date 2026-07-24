"""
LifeAI — ML Agent
Prédit 3 risques à J+7 (sédentarité, dette de sommeil, baisse d'activité intense) à
partir des modèles XGBoost entraînés sur LifeSnaps (train_models/lifesnaps_ml.ipynb).
Contrairement à RiskAgent (règles écrites à la main), cet agent délègue le
scoring à des modèles appris sur données réelles.
"""

from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from .base_agent import BaseAgent, AgentReport

MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "models"

FEATURE_COLUMNS = [
    "calories_roll7", "steps_roll7", "bpm_roll7", "resting_hr_roll7", "sedentary_minutes_roll7",
    "lightly_active_minutes_roll7", "moderately_active_minutes_roll7", "very_active_minutes_roll7",
    "minutesAsleep_roll7", "sleep_efficiency_roll7",
    "gender_encoded", "age", "bmi",
]

# Valeurs par defaut = profil "typique" LifeSnaps (feature non fournie par l'appelant)
DEFAULTS = {
    "calories_roll7": 2200, "steps_roll7": 7000, "bpm_roll7": 75, "resting_hr_roll7": 65,
    "sedentary_minutes_roll7": 600, "lightly_active_minutes_roll7": 150,
    "moderately_active_minutes_roll7": 20, "very_active_minutes_roll7": 15,
    "minutesAsleep_roll7": 400, "sleep_efficiency_roll7": 94,
    "gender_encoded": 0, "age": ">=30", "bmi": "23.0",
}

TARGETS = ["low_activity_risk", "sleep_debt_risk", "activity_decline_risk"]
TARGET_LABELS_FR = {
    "low_activity_risk": "sédentarité",
    "sleep_debt_risk": "dette de sommeil",
    "activity_decline_risk": "baisse d'activité intense",
}


@lru_cache(maxsize=1)
def _load_ml_models():
    """Charge le preprocessor + les 3 modèles XGBoost une seule fois par process."""
    preprocessor = joblib.load(MODEL_DIR / "preprocessor_lifesnaps.joblib")
    models = {
        target: joblib.load(MODEL_DIR / f"model_lifesnaps_{target}.joblib")
        for target in TARGETS
    }
    return preprocessor, models


class MLAgent(BaseAgent):
    """
    Predit 3 risques a J+7 via des modeles XGBoost entraines sur LifeSnaps
    (train_models/lifesnaps_ml.ipynb) : sedentarite, dette de sommeil, baisse
    d'activite intense. Chaque risque a son propre modele independant.

    Donnees attendues dans user_data['ml'] (moyennes sur les 7 derniers jours
    de l'utilisateur, toutes obtenables via Google Fit) :
      - calories_roll7, steps_roll7, bpm_roll7, resting_hr_roll7
      - sedentary_minutes_roll7, lightly_active_minutes_roll7,
        moderately_active_minutes_roll7, very_active_minutes_roll7
      - minutesAsleep_roll7, sleep_efficiency_roll7
      - gender_encoded (0/1), age, bmi (categories : ex '<30', '>=30', '23.0'...)

    Toute cle manquante retombe sur un profil "typique" (voir DEFAULTS).
    """

    # Seuils calibres par cible (medium = point F1-optimal, high = seuil strict)
    THRESHOLDS = {
        "low_activity_risk":     {"medium": 0.21, "high": 0.60},
        "sleep_debt_risk":       {"medium": 0.19, "high": 0.60},
        "activity_decline_risk": {"medium": 0.34, "high": 0.67},
    }

    def __init__(self, verbose: bool = False, llm_insights: bool = False):
        super().__init__("MLAgent", verbose, llm_insights)
        self._preprocessor, self._models = _load_ml_models()

    def _risk_level(self, target: str, proba: float) -> str:
        t = self.THRESHOLDS[target]
        if proba >= t["high"]:
            return "high"
        if proba >= t["medium"]:
            return "medium"
        return "low"

    def analyze(self, user_data: dict) -> AgentReport:
        data = user_data.get("ml", {})

        row = pd.DataFrame([{col: data.get(col, DEFAULTS[col]) for col in FEATURE_COLUMNS}])
        row_t = self._preprocessor.transform(row)

        risks = {}
        for target in TARGETS:
            proba = float(self._models[target].predict_proba(row_t)[0, 1])
            risks[target] = {"probability": round(proba, 4), "risk_level": self._risk_level(target, proba)}

        # ── Score global (100 = aucun risque, coherent avec RiskAgent) ────
        risk_composite = sum(r["probability"] for r in risks.values()) / len(risks)
        score = max(0.0, 100 - risk_composite * 100)

        # ── Anomalies ─────────────────────────────────────────────────────
        anomalies = []
        for target in TARGETS:
            if risks[target]["risk_level"] == "high":
                label = TARGET_LABELS_FR[target]
                anomalies.append(
                    f"Risque élevé de {label} à J+7 (probabilité {risks[target]['probability']:.0%})"
                )

        # ── Insights ──────────────────────────────────────────────────────
        insights = [
            f"Risque de sédentarité à J+7 : {risks['low_activity_risk']['probability']:.0%} ({risks['low_activity_risk']['risk_level']})",
            f"Risque de dette de sommeil à J+7 : {risks['sleep_debt_risk']['probability']:.0%} ({risks['sleep_debt_risk']['risk_level']})",
            f"Risque de baisse d'activité intense à J+7 : {risks['activity_decline_risk']['probability']:.0%} ({risks['activity_decline_risk']['risk_level']})",
        ]

        # ── Recommandations ───────────────────────────────────────────────
        recs = []
        if risks["low_activity_risk"]["risk_level"] != "low":
            recs.append("Vise au moins 5000 pas/jour cette semaine — une marche de 20-30 min suffit")
        if risks["sleep_debt_risk"]["risk_level"] != "low":
            recs.append("Priorise ton créneau de sommeil ces prochains jours — vise un coucher plus tôt et régulier")
        if risks["activity_decline_risk"]["risk_level"] != "low":
            recs.append("Maintiens tes séances d'intensité modérée à élevée cette semaine pour éviter de décrocher")
        if not recs:
            recs.append("Aucun signal de risque marquant pour les 7 prochains jours — maintiens ce rythme")

        key_metrics = {
            "Risque sédentarité (J+7)":              f"{risks['low_activity_risk']['probability']:.0%} ({risks['low_activity_risk']['risk_level']})",
            "Risque dette de sommeil (J+7)":          f"{risks['sleep_debt_risk']['probability']:.0%} ({risks['sleep_debt_risk']['risk_level']})",
            "Risque baisse d'activité intense (J+7)": f"{risks['activity_decline_risk']['probability']:.0%} ({risks['activity_decline_risk']['risk_level']})",
        }
        llm = self._llm_enrich("prévention de la sédentarité et de la fatigue (prédictions J+7)", key_metrics, anomalies)
        if llm:
            recs = llm.get("recommendations", recs)
            insights = llm.get("insights", insights)

        return self._make_report(
            score=score,
            key_metrics=key_metrics,
            insights=insights,
            recommendations=recs,
            anomalies=anomalies,
            raw_data={**data, "_risks": risks},
        )
