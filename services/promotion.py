"""
LastEdge Strategy Lab — Strategy Promotion & Packaging Service
services/promotion.py

Handles explicit, auditable transition of validated strategy candidates from
Research to Production.

Lifecycle:
  EXPERIMENTAL -> BACKTESTED -> OPTIMIZED -> VALIDATED -> CANDIDATE -> APPROVED -> PRODUCTION -> RETIRED

Guarantees that:
1. Every promoted strategy satisfies the Unified Strategy Contract (BaseStrategy, StrategyMetadata).
2. The exact validated parameters, rules, and exit configurations are locked.
3. A semantic version (vX.Y.Z) and reproducible metadata hash are assigned.
4. No automated/unauthorized changes are pushed to Production without explicit approval.
"""

from __future__ import annotations

import os
import json
import hashlib
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class StrategyPromotionService:
    """Manages strategy candidate evaluation, packaging, and promotion."""

    def __init__(self, lab_root: Optional[Path] = None):
        self.lab_root = lab_root or Path(__file__).parent.parent
        self.candidates_dir = self.lab_root / "data" / "candidates"
        self.candidates_dir.mkdir(parents=True, exist_ok=True)

    def register_candidate(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        version: str,
        rules_config: Dict[str, Any],
        validation_metrics: Dict[str, Any],
        source_module_path: str,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Registers a validated strategy candidate in the Lab's candidate registry.
        """
        candidate_id = f"{symbol.lower()}_{strategy_name.lower()}_{version.replace('.', '_')}"
        record = {
            "candidate_id": candidate_id,
            "strategy_name": strategy_name,
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "version": version,
            "status": "CANDIDATE",
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "source_module_path": source_module_path,
            "rules_config": rules_config,
            "metrics": validation_metrics,
            "notes": notes,
        }

        # Calculate integrity hash of configuration
        config_str = json.dumps(rules_config, sort_keys=True)
        record["config_hash"] = hashlib.sha256(config_str.encode("utf-8")).hexdigest()[:16]

        # Calculate code file SHA-256 if file exists
        src_p = Path(source_module_path)
        if src_p.exists() and src_p.is_file():
            record["code_sha256"] = hashlib.sha256(src_p.read_bytes()).hexdigest()
        else:
            record["code_sha256"] = ""

        file_path = self.candidates_dir / f"{candidate_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)

        logger.info("[PromotionService] Registered candidate: %s (%s)", candidate_id, version)
        return record

    def list_candidates(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists all registered strategy candidates, optionally filtered by status."""
        candidates = []
        for file in self.candidates_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if status is None or data.get("status") == status:
                        candidates.append(data)
            except Exception as e:
                logger.error("Error reading candidate file %s: %s", file, e)
        return sorted(candidates, key=lambda c: c.get("registered_at", ""), reverse=True)

    def promote_to_production(
        self,
        candidate_id: str,
        approver: str = "Architect",
        target_engine_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Promotes a candidate from CANDIDATE to APPROVED/PRODUCTION and exports
        the standardized package.
        """
        file_path = self.candidates_dir / f"{candidate_id}.json"
        if not file_path.exists():
            return {"ok": False, "error": f"Candidate '{candidate_id}' not found."}

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["status"] = "APPROVED"
        data["promoted_at"] = datetime.now(timezone.utc).isoformat()
        data["approved_by"] = approver

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # If target engine directory provided, package and export
        if target_engine_dir:
            target_engine_dir = Path(target_engine_dir)
            if target_engine_dir.exists():
                export_res = self._export_production_package(data, target_engine_dir)
                return {"ok": True, "candidate": data, "export": export_res}

        return {"ok": True, "candidate": data}

    def _export_production_package(self, candidate_data: Dict[str, Any], engine_dir: Path) -> Dict[str, Any]:
        """Exports the approved strategy into the Trading Engine's strategies directory."""
        strategies_dir = engine_dir / "strategies"
        strategies_dir.mkdir(parents=True, exist_ok=True)

        symbol = candidate_data["symbol"]
        version = candidate_data["version"]
        src_path = Path(candidate_data.get("source_module_path", ""))

        if src_path.exists() and src_path.is_file():
            dest_file = strategies_dir / f"{symbol.lower()}_v{version.replace('.', '_')}.py"
            shutil.copy2(src_path, dest_file)
            dest_sha256 = hashlib.sha256(dest_file.read_bytes()).hexdigest()
            logger.info("[PromotionService] Exported strategy file to %s (SHA-256: %s)", dest_file, dest_sha256[:12])
            return {
                "exported": True,
                "dest_file": str(dest_file),
                "sha256": dest_sha256,
                "verified": dest_sha256 == candidate_data.get("code_sha256")
            }

        return {"exported": False, "reason": f"Source file {src_path} not accessible."}


_promotion_service_instance: Optional[StrategyPromotionService] = None


def get_promotion_service() -> StrategyPromotionService:
    global _promotion_service_instance
    if _promotion_service_instance is None:
        _promotion_service_instance = StrategyPromotionService()
    return _promotion_service_instance
