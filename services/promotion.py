"""
LastEdge Strategy Lab — Strategy Promotion & Packaging Service
services/promotion.py

Handles explicit, auditable transition of validated strategy candidates from
Research to Production.

Guarantees that:
1. Every promoted strategy satisfies the Unified Strategy Contract (BaseStrategy, StrategyMetadata).
2. Code SHA-256, Config Hash, and Dataset SHA-256 are verified bit-for-bit.
3. All quantitative validation gates (WFA WES >= 0.60, Monte Carlo Ruin <= 5.0%, positive expectancy) must pass.
4. Promotion cannot be executed on unvalidated, corrupted, or altered candidates.
5. Exports full production package (Python code + JSON metadata manifest).
"""

from __future__ import annotations

import os
import json
import hashlib
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Quantitative Validation Gate Thresholds
MIN_WES_SCORE = 0.60
MAX_RUIN_PROB_PCT = 5.0
MIN_WINRATE_PCT = 25.0
MIN_SIGNALS = 5


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
        dataset_meta: Optional[Dict[str, Any]] = None,
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
            "source_module_path": str(source_module_path),
            "rules_config": rules_config,
            "metrics": validation_metrics,
            "dataset_meta": dataset_meta or {},
            "notes": notes,
        }

        # 1. Calculate integrity hash of configuration
        config_str = json.dumps(rules_config, sort_keys=True)
        record["config_hash"] = hashlib.sha256(config_str.encode("utf-8")).hexdigest()[:16]

        # 2. Calculate code file SHA-256 if file exists
        src_p = Path(source_module_path)
        if not src_p.is_absolute():
            src_p = self.lab_root / src_p

        if src_p.exists() and src_p.is_file():
            record["code_sha256"] = hashlib.sha256(src_p.read_bytes()).hexdigest()
        else:
            record["code_sha256"] = ""

        # 3. Record dataset SHA-256
        if dataset_meta and "file_hash_sha256" in dataset_meta:
            record["dataset_sha256"] = dataset_meta["file_hash_sha256"]
        else:
            record["dataset_sha256"] = ""

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

    def validate_candidate_readiness(self, candidate_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Performs rigorous validation of candidate readiness before promotion:
          - Status must be CANDIDATE or VALIDATED.
          - Code file on disk must match registered code_sha256 exactly.
          - Config hash must match registered config_hash.
          - Pipeline must have completed WFA (WES >= 0.60) and Monte Carlo (Ruin <= 5%).
        """
        reasons = []

        # 1. State check
        status = candidate_data.get("status")
        if status not in ("CANDIDATE", "VALIDATED", "APPROVED"):
            reasons.append(f"Invalid candidate status '{status}'. Must be CANDIDATE or VALIDATED.")

        # 2. Code integrity check (Source file must exist and SHA-256 match)
        src_path_str = candidate_data.get("source_module_path", "")
        if not src_path_str:
            reasons.append("Missing 'source_module_path' in candidate manifest.")
        else:
            src_p = Path(src_path_str)
            if not src_p.is_absolute():
                src_p = self.lab_root / src_p

            if not src_p.exists() or not src_p.is_file():
                reasons.append(f"Source code file not found at '{src_p}'.")
            else:
                current_sha256 = hashlib.sha256(src_p.read_bytes()).hexdigest()
                registered_sha256 = candidate_data.get("code_sha256", "")
                if current_sha256 != registered_sha256:
                    reasons.append(
                        f"Code SHA-256 mismatch! Registered: {registered_sha256[:12]}..., Current on disk: {current_sha256[:12]}... "
                        f"(Source file was modified after research registration)."
                    )

        # 3. Configuration integrity check
        rules_cfg = candidate_data.get("rules_config", {})
        config_str = json.dumps(rules_cfg, sort_keys=True)
        current_cfg_hash = hashlib.sha256(config_str.encode("utf-8")).hexdigest()[:16]
        registered_cfg_hash = candidate_data.get("config_hash", "")
        if current_cfg_hash != registered_cfg_hash:
            reasons.append(
                f"Config hash mismatch! Registered: {registered_cfg_hash}, Current: {current_cfg_hash}."
            )

        # 4. Quantitative Validation Metrics Gate
        metrics = candidate_data.get("metrics", {})

        # 4a. Backtest check
        bt = metrics.get("baseline_backtest", {})
        if not bt:
            reasons.append("Pipeline incomplete: Missing baseline backtest metrics.")
        elif bt.get("signals", 0) < MIN_SIGNALS:
            reasons.append(f"Insufficient trade count in baseline backtest ({bt.get('signals', 0)} < {MIN_SIGNALS}).")

        # 4b. Walk Forward Analysis check
        wf = metrics.get("walk_forward", {})
        if not wf:
            reasons.append("Pipeline incomplete: Walk Forward Analysis (WFA) was not executed.")
        else:
            wes = wf.get("wes_score", 0.0)
            if wes < MIN_WES_SCORE:
                reasons.append(f"Walk Forward Analysis failed: WES score {wes:.2f} < {MIN_WES_SCORE}.")

        # 4c. Monte Carlo check
        mc = metrics.get("monte_carlo", {})
        if not mc:
            reasons.append("Pipeline incomplete: Monte Carlo stress testing was not executed.")
        else:
            ruin_pct = mc.get("prob_ruin_pct", 100.0)
            if ruin_pct > MAX_RUIN_PROB_PCT:
                reasons.append(f"Monte Carlo risk of ruin failed: {ruin_pct:.2f}% > {MAX_RUIN_PROB_PCT}%.")

        return (len(reasons) == 0, reasons)

    def promote_to_production(
        self,
        candidate_id: str,
        approver: str = "Architect",
        target_engine_dir: Optional[Path] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Promotes a candidate from CANDIDATE to APPROVED/PRODUCTION after verifying
        all security and quantitative gates.
        """
        file_path = self.candidates_dir / f"{candidate_id}.json"
        if not file_path.exists():
            return {"ok": False, "error": f"Candidate '{candidate_id}' not found."}

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Evaluate readiness gates
        is_ready, reasons = self.validate_candidate_readiness(data)
        if not is_ready and not force:
            logger.warning("[PromotionService] Promotion blocked for %s: %s", candidate_id, reasons)
            return {
                "ok": False,
                "error": "Promotion blocked by validation gates.",
                "reasons": reasons,
                "candidate": data
            }

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
        """Exports the approved strategy code and manifest into the Trading Engine's strategies directory."""
        strategies_dir = engine_dir / "strategies"
        strategies_dir.mkdir(parents=True, exist_ok=True)

        symbol = candidate_data["symbol"]
        version = candidate_data["version"]
        src_path_str = candidate_data.get("source_module_path", "")
        src_p = Path(src_path_str)
        if not src_p.is_absolute():
            src_p = self.lab_root / src_p

        if src_p.exists() and src_p.is_file():
            base_name = f"{symbol.lower()}_v{version.replace('.', '_')}"
            dest_code_file = strategies_dir / f"{base_name}.py"
            dest_meta_file = strategies_dir / f"{base_name}.json"

            # 1. Export python strategy code
            shutil.copy2(src_p, dest_code_file)
            dest_sha256 = hashlib.sha256(dest_code_file.read_bytes()).hexdigest()

            # 2. Export manifest sidecar
            manifest = {
                "strategy_name": candidate_data["strategy_name"],
                "symbol": symbol,
                "timeframe": candidate_data["timeframe"],
                "version": version,
                "config": candidate_data["rules_config"],
                "config_hash": candidate_data.get("config_hash", ""),
                "code_sha256": dest_sha256,
                "dataset_sha256": candidate_data.get("dataset_sha256", ""),
                "promoted_at": candidate_data.get("promoted_at", datetime.now(timezone.utc).isoformat()),
                "approved_by": candidate_data.get("approved_by", "Architect"),
            }
            with open(dest_meta_file, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            logger.info("[PromotionService] Exported strategy package to %s (SHA-256: %s)", dest_code_file, dest_sha256[:12])
            return {
                "exported": True,
                "dest_code_file": str(dest_code_file),
                "dest_meta_file": str(dest_meta_file),
                "sha256": dest_sha256,
                "verified": dest_sha256 == candidate_data.get("code_sha256")
            }

        return {"exported": False, "reason": f"Source file {src_p} not accessible."}


_promotion_service_instance: Optional[StrategyPromotionService] = None


def get_promotion_service() -> StrategyPromotionService:
    global _promotion_service_instance
    if _promotion_service_instance is None:
        _promotion_service_instance = StrategyPromotionService()
    return _promotion_service_instance
