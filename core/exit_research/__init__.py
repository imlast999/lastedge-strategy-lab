"""
Exit Research — core/exit_research/

Módulo de investigación aislada para validar la robustez del sistema
de salidas de eurusd_simple.

La entrada es EXACTAMENTE la misma que eurusd_simple.
Solo varía la lógica de cálculo de SL/TP/trailing.

Uso rápido:
    from core.exit_research import run_exit_research
    report = run_exit_research(bars=10000)
    print(report["symbol"])

Uso desde Discord / bot.py:
    from core.exit_research.runner import ExitResearchRunner
    runner = ExitResearchRunner()
    runner.run_all(bars=10000, save=True)
"""

from .runner           import ExitResearchRunner
from .strategy_adapter import StrategyAdapter, adapter_for_symbol

__all__ = ["ExitResearchRunner", "run_exit_research", "StrategyAdapter", "adapter_for_symbol"]


def run_exit_research(
    bars: int = 20_000,
    symbol: str = "EURUSD",
    save: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Single public entry point.

    Returns the Research_Report as a plain dict.

    Raises:
        ValueError: If bars < 5000.

    Re-raises any unrecoverable phase exception with phase name + traceback.

    Ejemplo:
        from core.exit_research import run_exit_research
        report = run_exit_research(bars=20000)
        print(report["symbol"])
    """
    if bars < 5000:
        raise ValueError(f"bars must be >= 5000, got {bars}")
    runner = ExitResearchRunner(symbol=symbol)
    return runner.run_all(bars=bars, save=save, verbose=verbose)
