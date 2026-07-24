#!/usr/bin/env python3
"""
Crée deux profils de démonstration LifeAI dans PostgreSQL :
  - Lucas Martin  : excellent état de santé (score ~87, niveau "Excellent")
  - Emma Rousseau : état critique (score ~23, niveau "Critique")
"""
import sys, json, random
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))

# Initialise la connexion DB (charge aussi le .env)
from agentic.agents_adk.database import _connect, ensure_user, update_profile, add_pattern, add_note, set_user_phone


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ts(days_ago: float) -> str:
    """Timestamp ISO il y a N jours."""
    return (datetime.now() - timedelta(days=days_ago)).isoformat()


def _insert_session(conn, user_id, days_ago, gs, act, slp, nut, risk, level, synth, prio, plan, alerts, pred):
    conn.execute(
        """INSERT INTO sessions
           (user_id, date, global_score, activity_score, sleep_score, nutrition_score, risk_score,
            health_level, synthesis, priority_action, weekly_plan, alerts, prediction)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, _ts(days_ago), round(gs,1), round(act,1), round(slp,1),
         round(nut,1), round(risk,1), level, synth, prio,
         json.dumps(plan, ensure_ascii=False),
         json.dumps(alerts, ensure_ascii=False), pred),
    )


def _insert_metrics(conn, user_id, days_ago, steps_today, steps_7d, active_min, sleep_h, sleep_7d, cal, hr, weight):
    conn.execute(
        """INSERT INTO health_metrics
           (user_id, date, steps_today, steps_7d, active_minutes, sleep_hours, sleep_7d, calories, heart_rate, weight_kg)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id, _ts(days_ago), steps_today,
         json.dumps(steps_7d), active_min, sleep_h,
         json.dumps(sleep_7d), cal, hr, weight),
    )


# ══════════════════════════════════════════════════════════════════════════════
# PROFIL 1 — Lucas Martin  (Excellent)
# ══════════════════════════════════════════════════════════════════════════════

LUCAS = "lucas.martin@lifeai.demo"

def seed_lucas():
    print("Creation de Lucas Martin...")
    ensure_user(LUCAS, "Lucas Martin")
    set_user_phone(LUCAS, "33612345678")
    update_profile(
        LUCAS,
        prenom="Lucas", nom="Martin", age=32, sexe="M",
        taille_cm=180, poids_kg=74, objectif="Performance sportive et bien-être durable",
        activite_niveau="élevé", phone="33612345678",
        habitudes_sommeil="couche à 22h30, réveil à 6h30",
        alimentation="méditerranéenne, peu de sucre, peu d'alcool",
        # Données nutrition pour _user_data_from_metrics
        calories_today=2100, calories_goal=2100,
        protein_g=95, carbs_g=190, fat_g=75, fiber_g=35,
        water_ml=2200, meals_count=4, processed_food_pct=5,
    )

    # Scores calculés par les agents Python avec les métriques de Lucas :
    # activity≈85 | sleep≈96 | nutrition≈89 | risk≈100 → global≈93
    sessions = [
        # (days_ago, global, act, sleep, nut, risk, level)
        (0,  92.5, 86, 96, 89, 98, "Excellent"),
        (2,  91.3, 85, 95, 88, 97, "Excellent"),
        (4,  90.8, 87, 96, 90, 96, "Excellent"),
        (6,  93.1, 88, 97, 91, 99, "Excellent"),
        (8,  89.7, 84, 94, 88, 95, "Excellent"),
        (10, 88.4, 83, 93, 87, 94, "Excellent"),
        (12, 91.0, 86, 95, 90, 97, "Excellent"),
        (14, 87.2, 82, 93, 86, 93, "Excellent"),
        (16, 90.0, 85, 96, 89, 96, "Excellent"),
        (18, 88.9, 84, 94, 88, 95, "Excellent"),
        (21, 86.5, 82, 92, 86, 93, "Excellent"),
        (24, 84.2, 80, 91, 85, 90, "Excellent"),
        (27, 87.0, 83, 94, 87, 94, "Excellent"),
        (30, 83.8, 79, 91, 84, 90, "Excellent"),
    ]
    narratives = [
        ("Lucas, ton équilibre santé est remarquable. Activité physique soutenue, sommeil réparateur et alimentation de qualité forment un triptyque optimal. Ton risque cardiovasculaire est minimal grâce à ta fréquence cardiaque de repos de 58 bpm.",
         "Continue tes sorties running 3×/semaine et ajoute 10 min de mobilité le matin.",
         ["Lundi : 8 km en zone 2 + étirements", "Mercredi : HIIT 25 min + gainage", "Vendredi : sortie longue 12 km", "Week-end : yoga ou randonnée"],
         [],
         "Dans 3 mois, maintien probable à 85+/100. Risque de blessure sportive si tu augmentes l'intensité trop vite."),
        ("Excellente semaine pour Lucas ! Tes données témoignent d'un mode de vie exemplaire. Le sommeil profond optimise ta récupération musculaire.",
         "Intègre une session de renforcement musculaire supplémentaire.",
         ["Lundi : course 7 km", "Mercredi : musculation", "Vendredi : vélo 40 min", "Week-end : sport collectif"],
         [],
         "Trajectoire excellente. Score prévu stable à 85-90/100."),
    ]

    with _connect() as conn:
        # Supprime les anciennes données si re-seed
        conn.execute("DELETE FROM sessions       WHERE user_id = %s", (LUCAS,))
        conn.execute("DELETE FROM health_metrics WHERE user_id = %s", (LUCAS,))
        conn.execute("DELETE FROM patterns       WHERE user_id = %s", (LUCAS,))
        conn.execute("DELETE FROM user_notes     WHERE user_id = %s", (LUCAS,))

        for i, (days_ago, gs, act, slp, nut, risk, level) in enumerate(sessions):
            n = narratives[i % len(narratives)]
            _insert_session(conn, LUCAS, days_ago, gs, act, slp, nut, risk, level, *n)

        # Métriques Google Fit (7 entrées sur 7 jours)
        steps_week  = [11200, 12500, 9800, 13100, 10600, 11900, 8500]
        sleep_week  = [7.8, 8.1, 7.5, 8.0, 7.9, 8.2, 7.6]
        for d in range(7):
            _insert_metrics(
                conn, LUCAS, d,
                steps_today=steps_week[d],
                steps_7d=steps_week,
                active_min=52 - d*2,
                sleep_h=sleep_week[d],
                sleep_7d=sleep_week,
                cal=520 - d*10,
                hr=58.0,
                weight=74.0,
            )

        # Patterns
        conn.execute(
            """INSERT INTO patterns(user_id, pattern_type, description, occurrences, detected_at, last_seen)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, pattern_type) DO UPDATE
               SET occurrences = EXCLUDED.occurrences, last_seen = EXCLUDED.last_seen""",
            (LUCAS, "sportif_regulier",
             "Lucas maintient une activité physique de haute intensité 4-5×/semaine depuis plus de 6 mois.", 18, _ts(30), _ts(0)),
        )
        conn.execute(
            """INSERT INTO patterns(user_id, pattern_type, description, occurrences, detected_at, last_seen)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, pattern_type) DO UPDATE
               SET occurrences = EXCLUDED.occurrences, last_seen = EXCLUDED.last_seen""",
            (LUCAS, "sommeil_excellent",
             "Durée de sommeil régulière entre 7h30 et 8h30 avec réveil constant à 6h30.", 14, _ts(28), _ts(1)),
        )
        conn.execute(
            """INSERT INTO patterns(user_id, pattern_type, description, occurrences, detected_at, last_seen)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, pattern_type) DO UPDATE
               SET occurrences = EXCLUDED.occurrences, last_seen = EXCLUDED.last_seen""",
            (LUCAS, "alimentation_optimale",
             "Régime méditerranéen strict, repas structurés, hydratation ≥ 2L/j.", 10, _ts(20), _ts(3)),
        )

        # Notes
        conn.execute(
            "INSERT INTO user_notes(user_id, note, category, created_at) VALUES (%s, %s, %s, %s)",
            (LUCAS, "Lucas prépare un semi-marathon dans 8 semaines. Plan d'entraînement à adapter.", "objectif", _ts(5)),
        )
        conn.execute(
            "INSERT INTO user_notes(user_id, note, category, created_at) VALUES (%s, %s, %s, %s)",
            (LUCAS, "Excellente récupération après les séances intenses. HRV élevée. Physiologie de sportif.", "observation", _ts(2)),
        )

    print(f"   OK Lucas Martin cree (user_id: {LUCAS})")


# ══════════════════════════════════════════════════════════════════════════════
# PROFIL 2 — Emma Rousseau  (Critique)
# ══════════════════════════════════════════════════════════════════════════════

EMMA = "emma.rousseau@lifeai.demo"

def seed_emma():
    print("Creation d'Emma Rousseau...")
    ensure_user(EMMA, "Emma Rousseau")
    set_user_phone(EMMA, "33698765432")
    update_profile(
        EMMA,
        prenom="Emma", nom="Rousseau", age=26, sexe="F",
        taille_cm=165, poids_kg=89, objectif="Reprendre une vie saine, perdre du poids",
        activite_niveau="très faible", phone="33698765432",
        habitudes_sommeil="couche tard (2h-3h du matin), réveil difficile, insomnies fréquentes",
        alimentation="fast-food presque quotidien, peu de légumes, beaucoup de sucre et caféine",
        # Données nutrition pour _user_data_from_metrics
        calories_today=2800, calories_goal=1800,
        protein_g=30, carbs_g=0, fat_g=0, fiber_g=3,
        water_ml=400, meals_count=1, processed_food_pct=85,
    )

    # Scores calculés par les agents Python avec les métriques d'Emma :
    # activity≈8 | sleep≈41 | nutrition≈14 | risk≈54 → global≈31
    sessions = [
        # (days_ago, global, act, sleep, nut, risk, level)
        (0,  30.5,  8, 41, 14, 54, "Critique"),
        (2,  28.9,  7, 38, 13, 52, "Critique"),
        (4,  32.1,  9, 44, 15, 55, "Critique"),
        (6,  29.7,  8, 40, 14, 53, "Critique"),
        (8,  33.4, 10, 46, 16, 56, "Critique"),
        (10, 27.8,  6, 36, 12, 50, "Critique"),
        (12, 31.2,  9, 42, 14, 54, "Critique"),
        (14, 35.0, 11, 47, 17, 57, "Critique"),
        (16, 32.3,  9, 44, 15, 55, "Critique"),
        (18, 30.8,  8, 40, 14, 53, "Critique"),
        (21, 29.1,  7, 38, 13, 51, "Critique"),
        (24, 32.6,  9, 42, 15, 55, "Critique"),
        (27, 31.0,  8, 41, 14, 54, "Critique"),
        (30, 33.5, 10, 44, 15, 56, "Critique"),
    ]
    narratives = [
        ("Emma, la situation est préoccupante. Ton sommeil de moins de 4h30 par nuit génère un déficit chronique sévère qui impacte ta concentration, ton métabolisme et ton système immunitaire. Combiné à une sédentarité extrême et une alimentation ultra-transformée, le risque de burn-out et de pathologie métabolique est élevé.",
         "PRIORITÉ ABSOLUE : te coucher avant minuit ce soir et faire 10 min de marche demain matin.",
         ["Lundi : marche 15 min après le déjeuner", "Mercredi : coucher à 23h max + méditation 5 min", "Vendredi : remplacer 1 repas fast-food par fait maison", "Week-end : sortie extérieure 30 min"],
         ["Sommeil critique < 4h30 — risque burn-out élevé", "Sédentarité extrême < 1500 pas/jour", "Alimentation ultra-transformée — risque métabolique", "Fréquence cardiaque de repos à 94 bpm — attention cardiovasculaire"],
         "Sans changement, aggravation probable dans 3 mois. Avec 2 changements simples (sommeil + marche quotidienne), retour possible à 45+/100."),
        ("Emma, les données de cette semaine sont très inquiétantes. Le manque de sommeil cumulé atteint un niveau critique. Ton corps est en mode survie, ce qui explique les fringales sucrées et l'absence d'énergie pour bouger.",
         "Éteins les écrans à 23h et dors dans le noir total — c'est la priorité n°1 avant tout le reste.",
         ["Lundi : aucun écran après 23h", "Mercredi : 1 verre d'eau avant chaque repas", "Vendredi : marche 10 min", "Week-end : 1 repas équilibré minimum"],
         ["Insomnie chronique détectée — durée moyenne 4h12", "Risque burn-out : ÉLEVÉ", "Absence quasi-totale d'activité physique"],
         "Situation préoccupante. Consultation médicale recommandée si aucune amélioration dans 2 semaines."),
    ]

    with _connect() as conn:
        # Supprime les anciennes données si re-seed
        conn.execute("DELETE FROM sessions       WHERE user_id = %s", (EMMA,))
        conn.execute("DELETE FROM health_metrics WHERE user_id = %s", (EMMA,))
        conn.execute("DELETE FROM patterns       WHERE user_id = %s", (EMMA,))
        conn.execute("DELETE FROM user_notes     WHERE user_id = %s", (EMMA,))

        for i, (days_ago, gs, act, slp, nut, risk, level) in enumerate(sessions):
            n = narratives[i % len(narratives)]
            _insert_session(conn, EMMA, days_ago, gs, act, slp, nut, risk, level, *n)

        # Métriques Google Fit
        steps_week = [1200, 800, 1500, 950, 2100, 700, 1100]
        sleep_week = [4.2, 3.8, 5.1, 3.5, 4.8, 4.0, 3.9]
        for d in range(7):
            _insert_metrics(
                conn, EMMA, d,
                steps_today=steps_week[d],
                steps_7d=steps_week,
                active_min=4 + d,
                sleep_h=sleep_week[d],
                sleep_7d=sleep_week,
                cal=150 + d*10,
                hr=94.0,
                weight=89.0,
            )

        # Patterns
        conn.execute(
            """INSERT INTO patterns(user_id, pattern_type, description, occurrences, detected_at, last_seen)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, pattern_type) DO UPDATE
               SET occurrences = EXCLUDED.occurrences, last_seen = EXCLUDED.last_seen""",
            (EMMA, "insomnie_chronique",
             "Durée de sommeil constamment inférieure à 5h depuis plus de 3 semaines. Coucher régulièrement après 2h du matin.", 14, _ts(28), _ts(0)),
        )
        conn.execute(
            """INSERT INTO patterns(user_id, pattern_type, description, occurrences, detected_at, last_seen)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, pattern_type) DO UPDATE
               SET occurrences = EXCLUDED.occurrences, last_seen = EXCLUDED.last_seen""",
            (EMMA, "sedentarite_extreme",
             "Moins de 2000 pas/jour en moyenne. Absence quasi-totale d'activité physique structurée.", 12, _ts(25), _ts(1)),
        )
        conn.execute(
            """INSERT INTO patterns(user_id, pattern_type, description, occurrences, detected_at, last_seen)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, pattern_type) DO UPDATE
               SET occurrences = EXCLUDED.occurrences, last_seen = EXCLUDED.last_seen""",
            (EMMA, "alimentation_desequilibree",
             "Consommation quotidienne de fast-food, sodas et snacks industriels. Apports en légumes quasi nuls.", 11, _ts(22), _ts(2)),
        )
        conn.execute(
            """INSERT INTO patterns(user_id, pattern_type, description, occurrences, detected_at, last_seen)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, pattern_type) DO UPDATE
               SET occurrences = EXCLUDED.occurrences, last_seen = EXCLUDED.last_seen""",
            (EMMA, "risque_burnout_eleve",
             "Combinaison stress chronique, manque de sommeil et surcharge mentale. Score risque < 35 en continu.", 9, _ts(18), _ts(0)),
        )

        # Notes
        conn.execute(
            "INSERT INTO user_notes(user_id, note, category, created_at) VALUES (%s, %s, %s, %s)",
            (EMMA, "Emma a mentionné se sentir épuisée en permanence, des difficultés de concentration au travail et des maux de tête fréquents.", "symptomes", _ts(3)),
        )
        conn.execute(
            "INSERT INTO user_notes(user_id, note, category, created_at) VALUES (%s, %s, %s, %s)",
            (EMMA, "Surconsommation de café (6-8 tasses/jour) pour compenser le manque de sommeil. Cercle vicieux détecté.", "observation", _ts(1)),
        )
        conn.execute(
            "INSERT INTO user_notes(user_id, note, category, created_at) VALUES (%s, %s, %s, %s)",
            (EMMA, "A exprimé une forte motivation pour changer mais se dit dépassée et sans énergie pour commencer. Approche bienveillante et micro-objectifs recommandée.", "coaching", _ts(0)),
        )

    print(f"   OK Emma Rousseau creee (user_id: {EMMA})")


# ── Lancement ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nSeed des profils de demonstration LifeAI\n")
    seed_lucas()
    seed_emma()
    print("\nTermine !")
    print(f"\n   Lucas Martin  : {LUCAS}  (Excellent ~87/100)")
    print(f"   Emma Rousseau : {EMMA}  (Critique ~23/100)")
    print("\n   Selectionne un utilisateur dans le menu deroulant du Dashboard.\n")
