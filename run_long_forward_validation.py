"""
LastEdge — Long Forward Validation CLI Runner (P5.3)
=====================================================
Ejecuta y monitorea sesiones de validación de estabilidad a largo plazo (24h, 72h, 7d).
"""

from __future__ import annotations

import sys
import json
from services.bot_service import get_bot_service


def main():
    print("=" * 75)
    print("⏱️ LastEdge — Long Forward Validation & Longevity Engine (P5.3)")
    print("=" * 75)

    bot_svc = get_bot_service()

    profile = "24h"
    if "--72h" in sys.argv:
        profile = "72h"
    elif "--7d" in sys.argv:
        profile = "7d"

    if "--list" in sys.argv:
        sessions = bot_svc.list_long_forward_sessions()
        print("\n📜 HISTORIAL DE SESIONES DE VALIDACIÓN (PERSISTIDAS EN BD):")
        print("-" * 75)
        if not sessions:
            print("Sin sesiones registradas aún en SQLite.")
        else:
            for s in sessions:
                print(f"ID: {s['session_id']:<36} | Perfil: {s['profile']:<4} | Status: {s['status']:<11} | Score: {s.get('forward_score', 0):>5.1f}/100 | Veredicto: {s.get('final_verdict', 'N/A')}")
        print("-" * 75)
        sys.exit(0)

    if "--session" in sys.argv:
        try:
            idx = sys.argv.index("--session")
            session_id = sys.argv[idx + 1]
            details = bot_svc.get_long_forward_session(session_id)
            print(f"\n🔍 DETALLES DE SESIÓN [{session_id}]:")
            print(json.dumps(details, indent=2))
            sys.exit(0)
        except Exception as e:
            print(f"Error consultando sesión: {e}")
            sys.exit(1)

    if "--start" in sys.argv:
        res = bot_svc.start_long_forward_session(profile=profile)
        print(f"\n🚀 {res.get('message', 'Sesión iniciada')}")
        sys.exit(0)

    if "--stop" in sys.argv:
        res = bot_svc.stop_long_forward_session()
        print("\n🛑 Sesión de validación finalizada.")
        print(json.dumps(res.get("report", {}), indent=2))
        sys.exit(0)

    # Estado por defecto
    report = bot_svc.get_long_forward_status()
    verdict = report.get("verdict", "STABLE")
    icon = "✅ STABLE" if verdict == "STABLE" else ("⚠️ DEGRADED" if verdict == "DEGRADED" else "❌ UNSTABLE")
    mem = report.get("memory_telemetry", {})
    resil = report.get("resilience_telemetry", {})

    print(f"\nEstado Actual: {icon}")
    print(f"Perfil de Sesión: {report.get('session_profile', '24h')} (Activo: {report.get('session_active', False)})")
    print(f"\n📊 Telemetría de Memoria:")
    print(f"  • Memoria RSS Actual: {mem.get('current_rss_mb', 0)} MB")
    print(f"  • Muestra Mín / Máx / Promedio: {mem.get('min_rss_mb', 0)} / {mem.get('max_rss_mb', 0)} / {mem.get('avg_rss_mb', 0)} MB")
    print(f"  • Tasa de Crecimiento (Slope): {mem.get('memory_growth_slope_mb_per_hour', 0)} MB/hora")
    print(f"  • Muestras Totales Tomadas: {mem.get('total_samples', 0)}")

    print(f"\n🛡️ Telemetría de Resiliencia:")
    print(f"  • Reconexiones Totales: {resil.get('reconnections_total', 0)}")
    print(f"  • Fallos Recuperados: {resil.get('failures_recovered_total', 0)}")
    print(f"  • Anomalías Registradas: {resil.get('total_anomalies_logged', 0)}")

    anomalies = report.get("anomalies", [])
    if anomalies:
        print("\n⚠️ ÚLTIMAS ANOMALÍAS REGISTRADAS:")
        for a in anomalies[-5:]:
            print(f"  [{a['timestamp'][:19]}] [{a['severity']}] {a['anomaly_type']}: {a['description']}")

    if "--json" in sys.argv:
        print("\n--- JSON OUTPUT ---")
        print(json.dumps(report, indent=2))

    sys.exit(0 if verdict != "UNSTABLE" else 1)


if __name__ == "__main__":
    main()
