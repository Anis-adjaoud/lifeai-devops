"""
LifeAI — Agents ADK (Google Agent Development Kit)
Remplace l'orchestrateur custom par ParallelAgent + SequentialAgent natifs ADK.

Convention ADK : root_agent est exposé ici pour que `adk run` et `adk web` fonctionnent.
  adk run agents_adk        → terminal interactif
  adk web                   → UI web sur localhost:8000
"""

from .agent import root_agent
from .pipeline import run

__all__ = ["root_agent", "run"]