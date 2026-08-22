#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Backtesting y Seguimiento de Señales
Registra todas las señales generadas y permite análisis de rendimiento
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd

class BacktestTracker:
    def __init__(self, data_file: str = "backtest_data.json"):
        self.data_file = data_file
        self.signals_data = self.load_data()
    
    def load_data(self) -> Dict:
        """Carga los datos existentes del archivo"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error cargando datos: {e}")
                return {"signals": [], "metadata": {"created": datetime.now().isoformat()}}
        else:
            return {"signals": [], "metadata": {"created": datetime.now().isoformat()}}
    
    def save_data(self):
        """Guarda los datos al archivo"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.signals_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando datos: {e}")
    
    def add_signal(self, signal_data: Dict):
        """Registra una nueva señal"""
        
        # Función para convertir pandas Series y otros tipos no serializables
        def make_serializable(value):
            if hasattr(value, 'iloc'):  # pandas Series
                return float(value.iloc[0]) if len(value) > 0 else None
            elif hasattr(value, 'item'):  # numpy types
                return value.item()
            elif isinstance(value, (int, float, str, bool, type(None))):
                return value
            else:
                return str(value)
        
        signal_entry = {
            "id": len(self.signals_data["signals"]) + 1,
            "timestamp": datetime.now().isoformat(),
            "symbol": make_serializable(signal_data.get("symbol")),
            "direction": make_serializable(signal_data.get("direction")),
            "entry_price": make_serializable(signal_data.get("entry_price")),
            "stop_loss": make_serializable(signal_data.get("stop_loss")),
            "take_profit": make_serializable(signal_data.get("take_profit")),
            "confidence": make_serializable(signal_data.get("confidence")),
            "strategy": make_serializable(signal_data.get("strategy")),
            "risk_reward": make_serializable(signal_data.get("risk_reward")),
            "lot_size": make_serializable(signal_data.get("lot_size")),
            "status": "PENDING",  # PENDING, ACCEPTED, REJECTED, CLOSED
            "result": None,  # WIN, LOSS, BREAKEVEN
            "profit_loss": None,
            "close_price": None,
            "close_time": None,
            "duration_minutes": None,
            "notes": make_serializable(signal_data.get("notes", ""))
        }
        
        self.signals_data["signals"].append(signal_entry)
        self.save_data()
        return signal_entry["id"]
    
    def update_signal_status(self, signal_id: int, status: str, **kwargs):
        """Actualiza el estado de una señal"""
        for signal in self.signals_data["signals"]:
            if signal["id"] == signal_id:
                signal["status"] = status
                signal.update(kwargs)
                if status == "CLOSED" and "close_time" not in kwargs:
                    signal["close_time"] = datetime.now().isoformat()
                    
                    # Calcular duración
                    if signal.get("timestamp"):
                        start_time = datetime.fromisoformat(signal["timestamp"])
                        end_time = datetime.fromisoformat(signal["close_time"])
                        signal["duration_minutes"] = int((end_time - start_time).total_seconds() / 60)
                
                self.save_data()
                return True
        return False
    
    def get_statistics(self, days: int = 30) -> Dict:
        """Genera estadísticas de rendimiento"""
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_signals = [
            s for s in self.signals_data["signals"] 
            if datetime.fromisoformat(s["timestamp"]) >= cutoff_date
        ]
        
        if not recent_signals:
            return {"error": "No hay señales en el período especificado"}
        
        closed_signals = [s for s in recent_signals if s["status"] == "CLOSED"]
        
        if not closed_signals:
            return {"error": "No hay señales cerradas en el período especificado"}
        
        # Estadísticas básicas
        total_signals = len(recent_signals)
        closed_count = len(closed_signals)
        wins = len([s for s in closed_signals if s.get("result") == "WIN"])
        losses = len([s for s in closed_signals if s.get("result") == "LOSS"])
        breakevens = len([s for s in closed_signals if s.get("result") == "BREAKEVEN"])
        
        win_rate = (wins / closed_count * 100) if closed_count > 0 else 0
        
        # P&L
        total_pnl = sum([s.get("profit_loss", 0) for s in closed_signals])
        avg_win = sum([s.get("profit_loss", 0) for s in closed_signals if s.get("result") == "WIN"]) / wins if wins > 0 else 0
        avg_loss = sum([s.get("profit_loss", 0) for s in closed_signals if s.get("result") == "LOSS"]) / losses if losses > 0 else 0
        
        # Por símbolo
        symbols_stats = {}
        for symbol in set([s["symbol"] for s in closed_signals]):
            symbol_signals = [s for s in closed_signals if s["symbol"] == symbol]
            symbol_wins = len([s for s in symbol_signals if s.get("result") == "WIN"])
            symbol_total = len(symbol_signals)
            symbol_pnl = sum([s.get("profit_loss", 0) for s in symbol_signals])
            
            symbols_stats[symbol] = {
                "total_signals": symbol_total,
                "wins": symbol_wins,
                "win_rate": (symbol_wins / symbol_total * 100) if symbol_total > 0 else 0,
                "total_pnl": symbol_pnl
            }
        
        # Por estrategia
        strategies_stats = {}
        for strategy in set([s["strategy"] for s in closed_signals if s.get("strategy")]):
            strategy_signals = [s for s in closed_signals if s.get("strategy") == strategy]
            strategy_wins = len([s for s in strategy_signals if s.get("result") == "WIN"])
            strategy_total = len(strategy_signals)
            strategy_pnl = sum([s.get("profit_loss", 0) for s in strategy_signals])
            
            strategies_stats[strategy] = {
                "total_signals": strategy_total,
                "wins": strategy_wins,
                "win_rate": (strategy_wins / strategy_total * 100) if strategy_total > 0 else 0,
                "total_pnl": strategy_pnl
            }
        
        return {
            "period_days": days,
            "total_signals": total_signals,
            "closed_signals": closed_count,
            "pending_signals": total_signals - closed_count,
            "wins": wins,
            "losses": losses,
            "breakevens": breakevens,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "average_win": round(avg_win, 2),
            "average_loss": round(avg_loss, 2),
            "profit_factor": round(abs(avg_win * wins / (avg_loss * losses)) if avg_loss != 0 and losses > 0 else 0, 2),
            "symbols": symbols_stats,
            "strategies": strategies_stats
        }
    
    def generate_html_report(self, days: int = 30) -> str:
        """Genera un reporte HTML similar al de FundedEA"""
        stats = self.get_statistics(days)
        
        if "error" in stats:
            return f"<html><body><h1>Error</h1><p>{stats['error']}</p></body></html>"
        
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_signals = [
            s for s in self.signals_data["signals"] 
            if datetime.fromisoformat(s["timestamp"]) >= cutoff_date and s["status"] == "CLOSED"
        ]
        
        html = f"""
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html>
<head>
    <title>Reporte de Backtesting: Bot Trading Discord</title>
    <style type="text/css">
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .header {{ text-align: center; margin: 20px 0; }}
        .stats-table {{ max-width: 800px; margin: 0 auto; }}
        .positive {{ color: green; font-weight: bold; }}
        .negative {{ color: red; font-weight: bold; }}
        .neutral {{ color: blue; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Reporte de Backtesting</h1>
        <h2>Bot Trading Discord - Últimos {days} días</h2>
        <p>Período: {cutoff_date.strftime('%Y-%m-%d')} - {datetime.now().strftime('%Y-%m-%d')}</p>
    </div>
    
    <table class="stats-table">
        <tr><td>Total de Señales</td><td>{stats['total_signals']}</td></tr>
        <tr><td>Señales Cerradas</td><td>{stats['closed_signals']}</td></tr>
        <tr><td>Señales Pendientes</td><td>{stats['pending_signals']}</td></tr>
        <tr><td>Operaciones Ganadoras</td><td class="positive">{stats['wins']} ({stats['win_rate']}%)</td></tr>
        <tr><td>Operaciones Perdedoras</td><td class="negative">{stats['losses']}</td></tr>
        <tr><td>Operaciones en Breakeven</td><td class="neutral">{stats['breakevens']}</td></tr>
        <tr><td>P&L Total</td><td class="{'positive' if stats['total_pnl'] > 0 else 'negative'}">{stats['total_pnl']} EUR</td></tr>
        <tr><td>Ganancia Promedio</td><td class="positive">{stats['average_win']} EUR</td></tr>
        <tr><td>Pérdida Promedio</td><td class="negative">{stats['average_loss']} EUR</td></tr>
        <tr><td>Factor de Beneficio</td><td>{stats['profit_factor']}</td></tr>
    </table>
    
    <h3>Rendimiento por Símbolo</h3>
    <table>
        <tr><th>Símbolo</th><th>Señales</th><th>Ganadas</th><th>Win Rate</th><th>P&L Total</th></tr>
"""
        
        for symbol, data in stats['symbols'].items():
            html += f"""
        <tr>
            <td>{symbol}</td>
            <td>{data['total_signals']}</td>
            <td>{data['wins']}</td>
            <td>{data['win_rate']:.1f}%</td>
            <td class="{'positive' if data['total_pnl'] > 0 else 'negative'}">{data['total_pnl']:.2f}</td>
        </tr>"""
        
        html += """
    </table>
    
    <h3>Historial de Operaciones</h3>
    <table>
        <tr><th>#</th><th>Fecha</th><th>Símbolo</th><th>Dirección</th><th>Entrada</th><th>Salida</th><th>Resultado</th><th>P&L</th><th>Duración</th></tr>
"""
        
        for signal in recent_signals:
            result_class = "positive" if signal.get("result") == "WIN" else "negative" if signal.get("result") == "LOSS" else "neutral"
            html += f"""
        <tr>
            <td>{signal['id']}</td>
            <td>{datetime.fromisoformat(signal['timestamp']).strftime('%Y-%m-%d %H:%M')}</td>
            <td>{signal['symbol']}</td>
            <td>{signal['direction']}</td>
            <td>{signal.get('entry_price', 'N/A')}</td>
            <td>{signal.get('close_price', 'N/A')}</td>
            <td class="{result_class}">{signal.get('result', 'N/A')}</td>
            <td class="{result_class}">{signal.get('profit_loss', 0):.2f}</td>
            <td>{signal.get('duration_minutes', 0)} min</td>
        </tr>"""
        
        html += """
    </table>
</body>
</html>
"""
        return html
    
    def export_to_csv(self, filename: str = None):
        """Exporta los datos a CSV para análisis externo"""
        if not filename:
            filename = f"backtest_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        df = pd.DataFrame(self.signals_data["signals"])
        df.to_csv(filename, index=False)
        return filename

# Instancia global del tracker
backtest_tracker = BacktestTracker()

def get_backtest_tracker() -> BacktestTracker:
    return backtest_tracker