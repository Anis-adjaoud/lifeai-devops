"""
Profils de référence partagés par les tests des agents de scoring.

Les quatre agents (activity, sleep, nutrition, risk) lisent chacun leur propre
sous-dictionnaire dans le même `user_data`. Ces deux profils couvrent donc les
clés des quatre agents à la fois, ce qui permet de les tester en paramétré.

Valeurs calibrées sur le comportement réel des agents : le profil sain obtient
entre 88 et 100 selon l'agent, le profil dégradé entre 6 et 37. Les seuils
utilisés dans les tests (>= 70 / <= 45) gardent donc une marge confortable et
ne casseront pas au moindre ajustement de pondération.
"""
import pytest


PROFIL_SAIN = {
    "activity": {
        "steps_today": 11500,
        "steps_7d": [11200, 12500, 9800, 13100, 10600, 11900, 10500],
        "active_minutes": 52,
        "workouts_this_week": 4,
        "sedentary_hours": 6,
        "calories_burned": 520,
    },
    "sleep": {
        "duration_hours": 8.0,
        "sleep_7d": [7.8, 8.1, 7.9, 8.0, 8.2, 7.7, 8.0],
        "efficiency_pct": 93,
        "deep_sleep_pct": 20,
        "rem_pct": 22,
        "awakenings": 1,
        "bedtime_regularity": 15,
    },
    "nutrition": {
        "calories_today": 2100,
        "calories_goal": 2100,
        "protein_g": 95,
        "carbs_g": 190,
        "fat_g": 75,
        "fiber_g": 32,
        "water_ml": 2200,
        "meals_count": 4,
        "processed_food_pct": 5,
    },
    "risk": {
        "stress_level": 2,
        "resting_hr": 56,
        "resting_hr_baseline": 58,
        "hrv": 65,
        "hrv_baseline": 60,
    },
}

PROFIL_DEGRADE = {
    "activity": {
        "steps_today": 900,
        "steps_7d": [1200, 800, 1500, 950, 2100, 700, 1100],
        "active_minutes": 3,
        "workouts_this_week": 0,
        "sedentary_hours": 13,
        "calories_burned": 90,
    },
    "sleep": {
        "duration_hours": 4.0,
        "sleep_7d": [4.2, 3.8, 5.1, 3.5, 4.8, 4.0, 3.9],
        "efficiency_pct": 62,
        "deep_sleep_pct": 6,
        "rem_pct": 9,
        "awakenings": 7,
        "bedtime_regularity": 120,
    },
    "nutrition": {
        "calories_today": 3200,
        "calories_goal": 1800,
        "protein_g": 30,
        "carbs_g": 420,
        "fat_g": 140,
        "fiber_g": 3,
        "water_ml": 400,
        "meals_count": 1,
        "processed_food_pct": 85,
    },
    "risk": {
        "stress_level": 9,
        "resting_hr": 94,
        "resting_hr_baseline": 70,
        "hrv": 22,
        "hrv_baseline": 55,
    },
}


@pytest.fixture
def profil_sain() -> dict:
    return {k: dict(v) for k, v in PROFIL_SAIN.items()}


@pytest.fixture
def profil_degrade() -> dict:
    return {k: dict(v) for k, v in PROFIL_DEGRADE.items()}
