"""
LifeAI — Extraction d'aliments depuis un message de chat + enregistrement au journal.

Même principe que le formulaire, mais en langage naturel : quand l'utilisateur
mentionne un plat / repas dans le chat (« j'ai mangé une pomme ce midi »), on
extrait les aliments consommés via un LLM (Gemini), on les matche à la base CIQUAL
locale (nutrition_store.search_foods) et on les enregistre au journal
(nutrition_store.add_log).

Robuste par conception : `extract_and_log` n'échoue jamais (retourne [] en cas de
problème LLM/DB) pour ne pas casser la réponse du chat.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from nutrition import nutrition_store

_MEALS = set(nutrition_store.MEALS)   # breakfast | lunch | dinner | snack

# Repas français éventuellement renvoyés par le LLM → clés internes
_MEAL_FR = {
    "petit-déjeuner": "breakfast", "petit dejeuner": "breakfast", "matin": "breakfast",
    "déjeuner": "lunch", "dejeuner": "lunch", "midi": "lunch",
    "dîner": "dinner", "diner": "dinner", "soir": "dinner",
    "collation": "snack", "snack": "snack", "goûter": "snack", "gouter": "snack",
}

_MODEL = os.environ.get("FOOD_EXTRACT_MODEL", "gemini-2.5-flash")

_SYSTEM = (
    "Tu extrais uniquement les aliments et boissons que l'utilisateur dit avoir "
    "CONSOMMÉS (mangés ou bus), au passé ou au présent, en français.\n"
    "Règles STRICTES :\n"
    "- Ignore les questions (ex: « combien de calories dans une pomme ? »), les "
    "intentions futures (« je vais manger »), les envies, les recettes générales.\n"
    "- Pour chaque aliment consommé : donne un nom générique SIMPLE en français, de "
    "préférence l'ingrédient principal en un mot (ex: « pomme », « poulet », « riz », "
    "« café »).\n"
    "- quantity_g : quantité en grammes (estime une portion réaliste si non précisée).\n"
    "- meal ∈ {breakfast, lunch, dinner, snack} si le moment est mentionné, sinon null.\n"
    "- Si aucun aliment consommé n'est mentionné : liste vide.\n"
    'Réponds UNIQUEMENT en JSON, format exact : '
    '{"items":[{"food":"pomme","quantity_g":150,"meal":"lunch"}]}'
)


def _infer_meal(now: datetime | None = None) -> str:
    """Repas déduit de l'heure locale quand l'utilisateur ne le précise pas."""
    h = (now or datetime.now()).hour
    if h < 11:  return "breakfast"
    if h < 15:  return "lunch"
    if h < 18:  return "snack"
    if h < 23:  return "dinner"
    return "snack"


def _normalize_meal(meal) -> str | None:
    if not meal:
        return None
    m = str(meal).strip().lower()
    if m in _MEALS:
        return m
    return _MEAL_FR.get(m)


def _llm_extract(text: str, already_logged: list[dict] | None = None) -> list[dict]:
    """Appelle Gemini en mode JSON et renvoie la liste brute d'items (ou [])."""
    from google import genai

    system_instruction = _SYSTEM

    # Contexte anti-doublon : aliments déjà enregistrés aujourd'hui.
    if already_logged:
        listing = "; ".join(
            f"{a['name']} ({a['meal']})" for a in already_logged if a.get("name")
        )
        if listing:
            system_instruction += (
                "\n\nAliments DÉJÀ enregistrés aujourd'hui : " + listing + ".\n"
                "Ne renvoie PAS un aliment déjà enregistré si l'utilisateur ne fait "
                "que le commenter, le décrire ou en reparler. Renvoie-le UNIQUEMENT "
                "s'il s'agit clairement d'une NOUVELLE prise (autre moment/repas, ou "
                "mots comme « encore », « une autre », « j'ai repris », « à nouveau »)."
            )

    client = genai.Client()
    resp = client.models.generate_content(
        model=_MODEL,
        contents=text,
        config={
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "temperature": 0,
            "max_output_tokens": 500,
        },
    )
    raw = resp.text or "{}"
    data = json.loads(raw)
    items = data.get("items", []) if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def _todays_logged(user_id: str) -> list[dict]:
    """Aliments déjà enregistrés aujourd'hui : [{name, code, meal}]."""
    try:
        diary = nutrition_store.get_diary(user_id)
    except Exception:
        return []
    out = []
    for meal, mdata in diary.get("meals", {}).items():
        for e in mdata.get("entries", []):
            if e.get("name"):
                out.append({"name": e["name"], "code": e.get("food_code"), "meal": meal})
    return out


def extract_and_log(user_id: str, text: str) -> list[dict]:
    """
    Extrait les aliments consommés mentionnés dans `text`, les matche à CIQUAL et
    les enregistre au journal du jour. Retourne la liste de ce qui a été traité
    (matched=True avec détails, ou matched=False si aliment introuvable en base).
    Ne lève jamais d'exception.
    """
    if not text or len(text.strip()) < 3:
        return []

    already = _todays_logged(user_id)
    try:
        items = _llm_extract(text, already)
    except Exception as e:
        print(f"[food_extract] LLM erreur : {e}", flush=True)
        return []

    # Garde-fou anti-doublon : même aliment déjà présent au même repas non réenregistré
    seen_keys = {(a["code"], a["meal"]) for a in already if a.get("code")}

    logged: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        food = str(it.get("food") or "").strip()
        if not food:
            continue

        try:
            qty = float(it.get("quantity_g") or 100)
        except (TypeError, ValueError):
            qty = 100.0
        qty = max(1.0, min(qty, 2000.0))

        meal = _normalize_meal(it.get("meal")) or _infer_meal()

        # Match CIQUAL : nom complet, sinon repli sur le mot principal
        try:
            matches = nutrition_store.search_foods(food, limit=1)
            if not matches:
                first = food.split()[0] if food.split() else ""
                if first and first.lower() != food.lower():
                    matches = nutrition_store.search_foods(first, limit=1)
        except Exception as e:
            print(f"[food_extract] recherche CIQUAL erreur : {e}", flush=True)
            matches = []

        if not matches:
            logged.append({"matched": False, "query": food})
            continue

        m = matches[0]

        # Anti-doublon : déjà cet aliment à ce repas aujourd'hui → on n'ajoute pas.
        key = (m["code"], meal)
        if key in seen_keys:
            logged.append({"matched": False, "duplicate": True,
                           "query": food, "name": m["name"], "meal": meal})
            continue

        try:
            entry_id = nutrition_store.add_log(user_id, meal, m["code"], qty)
        except Exception as e:
            print(f"[food_extract] add_log erreur : {e}", flush=True)
            continue
        seen_keys.add(key)   # évite aussi les doublons dans le même message

        logged.append({
            "matched": True,
            "id": entry_id,
            "query": food,
            "name": m["name"],
            "meal": meal,
            "quantity_g": qty,
            "kcal": round((m.get("kcal_100g") or 0) * qty / 100),
            "nutriscore": m.get("nutriscore"),
            "is_liquid": m.get("is_liquid", False),
        })

    return logged
