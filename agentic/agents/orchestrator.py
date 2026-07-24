"""
LifeAI — Orchestrateur Principal
Lance tous les agents en parallèle (ou séquentiellement),
collecte les rapports et les passe au Chief Agent.
"""

import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .activity_agent  import ActivityAgent
from .sleep_agent     import SleepAgent
from .nutrition_agent import NutritionAgent
from .risk_agent      import RiskAgent
from .ml_agent        import MLAgent
from .chief_agent     import ChiefAgent, ChiefReport
from .memory          import LongTermMemory
from .base_agent      import AgentReport


class LifeAIOrchestrator:
    """
    Orchestrateur complet du pipeline multi-agents LifeAI.

    Usage :
        orchestrator = LifeAIOrchestrator(verbose=True)
        result = orchestrator.run(user_data)
        result.display()
    """

    def __init__(self, memory_path: str = "memory/user_memory.json",
                 parallel: bool = True, verbose: bool = False,
                 llm_insights: bool = False):
        self.parallel     = parallel
        self.verbose      = verbose
        self.llm_insights = llm_insights

        # Mémoire partagée entre le Chief Agent et l'orchestrateur
        self.memory = LongTermMemory(memory_path)

        # Agents spécialisés
        self.agents = {
            "ActivityAgent":  ActivityAgent(verbose=verbose,  llm_insights=llm_insights),
            "SleepAgent":     SleepAgent(verbose=verbose,     llm_insights=llm_insights),
            "NutritionAgent": NutritionAgent(verbose=verbose, llm_insights=llm_insights),
            "RiskAgent":      RiskAgent(verbose=verbose,      llm_insights=llm_insights),
            "MLAgent":        MLAgent(verbose=verbose,        llm_insights=llm_insights)
        }

        # Chief Agent (orchestre + LLM)
        self.chief = ChiefAgent(memory=self.memory, verbose=verbose)

    def run(self, user_data: dict) -> ChiefReport:
        """
        Lance le pipeline complet.

        1. Agents spécialisés (parallèles ou séquentiels)
        2. Chief Agent (synthèse LLM)
        3. Retourne le ChiefReport

        Args:
            user_data: dict avec clés 'activity', 'sleep', 'nutrition', 'risk'

        Returns:
            ChiefReport consolidé
        """
        start = time.time()
        self._log("=" * 60)
        self._log(f"  LifeAI Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        self._log("=" * 60)

        # ── Étape 1 : Agents spécialisés ──────────────────────────────────
        self._log("\n[1/2] Agents spécialisés en cours...")
        reports = self._run_agents(user_data)

        for name, report in reports.items():
            self._log(f"  ✓ {name}: {report.score:.1f}/100 [{report.status}]")

        # ── Étape 2 : Chief Agent ─────────────────────────────────────────
        self._log("\n[2/2] Chief Agent — synthèse LLM en cours...")
        chief_report = self.chief.synthesize(reports)

        elapsed = time.time() - start
        self._log(f"\n✅ Pipeline terminé en {elapsed:.1f}s")
        self._log(f"   Score global : {chief_report.global_score:.1f}/100 — {chief_report.health_level}")

        return chief_report

    def _run_agents(self, user_data: dict) -> dict[str, AgentReport]:
        """Lance les agents en parallèle ou séquentiellement."""
        results = {}

        if self.parallel:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {
                    executor.submit(agent.run, user_data): name
                    for name, agent in self.agents.items()
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        results[name] = future.result()
                    except Exception as e:
                        self._log(f"  ⚠ {name} error: {e}")
        else:
            for name, agent in self.agents.items():
                try:
                    results[name] = agent.run(user_data)
                except Exception as e:
                    self._log(f"  ⚠ {name} error: {e}")

        return results

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def set_user_profile(self, **kwargs):
        """Met à jour le profil utilisateur dans la mémoire."""
        self.memory.update_profile(**kwargs)

    def set_user_goals(self, goals: list[str]):
        """Définit les objectifs santé de l'utilisateur."""
        self.memory.update_coaching_context(goals=goals)

    def get_history(self, days: int = 30) -> list[dict]:
        """Retourne l'historique des analyses."""
        return self.memory.get_history(days=days)

    def export_report(self, report: ChiefReport, path: str = "output/latest_report.json"):
        """Exporte le rapport final en JSON."""
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False, default=str)
        print(f"Rapport exporté → {path}")
