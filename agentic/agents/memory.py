"""
LifeAI — Mémoire Long-Terme
Persiste le profil utilisateur, l'historique des scores et les patterns détectés.
Utilisé par le Chief Agent pour adapter les recommandations dans le temps.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path


class LongTermMemory:
    """
    Mémoire persistante de l'utilisateur.

    Structure JSON :
    {
      "user_profile": { ... },
      "history": [ { date, scores, global_score } ... ],
      "patterns": [ { type, description, detected_at, occurrences } ... ],
      "coaching_context": { last_advice, goals, preferences }
    }
    """

    def __init__(self, memory_path: str = "memory/user_memory.json"):
        self.path = Path(memory_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path, "r") as f:
                return json.load(f)
        return {
            "user_profile": {},
            "history": [],
            "patterns": [],
            "coaching_context": {
                "last_advice": [],
                "goals": [],
                "preferences": {}
            }
        }

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False, default=str)

    # ── Profil utilisateur ─────────────────────────────────────────────────────

    def update_profile(self, **kwargs):
        self._data["user_profile"].update(kwargs)
        self.save()

    def get_profile(self) -> dict:
        return self._data["user_profile"]

    # ── Historique des scores ──────────────────────────────────────────────────

    def add_session(self, scores: dict, global_score: float, date: str = None):
        """Ajoute une session d'analyse à l'historique."""
        entry = {
            "date": date or datetime.now().isoformat(),
            "global_score": round(global_score, 1),
            "scores": {k: round(v, 1) for k, v in scores.items()},
        }
        self._data["history"].append(entry)
        # Garde les 90 dernières sessions
        self._data["history"] = self._data["history"][-90:]
        self.save()

    def get_history(self, days: int = 30) -> list[dict]:
        """Retourne l'historique des N derniers jours."""
        cutoff = datetime.now() - timedelta(days=days)
        result = []
        for entry in self._data["history"]:
            try:
                entry_date = datetime.fromisoformat(entry["date"])
                if entry_date >= cutoff:
                    result.append(entry)
            except Exception:
                result.append(entry)
        return result

    def get_score_trend(self, metric: str = "global_score", window: int = 7) -> Optional[str]:
        """Calcule la tendance (hausse / baisse / stable) sur les N dernières sessions."""
        history = self.get_history(days=window * 2)
        if len(history) < 4:
            return None
        recent = [h.get("scores", {}).get(metric, h.get("global_score")) for h in history[-window:]]
        older  = [h.get("scores", {}).get(metric, h.get("global_score")) for h in history[:window]]
        recent = [x for x in recent if x is not None]
        older  = [x for x in older  if x is not None]
        if not recent or not older:
            return None
        avg_recent = sum(recent) / len(recent)
        avg_older  = sum(older)  / len(older)
        delta = avg_recent - avg_older
        if delta > 3:
            return f"↑ en hausse (+{delta:.1f} pts sur {window}j)"
        elif delta < -3:
            return f"↓ en baisse ({delta:.1f} pts sur {window}j)"
        return f"→ stable ({avg_recent:.1f} pts)"

    # ── Patterns détectés ─────────────────────────────────────────────────────

    def add_pattern(self, pattern_type: str, description: str):
        """Enregistre un pattern récurrent (ex: 'sleep_deficit', 'monday_inactive')."""
        # Vérifie si ce pattern existe déjà
        for p in self._data["patterns"]:
            if p["type"] == pattern_type:
                p["occurrences"] += 1
                p["last_seen"] = datetime.now().isoformat()
                self.save()
                return
        self._data["patterns"].append({
            "type": pattern_type,
            "description": description,
            "detected_at": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
            "occurrences": 1,
        })
        self.save()

    def get_recurring_patterns(self, min_occurrences: int = 2) -> list[dict]:
        return [p for p in self._data["patterns"] if p["occurrences"] >= min_occurrences]

    # ── Contexte coaching ─────────────────────────────────────────────────────

    def update_coaching_context(self, last_advice: list[str] = None, goals: list[str] = None):
        if last_advice:
            self._data["coaching_context"]["last_advice"] = last_advice
        if goals:
            self._data["coaching_context"]["goals"] = goals
        self.save()

    def get_coaching_context(self) -> dict:
        ctx = self._data["coaching_context"].copy()
        ctx["trend"] = self.get_score_trend() or "Pas assez de données"
        ctx["recurring_patterns"] = self.get_recurring_patterns()
        ctx["sessions_count"] = len(self._data["history"])
        return ctx

    # ── Résumé mémoire ────────────────────────────────────────────────────────

    def memory_summary(self) -> str:
        history = self.get_history(days=30)
        patterns = self.get_recurring_patterns()
        trend = self.get_score_trend() or "Pas assez de données"
        lines = [
            "=== MÉMOIRE LONG-TERME ===",
            f"Sessions enregistrées (30j): {len(history)}",
            f"Tendance globale: {trend}",
        ]
        if patterns:
            lines.append("Patterns récurrents:")
            for p in patterns:
                lines.append(f"  • [{p['occurrences']}x] {p['description']}")
        ctx = self._data["coaching_context"]
        if ctx["goals"]:
            lines.append(f"Objectifs utilisateur: {', '.join(ctx['goals'])}")
        if ctx["last_advice"]:
            lines.append("Derniers conseils donnés:")
            for a in ctx["last_advice"][:3]:
                lines.append(f"  → {a}")
        return "\n".join(lines)
