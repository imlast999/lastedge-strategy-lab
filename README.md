# LastEdge Strategy Lab

Quantitative research laboratory, Walk Forward Analysis, Monte Carlo simulation, and Strategy Promotion pipeline for LastEdge.

## Overview
- **Quantitative Research**: Statistical backtesting with realistic trade costs (spread, commission, slippage).
- **Walk Forward Analysis (WFA)**: Multi-window rolling optimization and stability scoring.
- **Monte Carlo Engine**: Risk-of-ruin calculation, drawdown confidence intervals.
- **Exit Research Framework**: Independent exit rule optimization.
- **Strategy Promotion**: Canonical contract verification, semantic versioning, and SHA-256 packaging into Trading Engine.
- **REST API**: Research telemetry and experiment endpoints on port `8082`.

## Quick Start
```bash
pip install -r requirements.txt
cp .env.example .env
python run_validation.py
```
