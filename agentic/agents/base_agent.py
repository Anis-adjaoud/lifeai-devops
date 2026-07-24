"""
LifeAI — Base Agent
Classe abstraite commune à tous les agents spécialisés.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
import json
from datetime import datetime


@dataclass
class AgentReport:
    """Rapport structuré produit par chaque agent."""
    agent_name: str
    timestamp: str
    score: Optional[float]  # 0-100, None si aucune donnée réelle disponible
    status: str              # "good" | "warning" | "critical" | "no_data"
    key_metrics: dict
    insights: list[str]
    recommendations: list[str]
    anomalies: list[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "timestamp": self.timestamp,
            "score": self.score,
            "status": self.status,
            "key_metrics": self.key_metrics,
            "insights": self.insights,
            "recommendations": self.recommendations,
            "anomalies": self.anomalies,
        }

    def to_summary_text(self) -> str:
        """Résumé textuel pour le Chief Agent."""
        lines = [
            f"=== {self.agent_name.upper()} REPORT ===",
            f"Score: {self.score:.1f}/100  |  Status: {self.status.upper()}",
            "\nMétriques clés:",
        ]
        for k, v in self.key_metrics.items():
            lines.append(f"  • {k}: {v}")
        if self.anomalies:
            lines.append("\n⚠ Anomalies détectées:")
            for a in self.anomalies:
                lines.append(f"  ! {a}")
        lines.append("\nInsights:")
        for i in self.insights:
            lines.append(f"  → {i}")
        lines.append("\nRecommandations:")
        for r in self.recommendations:
            lines.append(f"  ✓ {r}")
        return "\n".join(lines)


class BaseAgent(ABC):
    """
    Agent spécialisé de base.
    Chaque sous-classe implémente analyze() avec sa logique métier.
    """

    def __init__(self, name: str, verbose: bool = False, llm_insights: bool = False):
        self.name = name
        self.verbose = verbose
        self.llm_insights = llm_insights

    def log(self, msg: str):
        if self.verbose:
            print(f"[{self.name}] {msg}")

    def run(self, user_data: dict) -> AgentReport:
        """Point d'entrée principal — appelle analyze() + postprocess."""
        self.log(f"Analyse démarrée...")
        report = self.analyze(user_data)
        self.log(f"Analyse terminée — Score: {report.score:.1f} | Status: {report.status}")
        return report

    @abstractmethod
    def analyze(self, user_data: dict) -> AgentReport:
        """Logique métier spécifique à chaque agent."""
        pass

    def _llm_enrich(self, domain: str, key_metrics: dict, anomalies: list) -> dict | None:
        """
        Appelle le LLM pour enrichir recommendations et insights.
        Retourne {"recommendations": [...], "insights": [...]} ou None si désactivé/échec.
        """
        if not self.llm_insights:
            return None
        from .llm_client import ask_json
        metrics_str   = "\n".join(f"  - {k}: {v}" for k, v in key_metrics.items())
        anomalies_str = "\n".join(f"  ! {a}" for a in anomalies) if anomalies else "  Aucune"
        prompt = (
            f"Tu es un coach santé expert en {domain}. "
            f"Génère des recommandations personnalisées et précises basées sur ces données réelles.\n\n"
            f"Métriques:\n{metrics_str}\n\n"
            f"Anomalies:\n{anomalies_str}\n\n"
            f"Réponds UNIQUEMENT en JSON valide (sans markdown) :\n"
            f'{{"recommendations": ["rec1", "rec2"], "insights": ["insight1", "insight2"]}}\n\n'
            f"Règles : 2-3 items max par liste, mentionne les vrais chiffres, en français, ton bienveillant."
        )
        return ask_json(prompt)

    def _make_report(
        self,
        score: float,
        key_metrics: dict,
        insights: list[str],
        recommendations: list[str],
        anomalies: list[str] = None,
        raw_data: dict = None,
    ) -> AgentReport:
        """Helper pour construire un AgentReport standardisé."""
        status = (
            "critical" if score < 40
            else "warning" if score < 65
            else "good"
        )
        return AgentReport(
            agent_name=self.name,
            timestamp=datetime.now().isoformat(),
            score=round(score, 1),
            status=status,
            key_metrics=key_metrics,
            insights=insights,
            recommendations=recommendations,
            anomalies=anomalies or [],
            raw_data=raw_data or {},
        )
