"""
Tests du calcul Nutri-Score (nutrition/nutriscore.py).

Calcul purement arithmétique, sans dépendance : le candidat idéal pour des
tests unitaires. Les valeurs nutritionnelles utilisées ici sont celles de la
base CIQUAL, pour 100 g de produit.
"""
import pytest

from nutrition.nutriscore import compute_grade


# (libellé, arguments, note attendue)
CAS_DE_REFERENCE = [
    (
        "eau",
        dict(energy_kj=0, sugars_g=0, sat_fat_g=0, sodium_mg=0,
             fiber_g=0, protein_g=0, is_water=True),
        "A",
    ),
    (
        "brocoli",
        dict(energy_kj=147, sugars_g=1.7, sat_fat_g=0.1, sodium_mg=30,
             fiber_g=2.6, protein_g=2.8, fruit_veg_pct=100),
        "A",
    ),
    (
        "soda sucré",
        dict(energy_kj=180, sugars_g=10.6, sat_fat_g=0, sodium_mg=10,
             fiber_g=0, protein_g=0, is_beverage=True),
        "E",
    ),
    (
        "chips",
        dict(energy_kj=2200, sugars_g=0.6, sat_fat_g=3.5, sodium_mg=540,
             fiber_g=4.3, protein_g=6.4),
        "C",
    ),
]


@pytest.mark.parametrize(
    "arguments,note_attendue",
    [pytest.param(a, n, id=libelle) for libelle, a, n in CAS_DE_REFERENCE],
)
def test_notes_de_reference(arguments, note_attendue):
    assert compute_grade(**arguments) == note_attendue


def test_le_soda_est_moins_bien_note_que_l_eau():
    eau = compute_grade(energy_kj=0, sugars_g=0, sat_fat_g=0, sodium_mg=0,
                        fiber_g=0, protein_g=0, is_water=True)
    soda = compute_grade(energy_kj=180, sugars_g=10.6, sat_fat_g=0, sodium_mg=10,
                         fiber_g=0, protein_g=0, is_beverage=True)

    assert eau < soda, "A doit être mieux noté que E (ordre alphabétique croissant)"


@pytest.mark.parametrize("valeur_manquante", [None, -1])
def test_valeurs_absentes_ou_negatives_sont_traitees_comme_zero(valeur_manquante):
    """CIQUAL utilise '-' ou 'traces' pour de nombreux nutriments : après
    conversion, ces champs arrivent à None ou en négatif. Le calcul doit rester
    exploitable au lieu de lever une exception."""
    note = compute_grade(
        energy_kj=valeur_manquante,
        sugars_g=valeur_manquante,
        sat_fat_g=valeur_manquante,
        sodium_mg=valeur_manquante,
        fiber_g=valeur_manquante,
        protein_g=valeur_manquante,
    )

    assert note in {"A", "B", "C", "D", "E"}


def test_la_note_est_toujours_une_lettre_valide():
    """Balayage large : aucune combinaison ne doit produire de note hors A-E."""
    for energie in (0, 500, 1500, 3000):
        for sucres in (0, 10, 50):
            for sel in (0, 300, 900):
                note = compute_grade(
                    energy_kj=energie, sugars_g=sucres, sat_fat_g=5,
                    sodium_mg=sel, fiber_g=2, protein_g=5,
                )
                assert note in {"A", "B", "C", "D", "E"}
