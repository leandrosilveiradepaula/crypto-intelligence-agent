"""Validação documental determinística, sem dependências de terceiros."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = [
    "AGENTS.md",
    "docs/PRODUCT_SPEC.md",
    "docs/ARCHITECTURE.md",
    "docs/DATA_CONTRACT.md",
    "docs/CRYPTO_REGISTRY.md",
    "docs/PROVIDER_RIGHTS.md",
    "docs/STRATEGY_SPEC.md",
    "docs/VALIDATION_PLAN.md",
    "docs/DECISIONS.md",
    "docs/JOURNEYS.md",
    "docs/STATUS.md",
    "docs/OPERATIONAL_STATE.md",
]
errors = []
texts = {}
for name in REQUIRED:
    path = ROOT / name
    if not path.is_file():
        errors.append(f"missing: {name}")
        continue
    contents = path.read_text(encoding="utf-8")
    if not contents.lstrip().startswith("# "):
        errors.append(f"missing heading: {name}")
    if len(contents.strip()) < 80:
        errors.append(f"too short: {name}")
    texts[name] = contents

agents = texts.get("AGENTS.md", "")
decisions = texts.get("docs/DECISIONS.md", "")
state = texts.get("docs/OPERATIONAL_STATE.md", "")
data_contract = texts.get("docs/DATA_CONTRACT.md", "")
registry_doc = texts.get("docs/CRYPTO_REGISTRY.md", "")
rights_doc = texts.get("docs/PROVIDER_RIGHTS.md", "")
product = texts.get("docs/PRODUCT_SPEC.md", "")
for token in ["microtarefa", "prossiga", "Codex", "GitHub"]:
    if token.lower() not in agents.lower():
        errors.append(f"missing autonomy invariant: {token}")
for token in ["D01", "D02", "D03", "D05", "D07", "D13"]:
    if token not in decisions:
        errors.append(f"missing approved decision: {token}")
for token in ["50x", "futuros", "parciais", "manual"]:
    if token.lower() not in product.lower():
        errors.append(f"missing product invariant: {token}")
for token in ["UTC", "ClosedCandle", "idempotente", "read-only"]:
    if token.lower() not in data_contract.lower():
        errors.append(f"missing J1 data contract: {token}")
for token in ["J0", "#1", "Próxima ação"]:
    if token.lower() not in state.lower():
        errors.append(f"missing operational checkpoint: {token}")
for token in ["SHA-256", "look-ahead", "internal_research_only", "CoinPaprika", "CoinGecko"]:
    if token.lower() not in registry_doc.lower():
        errors.append(f"missing crypto registry governance: {token}")

for token in ["commercial_or_public_distribution_authorized = false", "marketdata@kraken.com", "não concede", "BLOQUEADO", "R$0,00"]:
    if token.lower() not in rights_doc.lower():
        errors.append(f"missing provider rights release gate: {token}")

if errors:
    for error in errors:
        print("FAIL:", error)
    raise SystemExit(1)
print(f"PASS: {len(REQUIRED)} documentos validados")
