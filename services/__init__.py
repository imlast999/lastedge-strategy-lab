"""
Services Package — LastEdge Strategy Lab

Services for research experiments tracking, backtest persistence, promotion, and Research API.
"""

from .logging import (
    IntelligentLogger,
    get_intelligent_logger,
    log_event,
    log_signal_evaluation,
)

from .database import (
    DatabaseManager,
    get_database_manager,
)

from .research_store import (
    ResearchStore,
    get_research_store,
)

from .backtest_tracker import (
    BacktestTracker,
    get_backtest_tracker,
)

from .long_forward_validation import (
    LongForwardValidationService,
)

from .promotion import (
    StrategyPromotionService,
    get_promotion_service,
)

from .api_server import (
    ResearchAPIServer,
    get_research_api_server,
    start_research_api_server,
)

__all__ = [
    'IntelligentLogger',
    'get_intelligent_logger',
    'log_event',
    'log_signal_evaluation',
    'DatabaseManager',
    'get_database_manager',
    'ResearchStore',
    'get_research_store',
    'BacktestTracker',
    'get_backtest_tracker',
    'LongForwardValidationService',
    'StrategyPromotionService',
    'get_promotion_service',
    'ResearchAPIServer',
    'get_research_api_server',
    'start_research_api_server',
]