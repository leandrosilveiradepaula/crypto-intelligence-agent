# J6/PRE5 #397 — demonstração executável do ciclo de runner PAPER

Comando: `python3 -m scripts.demo_paper_runner_close_flow` (somente modo offline, nenhum parâmetro de conta, caminho ou API). Nenhuma instalação/deploy ou VPS necessários. O script executa uma única sequência finita em um `TemporaryDirectory` privado e termina removendo os SQLite fictícios.

## Fluxo integrado
1. OPEN PAPER fictícia de 100 unidades reconhecida por evento FILL explicitamente inventado e em seguida plano de saídas 50/30/14.
2. Runner residual 6% confirmado no ledger AUTO4 e visto pelo inspetor J5, sem stop real.
3. RUNNER2 recebe ticks de mark **inventados** e observa `TRIGGERED_HYPOTHETICAL_ONLY`, sem execução.
4. RUNNER3/J6 PRE4 reserva, pela primeira vez, intenção REDUCE_ONLY PAPER de 6 unidades em AUTO4, status `PENDING` com **zero evento FILL**; J5 mostra `RUNNER_EXIT_PENDING_RECONCILIATION`.
5. Simulação de restart relê a intenção existente, não duplica ID ou saldo, não revalida RUNNER2 antigo.
6. O roteiro insere um FILL de fixture **explícito**, isolado deste executor, e o replay AUTO4 confirma saldo 0; J5 agora mostra `RUNNER_CLOSED_PAPER_ONLY`.

O JSON público informa apenas modalidade, estados/contagens e flags negativas. Não imprime símbolo, preços/ticks, credenciais, caminhos SQLite, mercado real, lucro ou endpoint. `orders_reais_enviadas=false`, `stop_nativo_verificado=false`, `trading_live_autorizado=false`. O preenchimento explícito final **não prova um fill em Binance/Bybit**; pertence apenas ao roteiro sintético local.

## Testes e limites
`tests/test_paper_runner_close_demo.py` verifica determinismo, sequência, contabilidade, no-network, stdout sanitizado, rejeição de flags de API/conta/arquivos e limpeza do diretório TEMP. Os próprios módulos AUTO4/RUNNER2/J6 são reutilizados, sem executor paralelo. CI Linux/docs, Windows/offline e Chrome/PAPER no SHA final e revisão antes de merge.

O produto final prevê entradas e saídas automáticas (D77), mas esta demonstração não é pesquisa de retorno, paper prospectivo com dados reais, testnet/live, stop de venue, homologação financeira ou autorização de ordens. J1 #2/#319 ainda depende do owner-run privado adiado; J6 #7 permanece aberta. R$ 0 adicional.
