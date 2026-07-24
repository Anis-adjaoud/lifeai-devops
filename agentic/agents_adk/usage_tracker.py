"""
LifeAI ADK — Suivi tokens/temps consommés par requête (analyse ou message de chat).

Sert de baseline avant optimisation (contextes/instructions plus courts, modèles
différents par agent, etc.) : on mesure ce qui est réellement consommé aujourd'hui
pour pouvoir chiffrer le gain plus tard.

Piège ADK : un agent délégué via AgentTool (ex. chief_agent -> nutrition_agent) tourne
dans son propre Runner interne dont les events ne remontent PAS au Runner du dessus
(agent_tool.py crée un `Runner(...)` local et n'en yield jamais les events). On ne peut
donc pas se contenter d'inspecter les events du Runner de premier niveau dans pipeline.py.
En revanche, `after_model_callback` est attaché à chaque LlmAgent lui-même : il se
déclenche quel que soit le Runner qui l'exécute. C'est donc le seul point qui voit tous
les appels LLM d'une requête, chief + sous-agents confondus.
"""

from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field


@dataclass
class UsageStats:
    started_at: float = field(default_factory=time.perf_counter)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thoughts_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    per_agent: dict[str, dict[str, int]] = field(default_factory=dict)

    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self.started_at

    def to_dict(self) -> dict:
        return {
            "elapsed_seconds": round(self.elapsed_seconds(), 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "thoughts_tokens": self.thoughts_tokens,
            "cached_tokens": self.cached_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "per_agent": self.per_agent,
        }


# ContextVar : isolé par requête même sous asyncio.gather (chaque Task copie le contexte)
_current: contextvars.ContextVar[UsageStats | None] = contextvars.ContextVar(
    "lifeai_usage_stats", default=None
)


def start_tracking() -> UsageStats:
    """À appeler en tout début de `_run_async` / `send_chat_message`."""
    stats = UsageStats()
    _current.set(stats)
    return stats


def log_model_response(callback_context, llm_response) -> None:
    """after_model_callback à attacher à CHAQUE LlmAgent (chief + sous-agents + agents d'action)."""
    stats = _current.get()
    usage = getattr(llm_response, "usage_metadata", None)
    if stats is None or usage is None:
        return None

    prompt = usage.prompt_token_count or 0
    completion = usage.candidates_token_count or 0
    thoughts = usage.thoughts_token_count or 0
    cached = usage.cached_content_token_count or 0
    total = usage.total_token_count or (prompt + completion + thoughts)

    stats.prompt_tokens += prompt
    stats.completion_tokens += completion
    stats.thoughts_tokens += thoughts
    stats.cached_tokens += cached
    stats.total_tokens += total
    stats.llm_calls += 1

    entry = stats.per_agent.setdefault(
        callback_context.agent_name,
        {"prompt": 0, "completion": 0, "thoughts": 0, "cached": 0, "total": 0, "calls": 0},
    )
    entry["prompt"] += prompt
    entry["completion"] += completion
    entry["thoughts"] += thoughts
    entry["cached"] += cached
    entry["total"] += total
    entry["calls"] += 1
    return None
