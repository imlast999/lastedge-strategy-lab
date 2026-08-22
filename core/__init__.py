"""
Core Quantitative Research & Backtesting — LastEdge Strategy Lab

Exports modules for exit research, replay engine, walk-forward analysis, Monte Carlo simulation, and trade cost modeling.
"""

from .replay_engine import (
    ReplayEngine,
    ReplaySignal,
    ReplayStatistics,
    get_replay_engine
)

from .montecarlo import (
    MonteCarlo,
    MonteCarloReport,
    TradeRecord,
    run_montecarlo,
)

from .walkforward import (
    WalkForwardTester,
    WindowResult,
)

from .scoring import (
    FlexibleScoring,
    ConfirmationRule,
    ScoringResult,
    get_scoring_system
)

from .filters import (
    ConsolidatedFilters,
    FilterResult,
    get_filters_system
)

from .trade_costs import (
    get_round_trip_cost_pips,
    apply_costs_to_profit,
    get_cost_summary,
)

__all__ = [
    'ReplayEngine',
    'ReplaySignal',
    'ReplayStatistics',
    'get_replay_engine',
    'MonteCarlo',
    'MonteCarloReport',
    'TradeRecord',
    'run_montecarlo',
    'WalkForwardTester',
    'WindowResult',
    'FlexibleScoring',
    'ConfirmationRule',
    'ScoringResult',
    'get_scoring_system',
    'ConsolidatedFilters',
    'FilterResult',
    'get_filters_system',
    'get_round_trip_cost_pips',
    'apply_costs_to_profit',
    'get_cost_summary',
]