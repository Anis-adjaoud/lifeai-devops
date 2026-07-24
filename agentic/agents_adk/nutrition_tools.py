"""
nutrition_tools.py — Recherche CIQUAL (base nutritionnelle officielle française)
exposée comme tool ADK pour l'agent nutrition.
"""

import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd


# ── Configuration ─────────────────────────────────────────────────────────────

# Le fichier CIQUAL est dans data/ à la racine du projet
_PROJECT_ROOT = Path(__file__).parent.parent.parent
CHEMIN_CIQUAL = _PROJECT_ROOT / "data" / "foods_table.xlsx"
DOSSIER_CACHE = _PROJECT_ROOT / "data" / ".cache_embeddings"
DOSSIER_CACHE.mkdir(exist_ok=True)

NOM_MODELE_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"

POIDS_SEMANTIQUE = 0.6
POIDS_TEXTUEL = 0.4

# Seuil en dessous duquel un résultat CIQUAL est jugé non pertinent
SEUIL_PERTINENCE_CIQUAL = 0.8

# Motifs calibrés sur les vrais en-têtes CIQUAL 2025 (colonnes officielles UE,
# pas la méthode Jones qui existe aussi dans le fichier).
COLONNES_MACROS = {
    "energie_kcal_100g": r"energie.*reglement.*kcal.*100\s*g",
    "proteines_100g": r"proteines.*n\s*x\s*6[.,]25.*100\s*g",
    "glucides_100g": r"glucides.*100\s*g",
    "lipides_100g": r"lipides.*100\s*g",
}


# ── Nettoyage / normalisation ─────────────────────────────────────────────────

def _nettoyer_valeur(val) -> float:
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    val = str(val).strip().lower()
    if val in ("-", "traces", "< 0.1", "< 0,1", ""):
        return 0.0
    try:
        return float(val.replace(",", "."))
    except ValueError:
        return 0.0


def _normaliser_nom_colonne(nom: str) -> str:
    """Normalise un nom de COLONNE : sans accents, minuscule, espaces normalisés (gère les \\n internes)."""
    nom = unicodedata.normalize("NFKD", str(nom))
    nom = "".join(c for c in nom if not unicodedata.combining(c))
    nom = re.sub(r"\s+", " ", nom).strip().lower()
    return nom


def _normaliser_texte(texte: str) -> str:
    """Normalise un texte de RECHERCHE (nom d'aliment / requête utilisateur) : sans accents, minuscule."""
    texte = unicodedata.normalize("NFKD", str(texte))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return texte.lower().strip()


def _trouver_colonne(df: pd.DataFrame, motif: str) -> str | None:
    for col in df.columns:
        if re.search(motif, _normaliser_nom_colonne(col)):
            return col
    return None


def _hash_fichier(chemin: Path) -> str:
    """Hash rapide basé sur taille + date de modif (pas le contenu entier, trop lourd)."""
    stat = chemin.stat()
    return hashlib.md5(f"{stat.st_size}-{stat.st_mtime}".encode()).hexdigest()[:12]


def _meilleur_score_mot(requete_norm: str, nom_norm: str) -> float:
    """
    Compare la requête à chaque mot du nom (pas à la chaîne entière),
    pour éviter que les noms longs (ex: "banane, pulpe, crue, france")
    soient pénalisés par leur longueur face à une requête courte comme "banane".
    """
    mots = [m for m in re.split(r"[^a-z0-9]+", nom_norm) if m]
    if not mots:
        return 0.0

    for mot in mots:
        if requete_norm in mot or mot in requete_norm:
            return max(0.95, SequenceMatcher(None, requete_norm, mot).ratio())

    return max(SequenceMatcher(None, requete_norm, mot).ratio() for mot in mots)


# ── Embeddings ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _charger_modele_embedding():
    """Charge le modèle une seule fois par process."""
    from sentence_transformers import SentenceTransformer
    print(f"[CIQUAL] Chargement du modèle d'embeddings ({NOM_MODELE_EMBEDDING})...", flush=True)
    return SentenceTransformer(NOM_MODELE_EMBEDDING)


def _calculer_embeddings(noms: list[str]) -> np.ndarray:
    """
    Calcule les embeddings pour une liste de noms d'aliments.
    -> Point d'extension : remplace ce corps par un appel à ton MODEL / API
       d'embeddings si tu n'utilises pas sentence-transformers.
    """
    modele = _charger_modele_embedding()
    embeddings = modele.encode(
        noms,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,  # normalisés -> produit scalaire = cosinus
    )
    return np.asarray(embeddings, dtype=np.float32)


@lru_cache(maxsize=2048)
def _embedding_requete_cache(requete_utilisateur: str) -> np.ndarray:
    """Cache l'embedding d'une requête utilisateur (clé = texte exact envoyé au modèle)."""
    return _calculer_embeddings([requete_utilisateur])[0]


def _charger_ou_calculer_embeddings(df: pd.DataFrame, chemin_ciqual: Path) -> np.ndarray:
    """Charge les embeddings depuis le cache disque, ou les calcule et les sauvegarde."""
    cle_cache = DOSSIER_CACHE / f"embeddings_{_hash_fichier(chemin_ciqual)}.npy"

    if cle_cache.exists():
        print(f"[CIQUAL] Embeddings chargés depuis le cache ({cle_cache.name}).", flush=True)
        return np.load(cle_cache)

    print("[CIQUAL] Aucun cache trouvé, calcul des embeddings CIQUAL (une seule fois ~2 min)...", flush=True)
    embeddings = _calculer_embeddings(df["alim_nom_fr"].tolist())
    np.save(cle_cache, embeddings)
    print("[CIQUAL] Embeddings sauvegardés dans le cache.", flush=True)
    return embeddings


# ── Chargement de la table CIQUAL ────────────────────────────────────────────

@lru_cache(maxsize=1)
def charger_ciqual(chemin: str = str(CHEMIN_CIQUAL)) -> pd.DataFrame:
    """Charge et nettoie la base CIQUAL une seule fois (mise en cache mémoire)."""
    chemin_path = Path(chemin)
    if not chemin_path.exists():
        raise FileNotFoundError(f"Fichier CIQUAL introuvable : {chemin_path}")

    print(f"[CIQUAL] Chargement de la base ({chemin_path.name})...", flush=True)
    df = pd.read_excel(chemin_path, engine="openpyxl")

    if "alim_nom_fr" not in df.columns:
        raise ValueError(
            "Colonne 'alim_nom_fr' absente. Colonnes disponibles : "
            f"{list(df.columns)}"
        )

    colonnes_resolues = {}
    for nom_canonique, motif in COLONNES_MACROS.items():
        vraie_colonne = _trouver_colonne(df, motif)
        if vraie_colonne:
            df[vraie_colonne] = df[vraie_colonne].apply(_nettoyer_valeur)
            colonnes_resolues[nom_canonique] = vraie_colonne
        else:
            print(f"[CIQUAL] Colonne '{nom_canonique}' non trouvee (motif: {motif})", flush=True)

    df.attrs["colonnes_resolues"] = colonnes_resolues
    df["_alim_nom_norm"] = df["alim_nom_fr"].apply(_normaliser_texte)
    df.attrs["embeddings"] = _charger_ou_calculer_embeddings(df, chemin_path)

    print(f"[CIQUAL] Base chargee : {len(df)} aliments, colonnes={list(colonnes_resolues)}", flush=True)
    return df


# ── Recherche hybride ─────────────────────────────────────────────────────────

def rechercher_aliments_ciqual(
    requete_utilisateur: str,
    top_k: int = 3,
    mode: str = "hybride",  # "hybride" | "semantique" | "textuel"
) -> list[dict]:
    """
    Recherche les aliments CIQUAL les plus proches de la requête.
    - "textuel"   : similarité mot-à-mot (rapide, tolère les fautes de frappe)
    - "semantique": similarité d'embeddings (comprend les reformulations)
    - "hybride"   : combine les deux (recommandé)
    """
    df = charger_ciqual()
    colonnes = df.attrs.get("colonnes_resolues", {})
    requete_norm = _normaliser_texte(requete_utilisateur)

    score_textuel = df["_alim_nom_norm"].apply(
        lambda nom: _meilleur_score_mot(requete_norm, nom)
    )

    if mode == "textuel":
        score_final = score_textuel
    else:
        embeddings = df.attrs["embeddings"]
        embedding_requete = _embedding_requete_cache(requete_utilisateur)
        score_semantique = embeddings @ embedding_requete  # cosinus (vecteurs normalisés)

        if mode == "semantique":
            score_final = pd.Series(score_semantique, index=df.index)
        else:  # hybride
            score_final = (
                POIDS_SEMANTIQUE * score_semantique + POIDS_TEXTUEL * score_textuel
            )

    df_resultats = df.copy()
    df_resultats["_score"] = score_final
    df_resultats = df_resultats.sort_values("_score", ascending=False).head(top_k)

    aliments = []
    for _, ligne in df_resultats.iterrows():
        aliment = {
            "nom": ligne["alim_nom_fr"],
            "score": round(float(ligne["_score"]), 4),
        }
        for nom_canonique, vraie_colonne in colonnes.items():
            aliment[nom_canonique] = ligne.get(vraie_colonne, 0.0)
        aliments.append(aliment)

    return aliments


# ── Tool exposé à l'agent ADK ─────────────────────────────────────────────────

def rechercher_aliment_ciqual_tool(nom_aliment: str) -> dict:
    """
    Recherche un aliment dans la base CIQUAL (base nutritionnelle officielle française)
    par similarité vectorielle/textuelle hybride.

    Args:
        nom_aliment: nom de l'aliment à rechercher (ex: "banane", "blanc de poulet grillé")

    Returns:
        dict avec:
        - "pertinent": bool, True si au moins un résultat dépasse le seuil de confiance
        - "resultats": liste des aliments trouvés (nom + valeurs macro + score)
        - "message": indication pour l'agent sur la conduite à tenir
    """
    resultats = rechercher_aliments_ciqual(nom_aliment, top_k=3, mode="hybride")

    if not resultats or resultats[0]["score"] < SEUIL_PERTINENCE_CIQUAL:
        return {
            "pertinent": False,
            "resultats": resultats,
            "message": (
                "Aucun résultat suffisamment fiable trouvé dans la base CIQUAL "
                f"pour '{nom_aliment}'. Utilise tes propres connaissances nutritionnelles "
                "pour répondre, et précise clairement à l'utilisateur que cette estimation "
                "ne provient pas de la base CIQUAL officielle."
            ),
        }

    return {
        "pertinent": True,
        "resultats": resultats,
        "message": (
            f"Résultat CIQUAL fiable trouvé : '{resultats[0]['nom']}'. "
            "Utilise ces valeurs officielles en priorité pour ta réponse."
        ),
    }
