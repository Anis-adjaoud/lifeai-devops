"""
LifeAI ADK — Tools
Les outils d'analyse appellent les agents métier.
Les outils de mémoire lisent/écrivent dans la base SQLite via database.py.
Aucun ToolContext dans les signatures — évite que le modèle passe des arguments inattendus.
"""

from contextvars import ContextVar
from typing import Optional
from . import database as db

# ContextVar : propagé automatiquement dans les coroutines async (contrairement à threading.local)
_current_user: ContextVar[str] = ContextVar("current_user", default="default")

def set_current_user(user_id: str) -> None:
    """Définit l'utilisateur courant pour la coroutine appelante (et ses enfants)."""
    _current_user.set(user_id)

def _uid() -> str:
    """Retourne l'user_id de la coroutine courante."""
    return _current_user.get()

# Alias pour compatibilité avec action_tools.py
USER_ID = "default"


# ── Outils d'analyse ──────────────────────────────────────────────────────────

def compute_activity_report(activity_data: dict) -> dict:
    """
    Calcule le score d'activité physique.
    Args:
        activity_data: Dict avec steps_today, steps_7d, active_minutes,
                       workouts_this_week, sedentary_hours, calories_burned.
    """
    from ..agents.activity_agent import ActivityAgent
    return ActivityAgent().analyze({"activity": activity_data}).to_dict()


def compute_sleep_report(sleep_data: dict) -> dict:
    """
    Calcule le score de sommeil.
    Args:
        sleep_data: Dict avec duration_hours, sleep_7d, efficiency_pct,
                    deep_sleep_pct, rem_pct, awakenings, bedtime_regularity.
    """
    from ..agents.sleep_agent import SleepAgent
    return SleepAgent().analyze({"sleep": sleep_data}).to_dict()


def compute_nutrition_report(nutrition_data: dict) -> dict:
    """
    Calcule le score nutritionnel.
    Args:
        nutrition_data: Dict avec calories_today, calories_goal, protein_g,
                        carbs_g, fat_g, fiber_g, water_ml, meals_count, processed_food_pct.
    """
    from ..agents.nutrition_agent import NutritionAgent
    return NutritionAgent().analyze({"nutrition": nutrition_data}).to_dict()


def compute_risk_report(user_data: dict) -> dict:
    """
    Calcule le score de risque burn-out en croisant tous les domaines.
    Args:
        user_data: Dict complet avec clés activity, sleep, nutrition.
    """
    from ..agents.risk_agent import RiskAgent
    return RiskAgent().analyze(user_data).to_dict()


def compute_ml_report(user_data: dict) -> dict:
    """
    Predit 3 risques a J+7 (stress, dette de sommeil, epuisement physique) via
    les modeles XGBoost entraines sur LifeSnaps (train_models/lifesnaps_ml.ipynb).
    Args:
        user_data: Dict complet, doit contenir la cle "ml" avec les features
                   en moyenne/ratio glissant 7 jours (voir agents/ml_agent.py).
    """
    from ..agents.ml_agent import MLAgent
    return MLAgent().analyze(user_data).to_dict()


# ── Mémoire — lecture ─────────────────────────────────────────────────────────

def get_context(fields: str = "all") -> dict:
    """
    Retourne le profil utilisateur, le contexte mémoire et les dernières métriques
    Google Fit (pas, sommeil, calories, poids, fréquence cardiaque).
    Args:
        fields: Passer "all" (valeur par défaut). Ignoré, retourne toujours tout.
    """
    _ = fields
    profile = db.get_profile(_uid())
    memory  = db.get_coaching_context(_uid())

    # Dernières métriques Google Fit (entrée la plus récente)
    latest_metrics = None
    metrics_rows = db.get_health_metrics(_uid(), days=7)
    if metrics_rows:
        m = metrics_rows[0]  # la plus récente
        latest_metrics = {
            "steps_today":    m.get("steps_today"),
            "steps_7d":       m.get("steps_7d"),
            "active_minutes": m.get("active_minutes"),
            "sleep_hours":    m.get("sleep_hours"),
            "sleep_7d":       m.get("sleep_7d"),
            "calories":       m.get("calories"),
            "heart_rate":     m.get("heart_rate"),
            "weight_kg":      m.get("weight_kg"),
            "recorded_at":    str(m.get("date", "")),
        }

    return {
        "profile":        profile if profile else {"status": "profil vide"},
        "memory":         memory,
        "latest_metrics": latest_metrics or {"status": "aucune donnée Google Fit enregistrée"},
    }


# ── Mémoire — écriture ────────────────────────────────────────────────────────

def save_profile(profile_update: dict) -> str:
    """
    Sauvegarde des données personnelles dans le profil utilisateur.
    Le champ 'phone' est écrit dans users.numero_tel (colonne dédiée).
    Args:
        profile_update: Dict des champs à sauvegarder, par exemple :
            {"name": "Anis", "age": 28, "weight_kg": 75, "phone": "33612345678"}
            {"goals": ["perdre 5kg"], "health_conditions": ["asthme léger"]}
    """
    phone = profile_update.get("phone")
    if phone:
        db.set_user_phone(_uid(), str(phone))
    db.update_profile(_uid(), **profile_update)
    return f"Profil sauvegardé : {', '.join(profile_update.keys())}"


def save_user_note(note: str, category: str) -> str:
    """
    Enregistre une observation sur la santé ou le mode de vie de l'utilisateur.
    Args:
        note: Observation (ex: "dort mal depuis le changement de poste").
        category: sleep | activity | nutrition | stress | medical | lifestyle | goal
    """
    db.add_note(_uid(), note, category)
    return f"Note enregistrée ({category})"


def save_session(
    global_score: float,
    activity_score: float,
    sleep_score: float,
    nutrition_score: Optional[float],
    risk_score: float,
    synthesis: str = "",
    priority_action: str = "",
    weekly_plan: Optional[list] = None,
    alerts: Optional[list] = None,
    prediction: str = "",
    health_level: str = "",
) -> str:
    """
    Enrichit la session en cours avec le rapport narratif du LLM.
    Met à jour la session créée par analyze_health_data (créée dans les 6h).
    Si aucune session récente, crée une nouvelle session complète.
    Args:
        global_score: Score global pondéré (0-100).
        activity_score, sleep_score, risk_score: Scores par domaine.
        nutrition_score: Score nutrition (0-100), ou None si nutrition_report.status
            vaut "no_data" (pas de journal alimentaire ni de profil renseigné) — ne
            jamais inventer un chiffre dans ce cas.
        synthesis: Synthèse narrative (3-4 phrases).
        priority_action: Action prioritaire recommandée.
        weekly_plan: Liste de recommandations pour la semaine.
        alerts: Liste d'alertes critiques.
        prediction: Prédiction des risques ML à J+7 (sédentarité, dette de sommeil, baisse d'activité).
        health_level: Excellent / Bon / Attention / Critique.
    """
    updated = db.update_today_session_narrative(
        _uid(),
        synthesis=synthesis or None,
        priority_action=priority_action or None,
        weekly_plan=weekly_plan if weekly_plan else None,
        alerts=alerts if alerts else None,
        prediction=prediction or None,
        health_level=health_level or None,
    )
    if not updated:
        # Fallback : aucune session récente, on en crée une complète
        db.add_session(
            _uid(),
            float(global_score), float(activity_score),
            float(sleep_score),
            float(nutrition_score) if nutrition_score is not None else None,
            float(risk_score),
            synthesis=synthesis, priority_action=priority_action,
            weekly_plan=weekly_plan or [], alerts=alerts or [],
            prediction=prediction, health_level=health_level,
        )

    sessions = db.get_sessions(_uid(), days=30)
    nouveaux_patterns = []
    if len(sessions) >= 3:
        last3 = sessions[:3]
        for pattern_type, description, field in [
            ("sleep_deficit_recurrent",  "Déficit de sommeil récurrent sur 3+ sessions",  "sleep_score"),
            ("activity_low_recurrent",   "Activité physique faible sur 3+ sessions",       "activity_score"),
            ("nutrition_low_recurrent",  "Score nutritionnel bas sur 3+ sessions",          "nutrition_score"),
            ("risk_high_recurrent",      "Risque burn-out élevé sur 3+ sessions",           "risk_score"),
        ]:
            # nutrition_score peut être None : on ne juge que les vraies valeurs
            values = [s[field] for s in last3 if s.get(field) is not None]
            if values and all(v < 50 for v in values):
                if db.add_pattern(_uid(), pattern_type, description):
                    nouveaux_patterns.append(description)

    resultat = f"Session enregistrée — score global : {global_score:.1f}/100"
    if nouveaux_patterns:
        # Signal pour le chief_agent : nouveau pattern récurrent détecté
        resultat += (
            " | NOUVEAU PATTERN RÉCURRENT DÉTECTÉ (déclenche une alerte WhatsApp "
            "maintenant via send_report_and_alert, avec ces éléments dans 'alerts') : "
            + "; ".join(nouveaux_patterns)
        )
    return resultat


def _enrich_user_data(user_data: dict) -> dict:
    """
    Complète user_data avec les données manquantes depuis le profil utilisateur.
    - nutrition : lit les valeurs du profil si non fournies dans user_data
    - sleep quality : estime depuis la durée si les indicateurs de qualité sont absents
    - risk.resting_hr : injecte la FC repos depuis _resting_hr si risk sub-dict absent
    """
    data = {**user_data}

    # ── Nutrition depuis le profil si absente ─────────────────────────────────
    nut = data.get("nutrition") or {}
    if not nut.get("calories_today"):
        profile = db.get_profile(_uid()) or {}
        if profile.get("calories_today"):
            # Valeurs réelles du profil (pas une invention)
            data["nutrition"] = {
                "calories_today":     float(profile.get("calories_today",     2000)),
                "calories_goal":      float(profile.get("calories_goal",      2000)),
                "protein_g":          float(profile.get("protein_g",          80)),
                "carbs_g":            float(profile.get("carbs_g",            200)),
                "fat_g":              float(profile.get("fat_g",              70)),
                "fiber_g":            float(profile.get("fiber_g",            20)),
                "water_ml":           float(profile.get("water_ml",           1500)),
                "meals_count":        int(profile.get("meals_count",          3)),
                "processed_food_pct": float(profile.get("processed_food_pct", 20)),
            }
        else:
            # Aucune donnée réelle : ne pas fabriquer d'alimentation type
            data["nutrition"] = {"_no_data": True}

    # ── Historique nutrition (14 derniers jours, hors aujourd'hui) ────────────
    # Historique 14j pour détecter une carence chronique
    from nutrition import nutrition_store
    data["nutrition"]["_historique_14j"] = nutrition_store.get_macro_history(_uid(), days=14)

    # ── Qualité du sommeil estimée depuis la durée si absente ─────────────────
    slp = data.get("sleep") or {}
    if slp and not slp.get("efficiency_pct"):
        duration = float(slp.get("duration_hours", 7.0))
        if duration < 5.0:
            quality = {"efficiency_pct": 62.0, "deep_sleep_pct": 8.0,  "rem_pct": 11.0, "awakenings": 6, "bedtime_regularity": 80.0}
        elif duration < 6.5:
            quality = {"efficiency_pct": 72.0, "deep_sleep_pct": 14.0, "rem_pct": 18.0, "awakenings": 3, "bedtime_regularity": 40.0}
        elif duration < 7.5:
            quality = {"efficiency_pct": 80.0, "deep_sleep_pct": 18.0, "rem_pct": 21.0, "awakenings": 2, "bedtime_regularity": 25.0}
        else:
            quality = {"efficiency_pct": 87.0, "deep_sleep_pct": 21.0, "rem_pct": 23.0, "awakenings": 1, "bedtime_regularity": 15.0}
        data["sleep"] = {**slp, **quality}

    # ── FC repos dans le sous-dict risk si absente ────────────────────────────
    risk = data.get("risk") or {}
    if not risk.get("resting_hr"):
        hr = float(data.get("_resting_hr", 65.0))
        data["risk"] = {**risk, "resting_hr": hr, "resting_hr_baseline": 65.0}

    return data


def _bmi_category(bmi: float) -> str:
    """Categorise un IMC selon les tranches vues a l'entrainement (LifeSnaps,
    anonymisees) : '<19', '19.0'..'29.0' (entier le plus proche), '>=30'."""
    if bmi < 19:
        return "<19"
    if bmi >= 30:
        return ">=30"
    return f"{round(bmi)}.0"


def _age_category(age: float) -> str:
    return "<30" if age < 30 else ">=30"


def _build_ml_features(user_data: dict) -> dict:
    """
    Approxime les features attendues par MLAgent (moyennes glissantes 7j,
    toutes obtenables via Google Fit -- le modele a ete reentraine sans
    humeur/PANAS/STAI, cf. train_models/lifesnaps_ml.ipynb) a partir des
    donnees disponibles dans user_data et du profil utilisateur. Les champs
    non trouvables (ex: bpm_roll7 si aucune FC n'est trackee) retombent sur
    les valeurs par defaut de MLAgent (profil "typique").
    """
    activity = user_data.get("activity", {}) or {}
    sleep    = user_data.get("sleep",    {}) or {}

    steps_7d = activity.get("steps_7d") or []
    sleep_7d = sleep.get("sleep_7d")   or []

    ml = {}
    if steps_7d:
        ml["steps_roll7"] = float(sum(steps_7d) / len(steps_7d))
    if sleep_7d:
        ml["minutesAsleep_roll7"] = float(sum(sleep_7d) / len(sleep_7d)) * 60
    if activity.get("active_minutes") is not None:
        active_min = float(activity["active_minutes"])
        ml["moderately_active_minutes_roll7"] = active_min
        # Google Fit ne distingue pas les intensités : on répartit active_minutes
        # selon les ratios LifeSnaps (light=9.32x, very=1.03x la valeur moderate)
        ml["lightly_active_minutes_roll7"] = active_min * 9.32
        ml["very_active_minutes_roll7"] = active_min * 1.03
    if activity.get("calories_burned") is not None:
        ml["calories_roll7"] = float(activity["calories_burned"])
    if activity.get("sedentary_hours") is not None:
        ml["sedentary_minutes_roll7"] = float(activity["sedentary_hours"]) * 60
    if sleep.get("efficiency_pct") is not None:
        ml["sleep_efficiency_roll7"] = float(sleep["efficiency_pct"])
    resting_hr = user_data.get("_resting_hr") or (user_data.get("risk") or {}).get("resting_hr")
    if resting_hr is not None:
        ml["resting_hr_roll7"] = float(resting_hr)
        # Pas de FC moyenne distincte via Google Fit : on réutilise la FC repos
        ml["bpm_roll7"] = float(resting_hr)

    # ── Profil (âge/genre/IMC) pour le ML ──
    profile = db.get_profile(_uid()) or {}
    sexe = profile.get("sexe")
    if sexe is not None:
        ml["gender_encoded"] = 1 if str(sexe).upper().startswith("F") else 0
    age = profile.get("age")
    if age is not None:
        ml["age"] = _age_category(float(age))
    taille_cm = profile.get("taille_cm")
    poids_kg  = profile.get("poids_kg") or user_data.get("_weight_kg")
    if taille_cm and poids_kg:
        bmi = float(poids_kg) / ((float(taille_cm) / 100) ** 2)
        ml["bmi"] = _bmi_category(bmi)

    return ml


def analyze_health_data(user_data: dict) -> dict:
    """
    Lance les 5 analyses en une seule fois et retourne tous les rapports + contexte mémoire.
    Utiliser à la place des compute_* séparés pour économiser des appels LLM.
    Args:
        user_data: Dict complet avec clés activity, sleep, nutrition, et si disponibles
                   _resting_hr (float) et _weight_kg (float) — a transmettre tels quels
                   depuis le JSON recu, sans les omettre : ce sont les seules sources de
                   frequence cardiaque et de poids pour le moteur ML (ml_report).
    Returns:
        Dict avec activity_report, sleep_report, nutrition_report, risk_report, ml_report, memory.
    """
    from ..agents.activity_agent  import ActivityAgent
    from ..agents.sleep_agent     import SleepAgent
    from ..agents.nutrition_agent import NutritionAgent
    from ..agents.risk_agent      import RiskAgent
    from ..agents.ml_agent        import MLAgent

    # Enrichit user_data avec profil et estimations si données manquantes
    user_data = _enrich_user_data(user_data)

    activity   = ActivityAgent().analyze({"activity":   user_data.get("activity",   {})}).to_dict()
    sleep      = SleepAgent().analyze({"sleep":         user_data.get("sleep",      {})}).to_dict()
    nutrition  = NutritionAgent().analyze({"nutrition": user_data.get("nutrition",  {})}).to_dict()
    # Injecte le score nutrition pour le RiskAgent (None géré nativement)
    user_data_with_scores = {**user_data, "_nutrition_score": nutrition.get("score")}
    risk       = RiskAgent().analyze(user_data_with_scores).to_dict()
    try:
        ml_report = MLAgent().analyze({"ml": _build_ml_features(user_data)})
        ml        = ml_report.to_dict()
        ml_risks  = ml_report.raw_data.get("_risks")
    except Exception as e:
        # Modèles ML absents ou erreur : on dégrade sans casser le pipeline
        print(f"[analyze_health_data] MLAgent indisponible : {e}", flush=True)
        from datetime import datetime
        ml = {
            "agent": "MLAgent",
            "timestamp": datetime.now().isoformat(),
            "score": None,
            "status": "unavailable",
            "key_metrics": {},
            "insights": ["Prédictions ML (stress/sommeil/épuisement à J+7) indisponibles pour le moment."],
            "recommendations": [],
            "anomalies": [],
        }
        ml_risks = None
    memory     = db.get_coaching_context(_uid())

    # Calcule le score global pondéré en Python (fiable, indépendant du LLM)
    activity_score  = float(activity.get("score", 0))
    sleep_score     = float(sleep.get("score",    0))
    risk_score      = float(risk.get("score",     0))
    nutrition_score = nutrition.get("score")  # None si pas de données réelles

    if nutrition_score is None:
        # Pas de nutrition fiable : domaine exclu, poids redistribué au prorata
        global_score = round(
            activity_score * (0.25 / 0.80) + sleep_score * (0.30 / 0.80) +
            risk_score * (0.25 / 0.80), 1
        )
    else:
        nutrition_score = float(nutrition_score)
        global_score = round(
            activity_score * 0.25 + sleep_score * 0.30 +
            nutrition_score * 0.20 + risk_score * 0.25, 1
        )
    if global_score >= 80:
        health_level = "Excellent"
    elif global_score >= 65:
        health_level = "Bon"
    elif global_score >= 45:
        health_level = "Attention"
    else:
        health_level = "Critique"

    # Persiste la session avec les scores calculés — garanti même si le LLM ne finit pas
    db.add_session(
        _uid(),
        global_score, activity_score, sleep_score, nutrition_score, risk_score,
        health_level=health_level,
        ml_risks=ml_risks,
    )

    # Persiste les métriques brutes Google Fit pour l'affichage dans le dashboard
    act = user_data.get("activity", {})
    slp = user_data.get("sleep",    {})
    db.add_health_metrics(
        _uid(),
        steps_today    = int(act.get("steps_today",    0)),
        steps_7d       = act.get("steps_7d",          []),
        active_minutes = int(act.get("active_minutes", 0)),
        sleep_hours    = float(slp.get("duration_hours", 0)),
        sleep_7d       = slp.get("sleep_7d",          []),
        calories       = int(act.get("calories_burned", 0)),
        heart_rate     = user_data.get("_resting_hr"),
        weight_kg      = user_data.get("_weight_kg"),
    )

    return {
        "activity_report":   activity,
        "sleep_report":      sleep,
        "nutrition_report":  nutrition,
        "risk_report":       risk,
        "ml_report":         ml,
        "memory":            memory,
        "profile":           db.get_profile(_uid()) or {},
        # Scores pré-calculés pour que le LLM les utilise directement
        "global_score":      global_score,
        "activity_score":    activity_score,
        "sleep_score":       sleep_score,
        "nutrition_score":   nutrition_score,
        "risk_score":        risk_score,
        "health_level":      health_level,
    }
