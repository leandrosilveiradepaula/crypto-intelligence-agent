# J2/D418 — observação pública N50 sustentada, limitada e sem ordens

## Necessidade comprovada na VPS

Em 18/11/2026 UTC, o proprietário do feed executou uma observação
read-only de **122,105 segundos** na Bybit pública V5 linear usando o
código principal pinado em
`4beaffa18096c269000e9e3f8155e52a51bb64c2` e o escopo N50
da epoch J1, somente leitura, via job auditável da VPS
`560d1fa846c34f40b86a4b983abe7f22`.

Evidências count-only reais:

- `status=lease_completed`, `sessions_attempted=1`,
  `subscriptions_acknowledged=1`, **zero reconexões e zero falhas**;
- **23.526** quadros de ticker aceitos pós-ACK; 23.759 quadros vistos;
- **5 pings, 5 pongs**, sem timeouts de heartbeat;
- **50/50 contratos com quote válida** ao menos uma vez, sem contrato
  jamais observado nem inelegível, mas **46/50 frescos ao final**;
  os outros 4 estavam previamente elegíveis e expiraram;
- zero callbacks com atraso exchange→recepção acima de 3 s;
- `owner_scope_unchanged_after_lease=true`,
  `j1_mutated=false`, `orders_sent=false`;
- `finite_coverage_fresh_at_end=false`,
  `continuous_24x7_verified=false`, `approved_for_live_use=false`.

O experimento não permite afirmar que os quatro instrumentos estavam sem
negociações, nem que 24×7 já está implementado. Pings respondidos
comprovam somente a sessão observada. A média de atualizações também não
é preço de execução garantido.

## Entrega de engenharia D418

O código reaproveita **D406** para revalidar a epoch J1, **D385/D386**
para snapshot/delta e supervisor de protocolo Bybit, e **D390/D416**
para contagem de cobertura e frescor por timestamp da exchange.
Não duplica ranking, ticker decoder, websocket transport, writer J1 ou
ledger PAPER.

- `crypto_intelligence_agent/j2_n50_sustained_public_operator_d418.py`
  permite uma única observação de **60 a 900 segundos**, 1 a 2 sessões
  de reconexão, 1.000 a 200.000 frames, 50 ativos N50 mais até 50
  instrumentos opcionais monitorados. São limites explícitos, não um
  daemon nem um serviço ativo.
- A leitura do ponteiro/cache privado owner requer opt-ins antes do
  transporte; símbolo, preço, diretório e ID privado não aparecem no
  relatório. A epoch é lida antes e depois do lease. Mudança de epoch,
  digest ou membros, ou indisponibilidade na segunda leitura, torna
  `owner_scope_unchanged_after_lease=false` e degrada o status.
- Dados pré-ACK só podem reconstruir estado depois do ACK, nunca
  acionar PAPER; reconnect zera o monitor de cobertura por sessão.
  Contagens da sessão final mantêm as quatro categorias disjuntas
  D416: nunca validado, validado inelegível, elegível expirado e fresco
  ao fim. Rejeição por clock ou sequência continua fail-closed.
- `scripts/probe_current_j1_n50_sustained_bybit_ws_d418.py` oferece
  operação **opt-in**, sem instalação; `--seconds`, `--max-frames`
  e `--max-sessions` têm limites de validação. A opção `--positions`
  é uma lista explícita de contratos de PAPER a **observar**, sem
  ler/alterar o journal ou executar reservas de ordens.
- `exit 0` significa somente que um lease público concluiu e
  **observou ao menos uma cotação elegível de todos os contratos
  solicitados** na epoch revalidada. Não implica cobertura
  simultaneamente fresca, proteção de stops, rentabilidade ou saúde
  de entradas. Frescor final é um campo distinto e exigido por gate
  de qualquer candidato/posição.
- Por construção, `approved_for_signals=false`,
  `continuous_24x7_verified=false`, `approved_for_live_use=false`,
  `paper_reservations_enabled=false` e `orders_sent=false`.
  A página J5/D417 importa o contrato anterior D406, não assume
  automaticamente o novo D418 como relatório autenticado.

## Testes, escopo de release e próximas etapas

`tests/test_j2_n50_sustained_public_operator_d418.py` cobre lease
sintético de 60 segundos e heartbeat, 50+1 contratos incluindo posição
fora do ranking, desconexão/reconnect com snapshot novo, mudança da
epoch, epoch indisponível, sanitização e opt-ins ausentes. Tudo sem rede.
Os testes D385/D386/D390/D406/D410/D416 permanecem aplicáveis.

**Sem implantação de daemon**, sem modificar timers, journal ou
serviços J1, sem requisição REST de conta, sem autenticação privada,
sem instalação de stop, sem ordens ou gastos. A próxima frente de
produto é o operador **24×7 real** com atualização de epoch durante
a sessão, watchdog, persistência mínima de saúde sanitizada e conexão
ao acompanhamento de posições PAPER, submetido a gate explícito de
release/produção. Este piloto finito não substitui esse trabalho.

Custo adicional: R$ 0,00.
