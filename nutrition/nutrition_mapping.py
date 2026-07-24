"""
LifeAI — Agrégat du journal alimentaire → contrat NutritionAgent.

Convertit le journal du jour (voir nutrition_store.get_diary) + hydratation +
objectif calorique en les 8 clés attendues par
agentic.agents.nutrition_agent.NutritionAgent :

    calories_today, calories_goal, protein_g, carbs_g, fat_g,
    fiber_g, water_ml, meals_count, processed_food_pct

Contrairement à la v1 qualitative, ce sont désormais de **vraies données agrégées**
(sommes des aliments réellement consommés). Fonction isolée/remplaçable.
"""

from __future__ import annotations


def diary_to_contract(diary: dict, water_ml: int, kcal_goal: int = 2000) -> dict:
    totals = diary["totals"]
    total_kcal = totals.get("kcal", 0) or 0
    processed_kcal = totals.get("processed_kcal", 0) or 0
    processed_pct = (processed_kcal / total_kcal * 100) if total_kcal > 0 else 0.0
    meals_count = sum(1 for m in diary["meals"].values() if m["entries"])

    return {
        "calories_today":     round(total_kcal),
        "calories_goal":      int(kcal_goal or 2000),
        "protein_g":          round(totals.get("protein_g", 0) or 0, 1),
        "carbs_g":            round(totals.get("carbs_g", 0) or 0, 1),
        "fat_g":              round(totals.get("fat_g", 0) or 0, 1),
        "fiber_g":            round(totals.get("fiber_g", 0) or 0, 1),
        "water_ml":           int(water_ml or 0),
        "meals_count":        meals_count,
        "processed_food_pct": round(processed_pct, 1),
    }
