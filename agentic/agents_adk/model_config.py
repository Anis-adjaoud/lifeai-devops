"""
LifeAI — Configuration des modèles LLM.
Deux niveaux : MODEL_CHIEF pour l'orchestrateur (function-calling multi-étapes,
contrat JSON strict), MODEL_LIGHT pour les agents spécialistes (1 outil + réponse
courte de 2-4 phrases, pas de raisonnement multi-étapes).
"""

from google.adk.models.lite_llm import LiteLlm

# MODEL = LiteLlm(model="groq/llama-3.1-8b-instant")             # Groq   — 6 000 TPM gratuit (gemma2-9b-it decommissione par Groq)

# MODEL = LiteLlm(model="groq/meta-llama/llama-prompt-guard-2-22m")
# MODEL = LiteLlm(model="groq/gemma2-9b-it")                  # DECOMMISSIONE (juil. 2026) -- ne plus utiliser
MODEL_CHIEF = "gemini-2.5-flash"                             # Google — nécessite billing
MODEL_LIGHT = "gemini-2.5-flash-lite"                        # Google — moins cher/rapide, agents à tâche unique
# MODEL = LiteLlm(model="anthropic/claude-haiku-4-5-20251001") # Anthropic — nécessite crédits
