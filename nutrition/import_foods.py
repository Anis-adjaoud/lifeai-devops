"""
LifeAI — Import de la table CIQUAL vers Postgres.

Lit `data/foods_table.xlsx` (table CIQUAL ANSES, **LECTURE SEULE** — jamais
modifiée) en stdlib (`zipfile` + XML, sans dépendance `openpyxl`), nettoie les
valeurs françaises, calcule le Nutri-Score, et remplit la table `foods` si elle
est vide.

Mapping des colonnes (entêtes CIQUAL FR figées) :
  G alim_code · H alim_nom_fr · D groupe · E sous-groupe · J énergie kJ ·
  K énergie kcal · P protéines (N×6.25) · Q glucides · R lipides · S sucres ·
  AA fibres · AF AG saturés · AX sel · BI sodium
"""

from __future__ import annotations

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from nutrition import nutriscore
from nutrition import nutrition_store

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_XLSX = Path(__file__).resolve().parent.parent / "data" / "foods_table.xlsx"

# Proxy « ultra-transformé » (CIQUAL n'a pas le groupe NOVA)
_PROCESSED_GROUPS = {
    "produits sucrés",
    "glaces et sorbets",
    "entrées et plats composés",
}
_FRUITVEG_GROUP = "fruits, légumes, légumineuses et oléagineux"
_BEVERAGE_GROUP = "eaux et autres boissons"


def _num(s):
    """Convertit une cellule CIQUAL en float, ou None (gère virgule, <, traces…)."""
    if s is None:
        return None
    s = str(s).strip()
    if s in ("", "-", "traces", "nd", "n/a", "ND"):
        return None
    s = s.replace("<", "").replace(">", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return None


def read_ciqual() -> list[dict]:
    """Parse le xlsx et retourne la liste des aliments normalisés (prêts pour `foods`)."""
    z = zipfile.ZipFile(_XLSX)
    shared: list[str] = []
    ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
    for si in ss.iter(_NS + "si"):
        shared.append("".join(t.text or "" for t in si.iter(_NS + "t")))
    sh = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = list(sh.iter(_NS + "row"))

    def cell(c):
        v = c.find(_NS + "v")
        if v is None:
            return ""
        return shared[int(v.text)] if c.get("t") == "s" else v.text

    def rowmap(r):
        d = {}
        for c in r.findall(_NS + "c"):
            col = "".join(ch for ch in c.get("r") if ch.isalpha())
            d[col] = cell(c)
        return d

    foods = []
    for r in rows[1:]:
        d = rowmap(r)
        code = (d.get("G") or "").strip()
        name = (d.get("H") or "").strip()
        kcal = _num(d.get("K"))
        if not code or not name or kcal is None:
            continue

        group    = (d.get("D") or "").strip()
        subgroup = (d.get("E") or "").strip()
        energy_kj = _num(d.get("J"))
        protein   = _num(d.get("P"))
        carbs     = _num(d.get("Q"))
        fat       = _num(d.get("R"))
        sugars    = _num(d.get("S"))
        fiber     = _num(d.get("AA"))
        satfat    = _num(d.get("AF"))
        salt      = _num(d.get("AX"))
        sodium    = _num(d.get("BI"))
        if sodium is None and salt is not None:
            sodium = salt * 400.0   # 1 g de sel ≈ 400 mg de sodium

        is_bev   = group == _BEVERAGE_GROUP
        is_water = is_bev and "eau" in subgroup.lower() and (kcal or 0) < 5
        fvp      = 85.0 if group == _FRUITVEG_GROUP else 0.0

        grade = nutriscore.compute_grade(
            energy_kj if energy_kj is not None else kcal * 4.184,
            sugars, satfat, sodium, fiber, protein,
            fruit_veg_pct=fvp, is_beverage=is_bev, is_water=is_water,
        )

        foods.append({
            "code":         code,
            "name":         name,
            "category":     group,
            "kcal_100g":    kcal,
            "protein_100g": protein or 0.0,
            "carbs_100g":   carbs or 0.0,
            "fat_100g":     fat or 0.0,
            "fiber_100g":   fiber or 0.0,
            "nutriscore":   grade,
            "processed":    group in _PROCESSED_GROUPS,
        })
    return foods


def seed_foods_if_empty() -> int:
    """Remplit la table `foods` depuis CIQUAL si elle est vide (idempotent)."""
    if nutrition_store.foods_count() > 0:
        return 0
    foods = read_ciqual()
    nutrition_store.bulk_insert_foods(foods)
    print(f"[foods] Seed CIQUAL : {len(foods)} aliments importés", flush=True)
    return len(foods)
