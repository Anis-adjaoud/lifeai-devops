"""
LifeAI — Stockage du journal alimentaire (façon YAZIO).

Google Fit ne fournit pas la nutrition ; ce module persiste :
  - `foods`         : catalogue d'aliments (seedé depuis CIQUAL, voir import_foods)
  - `food_log`      : aliments consommés par (user, jour, repas), avec snapshot nutritionnel
  - `water_log`     : hydratation par (user, jour)
  - `nutrition_goal`: objectif calorique par user

Réutilise la couche de connexion PostgreSQL existante
(agentic.agents_adk.database._connect) : même base, même pool — sans modifier la
racine (import en lecture seule uniquement).
"""

from __future__ import annotations

from datetime import date
import json
from typing import Optional

from agentic.agents_adk.database import _connect

MEALS = ("breakfast", "lunch", "dinner", "snack")

# Liquides CIQUAL : saisis en ml (densité ≈ 1, ml réutilisé comme grammes)
_LIQUID_CATEGORY = "eaux et autres boissons"


def is_liquid(category) -> bool:
    return (category or "").strip().lower() == _LIQUID_CATEGORY


# ── Schéma ────────────────────────────────────────────────────────────────────

def init_diary_tables() -> None:
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS foods (
            code         TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            category     TEXT,
            kcal_100g    REAL,
            protein_100g REAL,
            carbs_100g   REAL,
            fat_100g     REAL,
            fiber_100g   REAL,
            nutriscore   TEXT,
            processed    BOOLEAN DEFAULT FALSE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS food_log (
            id         SERIAL PRIMARY KEY,
            user_id    TEXT NOT NULL,
            date       DATE NOT NULL DEFAULT CURRENT_DATE,
            meal       TEXT NOT NULL,
            food_code  TEXT NOT NULL,
            quantity_g REAL NOT NULL,
            kcal       REAL, protein_g REAL, carbs_g REAL, fat_g REAL, fiber_g REAL,
            processed  BOOLEAN,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_food_log_user_date ON food_log(user_id, date)",
        "CREATE INDEX IF NOT EXISTS idx_foods_name ON foods(lower(name))",
        """
        CREATE TABLE IF NOT EXISTS water_log (
            user_id TEXT NOT NULL,
            date    DATE NOT NULL DEFAULT CURRENT_DATE,
            ml      INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS nutrition_goal (
            user_id   TEXT PRIMARY KEY,
            kcal_goal INTEGER NOT NULL DEFAULT 2000
        )
        """,
        # Résultats de l'analyse nutrition (dernier run) — insights/reco du NutritionAgent
        """
        CREATE TABLE IF NOT EXISTS nutrition_analysis (
            user_id         TEXT PRIMARY KEY,
            score           REAL,
            insights        TEXT DEFAULT '[]',
            recommendations TEXT DEFAULT '[]',
            anomalies       TEXT DEFAULT '[]',
            updated_at      TIMESTAMPTZ DEFAULT NOW()
        )
        """,
    ]
    with _connect() as conn:
        for stmt in stmts:
            conn.execute(stmt)


# ── Catalogue foods ───────────────────────────────────────────────────────────

def foods_count() -> int:
    with _connect() as conn:
        conn.execute("SELECT COUNT(*) AS n FROM foods")
        return conn.fetchone()["n"]


def bulk_insert_foods(foods: list[dict]) -> None:
    with _connect() as conn:
        for f in foods:
            conn.execute(
                """INSERT INTO foods
                       (code, name, category, kcal_100g, protein_100g, carbs_100g,
                        fat_100g, fiber_100g, nutriscore, processed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (code) DO NOTHING""",
                (f["code"], f["name"], f.get("category"), f.get("kcal_100g"),
                 f.get("protein_100g"), f.get("carbs_100g"), f.get("fat_100g"),
                 f.get("fiber_100g"), f.get("nutriscore"), f.get("processed", False)),
            )


def search_foods(query: str, limit: int = 25) -> list[dict]:
    """Recherche par nom (ILIKE), aliments commençant par la requête d'abord."""
    q = (query or "").strip()
    if not q:
        return []
    with _connect() as conn:
        conn.execute(
            """SELECT code, name, category, kcal_100g, protein_100g, carbs_100g,
                      fat_100g, fiber_100g, nutriscore, processed
               FROM foods
               WHERE name ILIKE ?
               ORDER BY (CASE WHEN lower(name) LIKE lower(?) THEN 0 ELSE 1 END),
                        length(name), name
               LIMIT ?""",
            (f"%{q}%", f"{q}%", limit),
        )
        rows = [dict(r) for r in conn.fetchall()]
    for r in rows:
        r["is_liquid"] = is_liquid(r.get("category"))
    return rows


def get_food(code: str) -> Optional[dict]:
    with _connect() as conn:
        conn.execute(
            """SELECT code, name, category, kcal_100g, protein_100g, carbs_100g,
                      fat_100g, fiber_100g, nutriscore, processed
               FROM foods WHERE code = ?""",
            (code,),
        )
        row = conn.fetchone()
    return dict(row) if row else None


# ── Journal ───────────────────────────────────────────────────────────────────

def add_log(user_id: str, meal: str, food_code: str, quantity_g: float) -> Optional[int]:
    """Ajoute un aliment à un repas du jour ; calcule le snapshot nutritionnel."""
    food = get_food(food_code)
    if food is None:
        return None
    r = quantity_g / 100.0
    kcal    = (food["kcal_100g"]    or 0) * r
    protein = (food["protein_100g"] or 0) * r
    carbs   = (food["carbs_100g"]   or 0) * r
    fat     = (food["fat_100g"]     or 0) * r
    fiber   = (food["fiber_100g"]   or 0) * r
    with _connect() as conn:
        conn.execute(
            """INSERT INTO food_log
                   (user_id, meal, food_code, quantity_g,
                    kcal, protein_g, carbs_g, fat_g, fiber_g, processed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (user_id, meal, food_code, quantity_g,
             kcal, protein, carbs, fat, fiber, bool(food.get("processed"))),
        )
        row = conn.fetchone()
    return row["id"] if row else None


def get_log_owner(entry_id: int) -> Optional[str]:
    """Retourne le user_id propriétaire d'une entrée du journal, ou None si introuvable."""
    with _connect() as conn:
        conn.execute("SELECT user_id FROM food_log WHERE id = ?", (entry_id,))
        row = conn.fetchone()
    return row["user_id"] if row else None


def delete_log(entry_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM food_log WHERE id = ?", (entry_id,))


def get_diary(user_id: str, day: Optional[date] = None) -> dict:
    """
    Journal d'un jour (défaut = aujourd'hui) : entrées groupées par repas,
    sous-totaux par repas, et totaux du jour (dont kcal transformés).
    """
    with _connect() as conn:
        if day is None:
            conn.execute(
                """SELECT fl.id, fl.meal, fl.food_code, fl.quantity_g, fl.kcal,
                          fl.protein_g, fl.carbs_g, fl.fat_g, fl.fiber_g, fl.processed,
                          f.name, f.nutriscore, f.category
                   FROM food_log fl LEFT JOIN foods f ON f.code = fl.food_code
                   WHERE fl.user_id = ? AND fl.date = CURRENT_DATE
                   ORDER BY fl.created_at""",
                (user_id,),
            )
        else:
            conn.execute(
                """SELECT fl.id, fl.meal, fl.food_code, fl.quantity_g, fl.kcal,
                          fl.protein_g, fl.carbs_g, fl.fat_g, fl.fiber_g, fl.processed,
                          f.name, f.nutriscore, f.category
                   FROM food_log fl LEFT JOIN foods f ON f.code = fl.food_code
                   WHERE fl.user_id = ? AND fl.date = ?
                   ORDER BY fl.created_at""",
                (user_id, day),
            )
        rows = [dict(r) for r in conn.fetchall()]
    for e in rows:
        e["is_liquid"] = is_liquid(e.get("category"))

    meals = {m: {"entries": [], "kcal": 0.0} for m in MEALS}
    totals = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0,
              "fiber_g": 0.0, "processed_kcal": 0.0, "entries": 0}
    for e in rows:
        meal = e["meal"] if e["meal"] in meals else "snack"
        meals[meal]["entries"].append(e)
        meals[meal]["kcal"] += e["kcal"] or 0
        totals["kcal"]      += e["kcal"] or 0
        totals["protein_g"] += e["protein_g"] or 0
        totals["carbs_g"]   += e["carbs_g"] or 0
        totals["fat_g"]     += e["fat_g"] or 0
        totals["fiber_g"]   += e["fiber_g"] or 0
        totals["entries"]   += 1
        if e["processed"]:
            totals["processed_kcal"] += e["kcal"] or 0

    for m in meals.values():
        m["kcal"] = round(m["kcal"])
    for k in ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "processed_kcal"):
        totals[k] = round(totals[k], 1)

    return {"meals": meals, "totals": totals}


def get_macro_history(user_id: str, days: int = 14) -> list[dict]:
    """
    Totaux nutritionnels par jour sur les N derniers jours (un jour sans
    entrée n'apparaît pas dans le résultat — contrairement à get_diary() qui
    ne couvre qu'un seul jour, ceci permet de détecter des tendances/carences
    chroniques, ex: apport protéique insuffisant sur plusieurs semaines).
    """
    with _connect() as conn:
        conn.execute(
            """SELECT date, SUM(kcal) AS kcal, SUM(protein_g) AS protein_g,
                      SUM(carbs_g) AS carbs_g, SUM(fat_g) AS fat_g, COUNT(*) AS entries
               FROM food_log
               WHERE user_id = ? AND date >= CURRENT_DATE - ? AND date < CURRENT_DATE
               GROUP BY date
               ORDER BY date DESC""",
            (user_id, days),
        )
        return [dict(r) for r in conn.fetchall()]


# ── Eau ───────────────────────────────────────────────────────────────────────

def get_water(user_id: str, day: Optional[date] = None) -> int:
    with _connect() as conn:
        if day is None:
            conn.execute("SELECT ml FROM water_log WHERE user_id = ? AND date = CURRENT_DATE", (user_id,))
        else:
            conn.execute("SELECT ml FROM water_log WHERE user_id = ? AND date = ?", (user_id, day))
        row = conn.fetchone()
    return row["ml"] if row else 0


def set_water(user_id: str, ml: int) -> None:
    ml = max(0, int(ml))
    with _connect() as conn:
        conn.execute(
            """INSERT INTO water_log (user_id, date, ml)
               VALUES (?, CURRENT_DATE, ?)
               ON CONFLICT (user_id, date) DO UPDATE SET ml = EXCLUDED.ml""",
            (user_id, ml),
        )


# ── Objectif calorique ────────────────────────────────────────────────────────

def get_goal(user_id: str) -> int:
    with _connect() as conn:
        conn.execute("SELECT kcal_goal FROM nutrition_goal WHERE user_id = ?", (user_id,))
        row = conn.fetchone()
    return row["kcal_goal"] if row else 2000


def set_goal(user_id: str, kcal_goal: int) -> None:
    kcal_goal = max(800, min(int(kcal_goal), 6000))
    with _connect() as conn:
        conn.execute(
            """INSERT INTO nutrition_goal (user_id, kcal_goal)
               VALUES (?, ?)
               ON CONFLICT (user_id) DO UPDATE SET kcal_goal = EXCLUDED.kcal_goal""",
            (user_id, kcal_goal),
        )


# ── Résultats d'analyse nutrition (insights / recommandations du NutritionAgent) ─

def save_nutrition_analysis(user_id: str, score: float, insights: list,
                            recommendations: list, anomalies: list) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO nutrition_analysis
                   (user_id, score, insights, recommendations, anomalies, updated_at)
               VALUES (?, ?, ?, ?, ?, NOW())
               ON CONFLICT (user_id) DO UPDATE SET
                   score           = EXCLUDED.score,
                   insights        = EXCLUDED.insights,
                   recommendations = EXCLUDED.recommendations,
                   anomalies       = EXCLUDED.anomalies,
                   updated_at      = EXCLUDED.updated_at""",
            (user_id, round(float(score), 1),
             json.dumps(insights or [], ensure_ascii=False),
             json.dumps(recommendations or [], ensure_ascii=False),
             json.dumps(anomalies or [], ensure_ascii=False)),
        )


def get_nutrition_analysis(user_id: str) -> Optional[dict]:
    with _connect() as conn:
        conn.execute(
            """SELECT score, insights, recommendations, anomalies, updated_at
               FROM nutrition_analysis WHERE user_id = ?""",
            (user_id,),
        )
        row = conn.fetchone()
    if not row:
        return None
    def _load(v):
        try:
            return json.loads(v) if v else []
        except (TypeError, ValueError):
            return []
    return {
        "score":           row["score"],
        "insights":        _load(row["insights"]),
        "recommendations": _load(row["recommendations"]),
        "anomalies":       _load(row["anomalies"]),
        "updated_at":      row["updated_at"].isoformat() if row["updated_at"] else None,
    }
