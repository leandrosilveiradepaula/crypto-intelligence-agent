# J1 D267 — diagnóstico único e somente leitura do estado operacional WebSocket

## Por que existe

A J1 já tem código para WebSocket público Bybit, journaling SQLite independente, exclusão mútua e um template `systemd` OFF por default. O problema de #429 não é falta de outro coletor, mas evidência externa de operação contínua: **nenhum teste unitário, último health JSON ou status systemd isolado comprova um dia de candles fechados reais sem lacuna**. D267 reúne observações em um relatório sanitizado único, sem alterar serviço ou dados.

Entradas: `crypto_intelligence_agent/j1_ws_private_readiness.py` (PIT, janela local 24h, capacidade e gaps) e `j1_ws_service_health.py` (último relatório local, nunca certificado de processo). Saída: status atual da unidade **fixa** `cia-j1-ws-owner.service`, saúde e janela de pesquisa, e o primeiro bloqueio operacional para inspeção.

## Contrato de segurança

`scripts.read_j1_ws_operational_preflight` é OFF por default. Exige `--allow-private-readonly-preflight`, POSIX, uid=euid não-root, caminho privado absoluto, UTC válido. Executa somente uma consulta `systemctl show cia-j1-ws-owner.service --no-pager --property=Id,LoadState,ActiveState,SubState,MainPID,User,UnitFileState,Result`, via argumentos fixos `shell=False`, timeout 3s, sem stderr impresso, sem credenciais no ambiente e sem retry. Exige unidade exata, campos completos/únicos e valores allowlisted; ativo/running requer PID positivo e User exatamente `cia-probe`. Nunca imprime PID, usuário, path, comando completo, símbolo, preço, turnover, URL nem credenciais.

Depois, reutiliza apenas observadores existentes, sem criar SQLite ou WS. Valida contagens internas (1..52 membros, completos+faltantes), todos os flags de autorização false. Uma resposta falsa, duplicada, atrasada, malformada ou um estado de unidade incoerente vira `abstain`. O relatório se limita às classes `service_uninstalled`, `service_inactive`, `ws_private_unavailable`, `ws_window_incomplete`, `ws_health_stale_or_missing`, `evidence_insufficient_for_continuity`.

**Invariantes mesmo com unidade ativa e 52×24 candles locais:** `worker_running_verified=false`, `continuous_collector_verified=false`, `source_authenticated=false`, `marketwide_top50_verified=false`, `live_trading_authorized=false`, `orders_sent=false`, `database_modified=false`, `network_requests=0`. Campo `service_manager_observed_running=true` significa SOMENTE o estado reportado pelo systemd em uma consulta instantânea, não liveness confirmado independentemente nem continuidade.

## Testes e gates

Testes portáveis `tests/test_j1_ws_operational_preflight.py`: opt-in desativado deve impedir até a consulta systemd; root, caminho relativo e clock malformado abstêm; parser rejeita unit diferente, User root, PID inválido, campos duplicados ou indevidos e estados contraditórios; leitura inexistente/inativa/saudável/incompleta/missing/stale; readiness/health manipulados falham fechados; timeout e resposta maliciosa nunca são expostos. Executar também `test_j1_ws_private_readiness.py`, `test_j1_ws_service.py`, `test_j1_ws_owner_readonly.py`, CI Linux/docs Windows/offline Chrome/PAPER no head exato. CI verde prova **software**, nunca estado da VPS.

Depois de PR/merge sem deploy e SHA exato, **somente** este comando, sob `cia-probe`, com pasta WS privada existente verificada, pode ser executado pelo proprietário:

```bash
python -m scripts.read_j1_ws_operational_preflight \
  --directory /CAMINHO/WS/PRIVADO/EXISTENTE \
  --allow-private-readonly-preflight
```

O caminho precisa ser o do **journal WS** (`ws-confirmed.sqlite` + `ws-reviewed-scope.json`), e **NÃO** o SQLite REST de `j1-global-closed24h-private/run` usado em D265. Não inventar diretório nem ligar serviço caso não exista: `service_uninstalled` é resultado válido do diagnóstico. Se o serviço está OFF, instalar/ativar sistema é gate **separado** sujeito a autorização e verificações de produção. Nenhuma chamada Bybit, WS, REST, transação, timer, migration, release ou negociação ocorre aqui.

#429 permanece aberta até a continuidade real observada por múltiplos fechamentos e scope PIT seguro; #319 exige Top50 crypto-only, #2 aceite completo J1. `docs/OPERATIONAL_STATE.md` registra checkpoint e próximo passo, não estados fictícios.
