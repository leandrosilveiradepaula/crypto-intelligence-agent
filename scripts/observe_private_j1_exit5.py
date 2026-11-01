"""Offline read-only J1 EXIT5 status for owner-private JSON artifacts.

Never starts a worker, opens the market/database or monitors in background.
"""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_ops_status import (
    PrivateJ1StatusError, observe_private_exit5,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--allow-private-readonly-status", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = observe_private_exit5(
            directory=args.directory,
            allow_private_readonly_status=args.allow_private_readonly_status,
        )
    except PrivateJ1StatusError as exc:
        report = {
            "status": str(exc), "audit_accepted": False,
            "marketwide_top50_verified": False,
            "network_requests_by_observer": 0,
            "data_written_by_observer": False, "orders_sent": False,
        }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return int(report["status"] not in {
        "concluido_amostra_revisada_auditada",
        "aguardando_proximo_fechamento_informado",
        "progresso_informado_sem_resultado", "sem_resultado_final",
    })


if __name__ == "__main__":
    raise SystemExit(main())