# J6/PRE9 #405 — prova causal sintética de entrada até runner PAPER

`python -m scripts.demo_full_offline_paper_lifecycle` demonstra o mesmo ciclo de intenções e posições de ponta a ponta com os módulos J2/J4/J6 existentes. A origem são velas e observações de risco 100% inventadas de `demo_durable_offline_paper_batch`: **nenhum mercado, conta ou preço de corretora**.

## Pipeline demonstrado

1. `run_durable_offline_paper_batch` emite uma hipótese quantitativa causal que passa pelo RiskGate de pesquisa e reserva **uma única** intenção OPEN em AUTO2, protegida por cursor SQLite. Não existe AUTO4 confirmado nesse instante.
2. A demo lê no AUTO2 a intenção **realmente produzida e indexada pelo cursor**, sem inventar outra identidade. Um FILL de 2 unidades é **injetado explicitamente por fixture independente**, não pelo motor de sinal. AUTO4 cria posição apenas depois de verificar o FILL e a mesma identidade; `inspect_paper_position(...opening_order_path=...)` cruza os dois bancos e prova que a abertura corresponde a AUTO2. Reinicialização mantém a mesma posição.
3. O plano de saída sobre saldo restante 50/60/70 usa os alvos de `PaperPositionBalance.tranches`: 1, 0,60 e 0,28, deixando 0,12 do runner, sem duplicar matemática dos percentuais. Cada redução recebe FILL de fixture **explícito**, jamais confundido com ordem de corretora.
4. RUNNER2 recebe marcas arbitrárias, produz `TRIGGERED_HYPOTHETICAL_ONLY` e o step PRE4 reserva 0,12 em `REDUCE_ONLY` local, sem FILL. Um restart apenas recupera PENDING. FILL de runner 0,12 é **injetado por fixture** separadamente.
5. PRE8 audita o ledger final em modo read-only com cross-check AUTO2: `RUNNER_CLOSED_PAPER_ONLY` e saldo confirmado zero, sem stop nativo, PnL ou prova de exchange.

Relatório JSON sanitizado `j6_full_offline_paper_lifecycle_v1` só contém etapas, quantidades de pesquisa, flags negativas, contagem de eventos de fixture, sem IDs de ordens, símbolos, preços, caminhos SQLite ou credentials. CLI não recebe endpoints nem paths.

## Não-objetivos e gates

Não envia ordens reais, não autentica feed, não calcula retorno financeiro, não homologa margem 50x, funding, slippage, manutenção, exchange ou testnet. AUTO2 e AUTO4 são dois arquivos independentes e o cross-check detecta divergências, mas **não fornece commit atômico conjunto**. A demonstração não implementa um reconciliador para exchange. J6 #7 permanece aberta; J1 #2/#319 owner-run da VPS segue adiado pelo PO. Sem VPS, rede, cron, daemon, deploy, migration ou custo novo.

Teste `tests/test_full_offline_paper_lifecycle.py`: sequência inteira, determinismo em duas execuções, sem socket/urllib, zero ordens/stop/live, JSON sanitizado e argumento de execução indevido rejeitado. CI docs/Linux, Windows/offline e Chrome/PAPER no head exato, review e squash sem produção.
