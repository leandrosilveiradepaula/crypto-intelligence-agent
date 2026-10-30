# J5/PRE15 #389 — visualização de journal RUNNER2 no mobile PAPER

## Contrato
O inspecionador `scripts.inspect_paper_positions` continua sendo uma aplicação offline, de leitura, com IDs de posição explícitos. O caminho legado não carrega diário RUNNER2. Se o usuário fornece os sete argumentos de observação, a CLI abre journal separado pelo `load_paper_runner_journal` e valida versão, hash local, política, vínculo ao checkpoint PAPER e staleness. Reconsulta a posição para identificar alterações entre as duas leituras. A ausência de transação atômica entre bancos permanece limitação explícita.

Os parâmetros são `--runner-journal`, `--runner-position-id`, `--runner-activation-bps`, `--runner-trail-distance-bps`, `--runner-max-tick-gap-ms`, `--runner-max-last-tick-age-ms` e `--runner-as-of-ms`. Todos são obrigatórios juntos; sem defaults ou descoberta de posições. Nenhum deles habilita coleta ou envio de ordens.

## Observações exibidas
Campo aditivo opcional `recovered_runner` na posição selecionada do JSON `paper_positions_snapshot_v1`: `state`, `observed_tick_count`, `digest_sha256`, `hypothetical_only=true`, `native_stop_verified=false`, `trailing_stop_active=false`. Nenhum preço, stop numérico, OHLC, credencial, conta ou PnL é exportado. A interface traduz o estado, marca a quantidade de ticks **fictícios**, mantém alerta de stop não instalado e não confunde gatilho hipotético com fill.

## Testes e limitações
`tests/test_paper_runner_recovery_mobile.py` cobre o caminho opcional, HTML e JSON, seleção, policy parcial, identidade incompatível, trigger hipotético, corrupção, staleness e ausência de rede/escrita. CI Linux/docs, Windows/offline, Chrome/PAPER exigidas antes de merge. Nenhuma entrega aqui é homologação de estratégia, retorno financeiro, execução automática, liquidação, J1/Top50 ou ordem real. A execução privada J1 permanece adiada pelo proprietário. D77 e D188 preservadas.
