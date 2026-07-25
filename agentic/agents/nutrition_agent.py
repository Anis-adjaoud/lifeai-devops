"""
LifeAI — Nutrition Agent
Analyse les apports nutritionnels : calories, macros, hydratation, régularité des repas.
"""

from datetime import datetime

from .base_agent import BaseAgent, AgentReport


class NutritionAgent(BaseAgent):
    """
    Analyse les données nutritionnelles.

    Données attendues dans user_data['nutrition']:
      - calories_today    : int   — kcal ingérées aujourd'hui
      - calories_goal     : int   — objectif calorique personnalisé
      - protein_g         : float — protéines (g)
      - carbs_g           : float — glucides (g)
      - fat_g             : float — lipides (g)
      - fiber_g           : float — fibres (g) — idéal 25-35g
      - water_ml          : int   — hydratation (ml) — idéal 2000ml
      - meals_count       : int   — nombre de repas dans la journée
      - processed_food_pct: float — % de l'alimentation ultra-transformée (0-100)
    """

    WATER_GOAL      = 2000   # ml
    FIBER_MIN       = 25     # g
    MEALS_OPT_MIN   = 3
    PROCESSED_MAX   = 20     # %

    def __init__(self, verbose: bool = False, llm_insights: bool = False):
        super().__init__("NutritionAgent", verbose, llm_insights)

    def _macro_score(self, protein_g: float, carbs_g: float, fat_g: float, total_cal: int) -> float:
        """Score de la répartition macronutriments (objectif : 30P / 40C / 30F)."""
        if total_cal <= 0:
            return 50.0
        p_pct = (protein_g * 4 / total_cal) * 100
        c_pct = (carbs_g  * 4 / total_cal) * 100
        f_pct = (fat_g    * 9 / total_cal) * 100

        # Pénalité quadratique par rapport aux cibles
        score = 100
        score -= min(40, (p_pct - 30) ** 2 * 0.3)
        score -= min(30, (c_pct - 40) ** 2 * 0.15)
        score -= min(30, (f_pct - 30) ** 2 * 0.2)
        return max(0, score)

    PROTEIN_CHRONIC_THRESHOLD = 50   # g/jour
    PROTEIN_CHRONIC_MIN_JOURS = 5    # jours de journal minimum pour juger une tendance

    def _anomalie_proteines_chroniques(self, historique: list) -> str | None:
        """Détecte un apport protéique chroniquement bas sur l'historique du journal
        (14 derniers jours, hors aujourd'hui). None si pas assez de jours loggés."""
        jours_avec_donnees = [j for j in (historique or []) if j.get("entries")]
        if len(jours_avec_donnees) < self.PROTEIN_CHRONIC_MIN_JOURS:
            return None

        proteines = [float(j.get("protein_g") or 0) for j in jours_avec_donnees]
        moyenne = sum(proteines) / len(proteines)
        jours_bas = sum(1 for p in proteines if p < self.PROTEIN_CHRONIC_THRESHOLD)

        # Majorité des jours loggés sous le seuil (pas juste la moyenne)
        if jours_bas / len(proteines) >= 0.7:
            return (
                f"Apport protéique chroniquement bas : moyenne {moyenne:.0f}g/jour sur "
                f"{len(proteines)} jours loggés (objectif ≥ {self.PROTEIN_CHRONIC_THRESHOLD}g) — "
                "risque de fonte musculaire installé, pas un simple mauvais jour"
            )
        return None

    def analyze(self, user_data: dict) -> AgentReport:
        data = user_data.get("nutrition", {})
        anomalie_chronique = self._anomalie_proteines_chroniques(data.get("_historique_14j"))

        if data.get("_no_data"):
            # Pas de données du jour, mais l'historique peut révéler une carence chronique
            return AgentReport(
                agent_name=self.name,
                timestamp=datetime.now().isoformat(),
                score=None,
                status="no_data",
                key_metrics={},
                insights=["Aucune donnée nutritionnelle aujourd'hui — journal alimentaire vide et profil non renseigné."],
                recommendations=["Ajoute tes repas dans le journal alimentaire pour un score nutrition fiable."],
                anomalies=[anomalie_chronique] if anomalie_chronique else [],
                raw_data=data,
            )

        cal_today    = data.get("calories_today", 2000)
        cal_goal     = data.get("calories_goal", 2000)
        protein_g    = data.get("protein_g", 80)
        carbs_g      = data.get("carbs_g", 200)
        fat_g        = data.get("fat_g", 70)
        fiber_g      = data.get("fiber_g", 20)
        water_ml     = data.get("water_ml", 1500)
        meals_count  = data.get("meals_count", 3)
        processed    = data.get("processed_food_pct", 15)

        # ── Score ─────────────────────────────────────────────────────────
        cal_ratio  = cal_today / cal_goal if cal_goal > 0 else 1.0
        # Courbe en cloche : 90-110% = parfait, 70-130% = ok
        if 0.9 <= cal_ratio <= 1.1:
            s_cal = 100
        elif 0.7 <= cal_ratio <= 1.3:
            s_cal = 70 + (1 - abs(cal_ratio - 1.0) / 0.3) * 30
        else:
            s_cal = max(0, 50 - abs(cal_ratio - 1.0) * 50)

        s_macro    = self._macro_score(protein_g, carbs_g, fat_g, cal_today)
        s_water    = min(water_ml / self.WATER_GOAL, 1.0) * 100
        s_fiber    = min(fiber_g  / self.FIBER_MIN,  1.0) * 100
        s_meals    = 100 if meals_count >= self.MEALS_OPT_MIN else meals_count / self.MEALS_OPT_MIN * 80
        s_proc     = max(0, 100 - processed * 2)

        score = (
            s_cal   * 0.25 +
            s_macro * 0.25 +
            s_water * 0.20 +
            s_fiber * 0.15 +
            s_meals * 0.10 +
            s_proc  * 0.05
        )

        # ── Anomalies ─────────────────────────────────────────────────────
        # Même garde que pour cal_ratio plus haut : un profil dont l'objectif
        # calorique vaut 0 (modifiable via PUT /api/profile) faisait planter
        # l'analyse sur une division par zéro.
        pct_objectif = (cal_today / cal_goal * 100) if cal_goal > 0 else 0.0

        anomalies = []
        if cal_today < cal_goal * 0.6:
            anomalies.append(
                f"Apport calorique très bas : {cal_today} kcal ({pct_objectif:.0f}% de l'objectif)"
            )
        if cal_today > cal_goal * 1.4:
            surplus = cal_today - cal_goal
            anomalies.append(f"Surplus calorique important : +{surplus} kcal au-dessus de l'objectif")
        if water_ml < 1200:
            anomalies.append(f"Hydratation insuffisante : {water_ml} ml (minimum recommandé : 1500 ml)")
        if protein_g < 50:
            anomalies.append(f"Apport protéique très faible : {protein_g:.0f}g (risque de catabolisme musculaire)")
        if anomalie_chronique:
            anomalies.append(anomalie_chronique)
        if processed > 40:
            anomalies.append(f"Alimentation ultra-transformée : {processed:.0f}% — impact négatif sur le microbiote")

        # ── Macros répartition ────────────────────────────────────────────
        total_macro_cal = protein_g * 4 + carbs_g * 4 + fat_g * 9
        if total_macro_cal > 0:
            p_pct = protein_g * 4 / total_macro_cal * 100
            c_pct = carbs_g   * 4 / total_macro_cal * 100
            f_pct = fat_g     * 9 / total_macro_cal * 100
            macro_str = f"P:{p_pct:.0f}% / G:{c_pct:.0f}% / L:{f_pct:.0f}%"
        else:
            macro_str = "N/A"

        # ── Insights ──────────────────────────────────────────────────────
        insights = [
            f"Calories : {cal_today} kcal / {cal_goal} kcal ({pct_objectif:.0f}%)",
            f"Répartition macros : {macro_str} (cible : P:30% / G:40% / L:30%)",
            f"Hydratation : {water_ml} ml / {self.WATER_GOAL} ml",
            f"Fibres : {fiber_g:.0f}g (objectif ≥ {self.FIBER_MIN}g)",
        ]

        # ── Recommandations ───────────────────────────────────────────────
        recs = []
        if water_ml < self.WATER_GOAL:
            remaining_water = self.WATER_GOAL - water_ml
            recs.append(f"Bois encore {remaining_water} ml d'eau aujourd'hui ({remaining_water // 250} verres)")
        if protein_g < 60:
            recs.append("Ajoute une source de protéines à ton prochain repas (œufs, légumineuses, poulet, tofu)")
        if fiber_g < self.FIBER_MIN:
            recs.append("Augmente les fibres : +1 portion de légumes ou légumineuses suffit")
        if processed > self.PROCESSED_MAX:
            recs.append("Remplace un aliment ultra-transformé par un équivalent non-transformé")
        if meals_count < 2:
            recs.append("Sauter des repas perturbe la glycémie — essaie au moins 3 repas structurés")
        if not recs:
            recs.append("Alimentation équilibrée aujourd'hui — bel effort !")

        key_metrics = {
            "Calories":             f"{cal_today} / {cal_goal} kcal",
            "Protéines":            f"{protein_g:.0f}g",
            "Glucides":             f"{carbs_g:.0f}g",
            "Lipides":              f"{fat_g:.0f}g",
            "Fibres":               f"{fiber_g:.0f}g",
            "Hydratation":          f"{water_ml} ml",
            "Repas":                meals_count,
            "Alim. transformée":    f"{processed:.0f}%",
        }
        llm = self._llm_enrich("nutrition et alimentation", key_metrics, anomalies)
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
