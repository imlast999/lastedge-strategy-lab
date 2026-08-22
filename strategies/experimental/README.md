# Estrategias Descartadas

Estas estrategias fueron evaluadas y descartadas tras el grid search de mayo 2026.
Se conservan para referencia histórica y posible revisión futura.

| Estrategia | Motivo de descarte | Mejor PF obtenido |
|---|---|---|
| `eurusd_mtf` | PF máximo 0.42 en todo el grid. Sin edge en ninguna combinación. | 0.42 |
| `xauusd_psychological` | PF máximo 0.94, nunca llega a break-even. | 0.94 |
| `xauusd_reversal` | 1 señal en 5000 velas. Demasiado restrictiva para generar datos. | N/A |

## Cómo reactivar una estrategia

Si en el futuro se quiere reactivar alguna:
1. Moverla de vuelta a `strategies/`
2. Añadirla al `STRATEGY_REGISTRY` en `signals.py`
3. Añadirla a `STRATEGIES_BY_SYMBOL` en `tests/backtest_runner.py`
4. Correr backtest completo antes de usar en producción
