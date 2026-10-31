"""Run the finite J6/PRE7 offline PAPER incident matrix."""
from __future__ import annotations
import argparse
import json
from crypto_intelligence_agent.paper_incident_matrix import run_paper_incident_matrix

def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description="Executa matriz PAPER offline sem rede ou ordens.").parse_args(argv)
    print(json.dumps(run_paper_incident_matrix().sanitized_report(), ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
