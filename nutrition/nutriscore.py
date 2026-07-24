"""
LifeAI — Calcul du Nutri-Score (barème officiel 2017).

CIQUAL ne fournit pas la note, mais toutes les colonnes nécessaires. On la calcule
ici, à l'import, pour l'afficher façon YAZIO (badge A–E).

Isolé et testable : si l'ANSES fournit un jour la note directement, on remplace
juste ce module.
"""

from __future__ import annotations


def _points(value: float, thresholds: list[float]) -> int:
    """Nombre de seuils dépassés (barème par paliers Nutri-Score)."""
    p = 0
    for t in thresholds:
        if value > t:
            p += 1
        else:
            break
    return p


# ── Points négatifs (N) ───────────────────────────────────────────────────────
_ENERGY_SOLID = [335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350]   # kJ
_SUGAR_SOLID  = [4.5, 9, 13.5, 18, 22.5, 27, 31, 36, 40, 45]                  # g
_SATFAT       = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]                              # g
_SODIUM       = [90, 180, 270, 360, 450, 540, 630, 720, 810, 900]            # mg
_ENERGY_BEV   = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270]                # kJ
_SUGAR_BEV    = [0, 1.5, 3, 4.5, 6, 7.5, 9, 10.5, 12, 13.5]                  # g

# ── Points positifs (P) ───────────────────────────────────────────────────────
_FIBER   = [0.9, 1.9, 2.8, 3.7, 4.7]   # 0..5
_PROTEIN = [1.6, 3.2, 4.8, 6.4, 8.0]   # 0..5


def _fruitveg_points(pct: float, beverage: bool) -> int:
    if beverage:
        if pct > 80: return 10
        if pct > 60: return 4
        if pct > 40: return 2
        return 0
    if pct > 80: return 5
    if pct > 60: return 2
    if pct > 40: return 1
    return 0


def compute_grade(energy_kj, sugars_g, sat_fat_g, sodium_mg, fiber_g, protein_g,
                  fruit_veg_pct: float = 0.0, is_beverage: bool = False,
                  is_water: bool = False) -> str:
    """
    Retourne la lettre Nutri-Score 'A'..'E'. Les valeurs None/négatives sont
    traitées comme 0 (fréquent dans CIQUAL : '-', 'traces', etc.).
    """
    def v(x):
        return x if (x is not None and x >= 0) else 0.0

    energy_kj, sugars_g, sat_fat_g = v(energy_kj), v(sugars_g), v(sat_fat_g)
    sodium_mg, fiber_g, protein_g = v(sodium_mg), v(fiber_g), v(protein_g)

    if is_water:
        return 'A'

    if is_beverage:
        n = (_points(energy_kj, _ENERGY_BEV) + _points(sugars_g, _SUGAR_BEV)
             + _points(sat_fat_g, _SATFAT) + _points(sodium_mg, _SODIUM))
    else:
        n = (_points(energy_kj, _ENERGY_SOLID) + _points(sugars_g, _SUGAR_SOLID)
             + _points(sat_fat_g, _SATFAT) + _points(sodium_mg, _SODIUM))

    fvp     = _fruitveg_points(fruit_veg_pct, is_beverage)
    fiber_p = _points(fiber_g, _FIBER)
    prot_p  = _points(protein_g, _PROTEIN)

    # Règle protéines : si N>=11 et fruits/légumes < 5 pts (solides), on n'ajoute
    # pas les points protéines.
    if n >= 11 and fvp < 5 and not is_beverage:
        p = fiber_p + fvp
    else:
        p = fiber_p + fvp + prot_p

    score = n - p

    if is_beverage:
        if score <= 1: return 'B'
        if score <= 5: return 'C'
        if score <= 9: return 'D'
        return 'E'

    if score <= -1: return 'A'
    if score <= 2:  return 'B'
    if score <= 10: return 'C'
    if score <= 18: return 'D'
    return 'E'
