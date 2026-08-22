# GSRS (Gold Session Reversal Strategy) — Especificación para bot en Python y Gap Analysis para Backtest

**Basado en:** análisis del vídeo original (~46s), transcripción completa, y análisis de fotogramas (OCR + detección de píxeles) — documento de investigación GSRS v0.2.
**Objetivo de este documento:** traducir todo lo confirmado a reglas implementables en código, y listar de forma explícita y priorizada todo lo que falta antes de poder correr un backtest con sentido.

---

## 0. Cómo leer este documento

| Símbolo | Significado |
|---|---|
| 🟢 | Confirmado — se puede codificar directamente, sin ambigüedad |
| 🟡 | Parcialmente definido — se puede codificar con un supuesto explícito (ver §7) |
| 🔴 | Bloqueante — sin definir esto, el backtest no arranca o da resultados sin sentido |

---

## 1. Resumen para quien programe el bot

La estrategia es un sistema de reversión intradía en XAUUSD que solo opera en dos ventanas horarias fijas al día (segunda hora de Asia y segunda hora de Londres). Dentro de cada ventana, espera un impulso fuerte, luego un cambio de estructura (posible MSS de 5 swings), luego una entrada en el retroceso del ~50%, con SL detrás del extremo de la estructura y TP al 50% de un rango llamado "hourly overextension".

**Estado actual:** la lógica de *detección de señal* (cuándo y en qué dirección operar) está razonablemente bien definida a nivel conceptual, pero le faltan casi todos los umbrales numéricos exactos. La *gestión de riesgo* no está definida en absoluto. **No se puede programar un backtest fiel al 100% al autor original con la información disponible hoy** — sí se puede programar una primera versión con supuestos explícitos (ver §7) para empezar a iterar.

---

## 2. Universo y datos

| Parámetro | Valor | Estado |
|---|---|---|
| Instrumento | XAUUSD (oro spot) | 🟢 |
| Timeframe operativo (señales) | M1 | 🟢 |
| Timeframe de contexto | H1 (solo referencia temporal, no genera señales) | 🟢 |
| Proveedor / fuente de datos M1 | Sin definir | 🔴 |
| Rango histórico necesario | Sin definir (recomendado: mínimo 2-3 años de M1 para tener volumen estadístico de sesiones) | 🔴 |
| Calidad de datos | Sin verificar (gaps de fin de semana, rollovers, velas duplicadas/faltantes) | 🔴 |

**Por qué importa el proveedor de datos:** el oro tiene spreads y ligeras diferencias de precio entre brokers (a veces varios dólares en momentos de volatilidad). Como la estrategia depende de niveles exactos (máximo/mínimo externo, 50% de retroceso), el broker/fuente de datos elegido **cambiará dónde caen esos niveles**. Hay que fijar una única fuente de datos y ser consistente entre backtest y ejecución en vivo.

---

## 3. Sesiones y horarios 🔴 BLOQUEANTE

El autor dice "segunda hora de Asia" y "segunda hora de Londres" pero **nunca da una hora exacta ni una zona horaria**. Esto es ambiguo porque:

- No hay una definición universal de "apertura de la sesión asiática" (Tokio, Sídney, apertura del mercado de futuros del oro en Shanghái... todas distintas).
- "Hora de Londres" puede referirse a hora del mercado de Londres (LBMA), o a la zona horaria GMT/BST.
- Ningún broker/plataforma usa exactamente los mismos límites de sesión.

**Convención habitual de mercado (ejemplo, NO confirmado por el autor):**

| Sesión | Apertura típica (UTC) | "Segunda hora" (ejemplo) |
|---|---|---|
| Asia | 23:00–00:00 UTC | 00:00–01:00 UTC |
| Londres | 07:00–08:00 UTC | 08:00–09:00 UTC |

Estas horas cambian con el horario de verano (DST) tanto en UTC de origen como en la zona horaria del broker. **Antes de programar nada, hay que decidir:**
1. En qué zona horaria vienen las velas de tu fuente de datos (UTC, hora del broker, EST...).
2. Qué definición exacta de "apertura de sesión" vas a usar.
3. Cómo tratar el cambio de horario de verano (¿ventana fija en UTC, o fija en hora local de Londres/Tokio que se desplaza con el DST?).

---

## 4. Máquina de estados — lógica de implementación

Mismos 9 estados del documento de investigación, con el detalle de qué se sabe y qué falta en cada uno.

### 4.1 `WAIT_SESSION` → `WAIT_SECOND_HOUR`
🟢 Trivial: comprobar si el timestamp de la vela cae dentro de una de las dos ventanas horarias definidas en §3.

### 4.2 `WAIT_EXPANSION` 🟡
**Confirmado:** debe aparecer "mucho volumen" y movimiento fuerte y direccional al empezar la ventana, sin consolidación previa relevante.
**No confirmado:** ningún umbral numérico. No hay panel de volumen visible en el vídeo — probablemente "volumen" se refiere visualmente al tamaño/velocidad de las velas, no a un dato de volumen real contrastado (XAUUSD spot no tiene volumen centralizado real; muchos brokers muestran volumen de ticks, que no es comparable entre proveedores).
**Pseudocódigo orientativo (con supuesto marcado):**
```python
# ASSUMPTION — umbral no confirmado por el autor
def is_expansion(candles_window, atr_h1, min_atr_multiple=1.5):
    move = abs(candles_window[-1].close - candles_window[0].open)
    return move >= min_atr_multiple * atr_h1
```

### 4.3 `WAIT_SHIFT` (Type 3 Shift / posible MSS) 🟡
**Confirmado por evidencia de vídeo (un solo ejemplo):** secuencia de 5 swings — Low → High → Higher Low → Higher High → ruptura por debajo del primer Low. Coincide con un Market Structure Shift (MSS) clásico de metodología ICT/SMC.
**No confirmado:** 
- Si el autor exige siempre exactamente 5 swings o el número varía.
- Qué algoritmo de detección de swings usa (fractal de N velas, pivote de swing con "strength" X, ZigZag con % mínimo, etc.).
- Si la ruptura se confirma por mecha o por cierre de vela.
**Pseudocódigo orientativo:**
```python
# ASSUMPTION — método de detección de swings no confirmado
def detect_swings(m1_candles, fractal_strength=2):
    """Fractal estándar: un pivote necesita N velas más bajas/altas a cada lado."""
    ...

def is_type3_shift(swings):
    # Evidencia de vídeo: L1 -> H1 -> L2(higher low) -> H2(higher high) -> L3 < L1
    if len(swings) < 5:
        return False
    l1, h1, l2, h2, l3 = swings[-5:]
    return (l2.price > l1.price and h2.price > h1.price
            and l3.price < l1.price)
```

### 4.4 `WAIT_PULLBACK` 🟡
**Confirmado:** entrada en un retroceso de "alrededor del 50%" del "breaking move" (el tramo de ruptura, es decir, de H2/External High hasta L3).
**No confirmado:** no se ve ninguna herramienta de Fibonacci en el vídeo. Podría ser: (a) 50% simple del rango high-low del tramo de ruptura, (b) 50% medido con Fibonacci real, (c) 50% del cuerpo de las velas de ruptura. La opción (a) es la más simple y la que mejor encaja con lo observado (el autor no usa ninguna herramienta visible, parece una estimación a ojo).
```python
# ASSUMPTION — sin fibonacci visible; punto medio simple del tramo de ruptura
def pullback_entry_level(external_high, break_low, direction="short"):
    return (external_high + break_low) / 2
```

### 4.5 `WAIT_ENTRY` 🟢/🟡
Entrada cuando el precio toca el nivel de pullback calculado arriba, dentro de la misma vela H1 de contexto (no confirmado si hay límite de tiempo para que se cumpla el pullback antes de descartar el setup — **gap**, ver §6).

### 4.6 `OPEN_POSITION` — SL/TP
- **Stop Loss 🟢 confirmado en concepto:** más allá del máximo o mínimo externo (el swing H2 de la secuencia del shift). **No confirmado:** margen adicional (buffer en pips/puntos) más allá del nivel exacto.
- **Take Profit 🟡:** "50% de la hourly overextension". La "hourly overextension" tiene apoyo visual (ver documento de investigación §13) para la hipótesis: rango entre la apertura de la vela H1 y el extremo alcanzado. **No confirmado:** fórmula exacta cuando el extremo sigue moviéndose después de la entrada.
```python
# ASSUMPTION — hourly overextension = |precio_actual_H1 - apertura_H1|
def take_profit(h1_open, h1_extreme, direction="short"):
    overextension = abs(h1_extreme - h1_open)
    if direction == "short":
        return h1_open - 0.5 * overextension  # ejemplo, ajustar según validación
    return h1_open + 0.5 * overextension
```

### 4.7 `MANAGE_POSITION` 🔴 BLOQUEANTE
**No hay absolutamente ninguna regla documentada**: sin break-even, sin trailing stop, sin cierre parcial, sin gestión de tiempo máximo en la operación. Un backtest sin esto es técnicamente posible (SL/TP fijos, "fire and forget"), pero no representa necesariamente cómo opera el autor.

### 4.8 `POSITION_CLOSED` → `WAIT_SESSION`
🟢 Trivial.

---

## 5. Tabla de parámetros de configuración (para el archivo de config del bot)

| Parámetro | Descripción | Valor conocido | Estado |
|---|---|---|---|
| `symbol` | Instrumento | XAUUSD | 🟢 |
| `entry_timeframe` | Timeframe de señales | M1 | 🟢 |
| `context_timeframe` | Timeframe de contexto | H1 | 🟢 |
| `session_windows` | Horarios de sesión válidos | Sin definir con exactitud | 🔴 |
| `expansion_threshold` | Umbral de expansión inicial | Sin definir | 🔴 |
| `swing_detection_method` | Método de detección de swings | Sin definir | 🔴 |
| `mss_swing_count` | Nº de swings requeridos para el shift | 5 (evidencia de un ejemplo) | 🟡 |
| `pullback_fraction` | Fracción de retroceso para entrar | 0.50 | 🟢 (confirmado como cifra, no como método) |
| `pullback_method` | Cómo se mide el 50% | Sin confirmar (supuesto: punto medio simple) | 🟡 |
| `sl_buffer` | Margen extra sobre el nivel externo | Sin definir | 🔴 |
| `tp_fraction` | Fracción de la overextension para TP | 0.50 | 🟢 (cifra) / 🟡 (método) |
| `overextension_method` | Cómo se mide la hourly overextension | Sin confirmar (supuesto: apertura H1 → extremo) | 🟡 |
| `risk_percent_per_trade` | Riesgo por operación | Sin definir | 🔴 |
| `max_trades_per_session` | Máximo de operaciones | Sin definir (supuesto razonable: 1) | 🔴 |
| `news_filter` | Filtro de noticias | Sin definir | 🔴 |
| `min_atr_filter` | Filtro de volatilidad mínima | Sin definir | 🔴 |
| `invalid_days` | Días/festivos excluidos | Sin definir | 🔴 |
| `reentry_rules` | Reglas de reentrada tras SL/TP | Sin definir | 🔴 |

---

## 6. Gap analysis completo — todo lo que falta antes de backtestear

### 6.1 Bloqueantes duros — sin esto el backtest **no puede arrancar**
1. **Zona horaria y definición exacta de las ventanas de sesión** (§3). Sin esto no se puede ni filtrar qué velas mirar.
2. **Fuente de datos M1 de XAUUSD** confirmada y con histórico suficiente (2-3 años mínimo recomendado).
3. **Umbral cuantitativo de "expansión inicial"** — hoy es puramente descriptivo ("movimiento fuerte con volumen").
4. **Algoritmo exacto de detección de swings** para el Type 3 Shift — sin esto no se puede programar `WAIT_SHIFT` de forma determinista.

### 6.2 Bloqueantes para que el resultado sea realista (el backtest "corre" pero no significa nada sin esto)
5. **Gestión de riesgo**: tamaño de posición, % de riesgo por operación, o lotaje fijo. Sin esto no hay curva de equity, solo una lista de operaciones ganadoras/perdedoras en pips.
6. **Modelo de costes**: spread, comisión, slippage. El oro puede tener spreads variables notables según la hora — importante porque la estrategia opera justo en la apertura de sesión, momento de spreads más amplios.
7. **Regla de invalidación / timeout**: ¿qué pasa si el Type 3 Shift no aparece en la ventana esperada? ¿Y si el pullback nunca llega al 50%? Sin esto el backtest no sabe cuándo "cancelar" un setup y pasar al día siguiente.
8. **Margen del Stop Loss** (buffer más allá del nivel externo) — sin esto, el SL podría saltar por ruido de mercado en cada operación.

### 6.3 Importantes pero no bloqueantes (afectan la fiabilidad, se pueden añadir después)
9. Filtro de noticias / calendario económico.
10. Filtro de volatilidad mínima (ATR).
11. Máximo de operaciones por día/sesión y comportamiento tras alcanzar el máximo.
12. Días inválidos (festivos, aperturas de domingo con gaps, viernes con cierre anticipado).
13. Reglas de reentrada tras un SL o un TP.
14. Comportamiento tras rachas de pérdidas (¿pausa el sistema, reduce riesgo, sigue igual?).

### 6.4 Deseables / refinamiento futuro
15. Break-even automático / trailing stop.
16. Cierre parcial de la posición.
17. Validación estadística con múltiples ejemplos — **todo lo confirmado hoy proviene de un único ejemplo mostrado en un vídeo de 46 segundos**. Antes de arriesgar capital real, hace falta validar el patrón sobre decenas/cientos de repeticiones históricas, no solo programarlo.

---

## 7. Supuestos por defecto propuestos para un primer backtest MVP

Si quieres empezar a iterar ya, en lugar de esperar a cerrar todos los huecos, aquí tienes un set de supuestos razonables y claramente marcados como **hipótesis de partida, no reglas confirmadas por el autor**. La idea es tener algo ejecutable cuanto antes y refinarlo con datos.

| Parámetro | Supuesto propuesto (MVP) | Cómo validarlo/ajustarlo después |
|---|---|---|
| Zona horaria de sesión | UTC fijo, Asia 00:00-01:00 / Londres 08:00-09:00 | Comparar resultados desplazando ±1h para ver sensibilidad |
| Expansión inicial | Rango de los primeros 10 min ≥ 1.5× ATR(14) en H1 | Barrer el multiplicador (1.0x–3.0x) y ver qué produce setups similares al vídeo |
| Detección de swings | Fractal estándar de 5 velas (2 a cada lado) en M1 | Probar también fractal de 3 y de 7 velas |
| Confirmación de ruptura | Por cierre de vela (más conservador que por mecha) | Comparar cierre vs. mecha en resultados |
| Nº de swings del shift | Exactamente 5 (L-H-HL-HH-break) | Relajar a "cualquier ruptura tras una higher low" si da muy pocas señales |
| Método de pullback | Punto medio simple (high+low)/2 del tramo de ruptura | Comparar contra Fibonacci 50% real |
| Buffer del SL | +10% del rango del tramo de ruptura, o un mínimo fijo en $ | Ajustar según ratio de SL-hunting observado |
| Overextension | \|extremo H1 − apertura H1\| | Confirmar visualmente contra más ejemplos |
| Riesgo por operación | 1% del capital, fijo | Backtestear con 0.5%/1%/2% y comparar drawdown |
| Máx. operaciones por sesión | 1 | — |
| Timeout del setup | Si no hay entrada dentro de la misma vela H1, se descarta | — |
| Costes | Spread fijo de referencia (p. ej. 20-30 puntos en XAUUSD) + comisión de tu bróker | Sustituir por spread real histórico si está disponible |

---

## 8. Preguntas concretas para cerrar con el autor (o investigación adicional)

1. ¿Qué zona horaria usa exactamente para "segunda hora de Asia/Londres"?
2. ¿Cómo cuantifica la "expansión inicial" — hay algún indicador o solo es visual?
3. ¿Qué indicador/herramienta usa para detectar el "Type 3 Shift" — es un indicador propio, un fractal estándar, o puramente discrecional?
4. ¿El 50% del pullback se mide con Fibonacci o a ojo?
5. ¿Qué % de riesgo arriesga por operación?
6. ¿Qué hace si el precio nunca retrocede al 50% o si el shift nunca aparece?
7. ¿Las cifras de rendimiento mostradas ("80% win rate", racha de 14) son de backtest o de cuenta real? ¿En qué plataforma/broker?

---

## 9. Checklist final antes de programar el backtest

- [ ] Fuente de datos M1 de XAUUSD confirmada, con histórico ≥ 2-3 años
- [ ] Zona horaria de los datos identificada y ventanas de sesión fijadas
- [ ] Umbral de "expansión inicial" definido (aunque sea un supuesto del §7)
- [ ] Algoritmo de detección de swings elegido e implementado
- [ ] Regla de confirmación del Type 3 Shift codificada y probada sobre datos históricos (¿cuántas veces al mes aparece?)
- [ ] Método de cálculo del pullback definido
- [ ] Buffer de SL definido
- [ ] Método de cálculo de la "hourly overextension" y del TP definido
- [ ] Modelo de riesgo (tamaño de posición) definido
- [ ] Modelo de costes (spread/comisión/slippage) incorporado
- [ ] Regla de timeout/invalidación del setup definida
- [ ] Filtros adicionales (noticias, ATR mínimo, días inválidos) decididos — aunque sea "ninguno por ahora"

---

*Documento complementario: `gsrs_strategy.py` — esqueleto de la máquina de estados en Python, con la configuración de este documento ya cableada y cada punto pendiente marcado explícitamente con `# ASSUMPTION` o `NotImplementedError`.*
