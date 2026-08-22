@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul 2>&1

:: ============================================================
:: LastEdge Exit Research Protocol
:: Lanzador interactivo unificado para cualquier simbolo
:: ============================================================

echo.
echo ====================================================
echo   LastEdge Exit Research Protocol
echo ====================================================
echo.

:: -- Verificar que estamos en el directorio correcto --
if not exist "run_exit_research.py" (
    echo [ERROR] Ejecutar desde el directorio raiz del proyecto.
    echo         cd c:\BOT-MT5
    echo         run_exit_research.bat
    pause
    exit /b 1
)

:: -- Verificar Python --
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Asegurate de tener Python 3.10+ en el PATH.
    pause
    exit /b 1
)

:: -- Descubrir simbolos registrados via Python (separados por espacio) --
echo Descubriendo simbolos registrados...
python -c "from core.exit_research.strategy_adapter import _STRATEGY_REGISTRY; print(' '.join(_STRATEGY_REGISTRY.keys()))" > _tmp_symbols.txt 2>nul
set /p _REG_SYMBOLS=<_tmp_symbols.txt
del _tmp_symbols.txt 2>nul

if "!_REG_SYMBOLS!"=="" (
    echo [WARNING] No se pudo leer el registro de simbolos. Usando lista estatica.
    set "_REG_SYMBOLS=EURUSD XAUUSD BTCEUR"
)

echo.
echo Simbolos disponibles en el sistema: !_REG_SYMBOLS!
echo.

:: -- Construir menu de simbolos (usando call para que se expanda correctamente) --
set "_SYM_COUNT=0"
call :count_symbols

:select_symbol
echo Seleccione el simbolo:
call :show_symbols
set /a "_IDX_LAST=!_SYM_COUNT!+1"
echo [!_IDX_LAST!] Otro (introducir manualmente)
echo.
set /p _SYM_OPT="> "

:: Validar opcion numerica
set "SYMBOL="
call :match_symbol

:: Opcion manual
if "!_SYM_OPT!"=="!_IDX_LAST!" (
    set /p SYMBOL="Introduzca el simbolo (ej: GBPUSD): "
    call :toupper SYMBOL
)

if "!SYMBOL!"=="" (
    echo Opcion invalida. Intente de nuevo.
    echo.
    goto select_symbol
)

echo.
echo Simbolo seleccionado: !SYMBOL!
echo.

:: -- Descubrir estrategia activa desde rules_config.json --
set "_SYM_FOR_CFG=!SYMBOL!"
python -c "import json,sys; cfg=json.load(open('rules_config.json',encoding='utf-8')); sym=sys.argv[1]; s=cfg.get(sym,{}).get('strategy','(default)'); print(s)" "!_SYM_FOR_CFG!" > _tmp_strat.txt 2>nul
set /p _CFG_STRATEGY=<_tmp_strat.txt
del _tmp_strat.txt 2>nul

if "!_CFG_STRATEGY!"=="" set "_CFG_STRATEGY=(default)"
echo Estrategia activa segun rules_config.json: !_CFG_STRATEGY!
echo.

:: -- Seleccion de velas --
:select_bars
echo Seleccione el numero de velas:
echo [1]  5000   (rapido, ~5 min)
echo [2] 10000   (medio,  ~10 min)
echo [3] 15000   (completo, ~20 min)
echo [4] 20000   (full dataset recomendado, ~30 min)
echo [5] Personalizado
echo.
set /p _BARS_OPT="> "

if "!_BARS_OPT!"=="1" ( set "BARS=5000"  ) else ^
if "!_BARS_OPT!"=="2" ( set "BARS=10000" ) else ^
if "!_BARS_OPT!"=="3" ( set "BARS=15000" ) else ^
if "!_BARS_OPT!"=="4" ( set "BARS=20000" ) else ^
if "!_BARS_OPT!"=="5" (
    set /p BARS="Introduce el numero de velas (minimo 5000): "
) else (
    echo Opcion invalida.
    echo.
    goto select_bars
)

if "!BARS!"=="" (
    echo El numero de velas no puede estar vacio.
    goto select_bars
)

echo.
echo Velas: !BARS!
echo.

:: -- Seleccion de modo --
:select_mode
echo Que desea ejecutar?
echo.
echo [1] Exit Research completo
echo     ^(incluye Walk-Forward y Monte Carlo integrados^)
echo.
set /p _MODE_OPT="> "

if "!_MODE_OPT!"=="1" (
    set "MODE=Protocolo Completo"
) else (
    echo Opcion invalida.
    echo.
    goto select_mode
)

:: -- Confirmacion --
echo.
echo ======================================
echo              RESUMEN
echo ======================================
echo   Simbolo:     !SYMBOL!
echo   Estrategia:  !_CFG_STRATEGY!
echo   Velas:       !BARS!
echo   Modo:        !MODE!
echo ======================================
echo.

:confirm
set /p _CONF="Continuar? [Y/N]: "
if /i "!_CONF!"=="N" (
    echo.
    echo Ejecucion cancelada.
    endlocal
    pause
    exit /b 0
)
if /i not "!_CONF!"=="Y" (
    echo Escriba Y para continuar o N para cancelar.
    goto confirm
)

:: -- Ejecucion --
echo.
echo ======================================
echo [1/1] Exit Research + WF + MC
echo ======================================
echo.

python run_exit_research.py --symbol !SYMBOL! --bars !BARS!
set "_EXIT_CODE=!errorlevel!"

echo.
if "!_EXIT_CODE!"=="0" (
    echo ====================================
    echo   Protocol Finished  [OK]
    echo ====================================
    echo   Exit Research      OK
    echo   Walk-Forward       OK  ^(integrado^)
    echo   Monte Carlo        OK  ^(integrado^)
    echo ====================================
    echo   Resultados en:
    echo   backtest_results/exit_research/
    echo ====================================
) else (
    echo ====================================
    echo   [ERROR] El protocolo finalizo con errores.
    echo   Revise el log anterior para detalles.
    echo ====================================
)

echo.
endlocal
pause
exit /b !_EXIT_CODE!


:: ============================================================
:: Subrutinas
:: ============================================================

:count_symbols
set "_SYM_COUNT=0"
for %%s in (!_REG_SYMBOLS!) do (
    set /a "_SYM_COUNT+=1"
    set "_SYM_!_SYM_COUNT!=%%s"
)
exit /b 0

:show_symbols
set "_IDX=0"
for %%s in (!_REG_SYMBOLS!) do (
    set /a "_IDX+=1"
    echo [!_IDX!] %%s
)
exit /b 0

:match_symbol
set "_IDX=0"
for %%s in (!_REG_SYMBOLS!) do (
    set /a "_IDX+=1"
    if "!_SYM_OPT!"=="!_IDX!" (
        set "SYMBOL=%%s"
    )
)
exit /b 0

:toupper
for %%A in (a b c d e f g h i j k l m n o p q r s t u v w x y z) do (
    call set "%1=%%%1:%%A=%%A%%"
)
exit /b 0
