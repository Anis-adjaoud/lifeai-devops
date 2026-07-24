"""
agents/llm_client.py — Client Groq partagé entre tous les agents.

Utilise llama-3.1-8b-instant pour les agents spécialisés (rapide, économique)
et laisse le ChiefAgent choisir son propre modèle (llama-3.3-70b-versatile).
"""

import os
import json
from pathlib import Path

_ENV_FILE = Path(__file__).parent.parent / ".env"
_client = None


def get_api_key() -> str | None:
    """
    Lit GROQ_API_KEY depuis os.environ, puis directement depuis .env si absent.
    Robuste quel que soit l'entry point (main.py, notebook, import direct).
    """
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        from dotenv import dotenv_values
        return dotenv_values(_ENV_FILE).get("GROQ_API_KEY")
    except ImportError:
        pass
    # Lecture manuelle du .env en dernier recours
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            if line.startswith("GROQ_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def _get_groq():
    global _client
    if _client is None:
        from groq import Groq
        _client = Groq(api_key=get_api_key())
    return _client


def ask_json(prompt: str, model: str = "llama-3.1-8b-instant", max_tokens: int = 600) -> dict | None:
    """
    Envoie un prompt à Groq et retourne le JSON parsé, ou None en cas d'échec.
    Extrait le premier objet JSON valide même si le LLM ajoute du texte autour.
    """
    try:
        response = _get_groq().chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()

        # Retire les blocs markdown ```json ... ```
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                if part.startswith("json"):
                    raw = part[4:].strip()
                    break
                if part.strip().startswith("{"):
                    raw = part.strip()
                    break

        # Extrait le premier objet JSON {...} complet, ignore le texte autour
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            raw = raw[start:end]

        return json.loads(raw)
    except Exception as e:
        print(f"[llm_client] ⚠ {e}")
        return None
