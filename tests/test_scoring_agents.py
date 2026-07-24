"""
Tests des quatre agents de scoring (activity, sleep, nutrition, risk).

Ces agents sont des fonctions pures : `analyze(dict) -> AgentReport`, sans base
de données, sans appel LLM et sans réseau (`llm_insights` vaut False par
défaut). Ils sont donc testables tels quels en CI, sans service externe.

Les tests sont paramétrés sur les quatre agents : toute règle vérifiée ici vaut
pour chacun, ce qui évite quatre fichiers quasi identiques.
"""
import pytest

from agentic.agents.activity_agent import ActivityAgent
from agentic.agents.sleep_agent import SleepAgent
from agentic.agents.nutrition_agent import NutritionAgent
from agentic.agents.risk_agent import RiskAgent


AGENTS = [
    pytest.param(ActivityAgent, id="activity"),
    pytest.param(SleepAgent, id="sleep"),
    pytest.param(NutritionAgent, id="nutrition"),
    pytest.param(RiskAgent, id="risk"),
]


@pytest.mark.parametrize("agent_cls", AGENTS)
def test_profil_sain_obtient_un_bon_score(agent_cls, profil_sain):
    rapport = agent_cls().analyze(profil_sain)

    assert rapport.score >= 70, f"{agent_cls.__name__} note trop bas un profil sain"
    assert rapport.status == "good"


@pytest.mark.parametrize("agent_cls", AGENTS)
def test_profil_degrade_est_signale_critique(agent_cls, profil_degrade):
    rapport = agent_cls().analyze(profil_degrade)

    assert rapport.score <= 45, f"{agent_cls.__name__} note trop haut un profil dégradé"
    assert rapport.status == "critical"


@pytest.mark.parametrize("agent_cls", AGENTS)
def test_le_profil_sain_est_toujours_mieux_note_que_le_degrade(
    agent_cls, profil_sain, profil_degrade
):
    """L'ordre relatif importe plus que la valeur absolue : c'est lui qui casse
    en premier si une pondération est modifiée par erreur."""
    agent = agent_cls()

    assert agent.analyze(profil_sain).score > agent.analyze(profil_degrade).score


@pytest.mark.parametrize("agent_cls", AGENTS)
def test_le_score_reste_dans_les_bornes(agent_cls, profil_sain, profil_degrade):
    for donnees in (profil_sain, profil_degrade, {}):
        score = agent_cls().analyze(donnees).score
        assert score is None or 0 <= score <= 100


@pytest.mark.parametrize("agent_cls", AGENTS)
def test_le_rapport_est_bien_forme(agent_cls, profil_sain):
    rapport = agent_cls().analyze(profil_sain)

    assert rapport.agent_name
    assert rapport.timestamp
    assert rapport.status in {"good", "warning", "critical", "no_data"}
    assert isinstance(rapport.key_metrics, dict)
    assert isinstance(rapport.insights, list)
    assert isinstance(rapport.recommendations, list)
    assert isinstance(rapport.to_dict(), dict)


@pytest.mark.parametrize("agent_cls", AGENTS)
def test_donnees_absentes_ne_font_pas_planter(agent_cls):
    """Un utilisateur fraîchement inscrit n'a encore aucune donnée.

    On vérifie seulement l'absence de plantage et un rapport exploitable : la
    valeur du score n'est volontairement PAS asserée ici, car les agents ne
    s'accordent pas sur la valeur par défaut à appliquer quand tout manque
    (activity part de zéro, les trois autres partent de valeurs favorables).
    Figer ce comportement dans un test reviendrait à l'entériner.
    """
    rapport = agent_cls().analyze({})

    assert rapport is not None
    assert rapport.status in {"good", "warning", "critical", "no_data"}


@pytest.mark.parametrize("agent_cls", AGENTS)
def test_valeurs_aberrantes_ne_font_pas_planter(agent_cls):
    """Une API tierce peut renvoyer des valeurs négatives ou hors échelle."""
    aberrant = {
        "activity": {
            "steps_today": -500,
            "steps_7d": [],
            "active_minutes": 99999,
            "workouts_this_week": -3,
            "sedentary_hours": 48,
            "calories_burned": -10,
        },
        "sleep": {
            "duration_hours": -2,
            "sleep_7d": [],
            "efficiency_pct": 250,
            "deep_sleep_pct": -5,
            "rem_pct": 300,
            "awakenings": -1,
            "bedtime_regularity": -60,
        },
        "nutrition": {
            "calories_today": -100,
            "calories_goal": 0,
            "protein_g": -5,
            "carbs_g": 99999,
            "fat_g": -1,
            "fiber_g": -2,
            "water_ml": -50,
            "meals_count": -1,
            "processed_food_pct": 500,
        },
        "risk": {
            "stress_level": 99,
            "resting_hr": -40,
            "resting_hr_baseline": 0,
            "hrv": -10,
            "hrv_baseline": 0,
        },
    }

    rapport = agent_cls().analyze(aberrant)

    assert rapport is not None
    assert rapport.score is None or 0 <= rapport.score <= 100
