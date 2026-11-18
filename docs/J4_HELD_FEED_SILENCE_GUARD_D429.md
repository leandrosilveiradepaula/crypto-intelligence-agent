# D429 — watchdog de silêncio do contrato PAPER durante a sessão

## Problema observado em dados reais (18/11/2026)

O motor AUTO4 já foi exercitado com preços públicos verdadeiros da Bybit. O ensaio real, sem J1 owner e sem conta, de **duas conexões** ao `tickers.BTCUSDT` no SHA `c8cee98e18307b49692878bc71f5feb5c6de106a` mostrou:

- Primeira sessão: ACK recebido, apenas **2 eventos aceitos**, lease **abstained**. Ela **não pode** contar como supervisão bem-sucedida.
- Segunda sessão: ACK recebido, **167 eventos aceitos**, abertura PAPER **fictícia** única, **uma** reserva hipotética de stop e **166** eventos de reconciliação, sem reemitir intenções e sem FILL. O teste usou limites de preço **absurdamente estreitos** apenas para exercitar o mecanismo, nunca para operar.
- Resultado agregado: `two_ws_sessions_incomplete`; NÃO existe prova de continuidade sem lacunas ou proteção nativa. O arquivo SQLite do laboratório foi descartado, sem escrever no owner J1 ou nos serviços existentes. Job read-only `643bacdecc3d494b8f659f08a6b7d661`.

D428 detectava ausência de cotação própria **ao encerrar** uma lease; uma conexão podia receber ticks de outros 49 contratos durante muitos segundos, perder o contrato da posição e só detectar no final. Um ACK também não atesta acompanhamento. Isto é inadequado para confiança de stop, especialmente em alavancagem elevada.

## Alteração executável em D429

O supervisor de ticker público **D386 já existente** passou a aceitar um único callback opcional `on_acked_poll`, executado a cada ciclo de leitura **depois do ACK**, inclusive nos ciclos que seguem a timeouts. Não cria thread, fila, daemon, socket adicional ou novo processo. Erro de validação encerra a lease com `lease_abstained` e causa sanitizada `held_paper_feed_silent`, sem expor símbolo, preço, identificador ou payload. Todos os clientes que não ativarem o callback preservam o comportamento anterior.

O conector D390 fornece opt-in `guard_held_feed_during_lease`. Ele só é válido junto ao roteamento de cotações da posição existente D391 e ao gate que valida cada tick PAPER. Reinicia seu marcador a cada nova tentativa de socket. Após **5 segundos de aquisição depois do ACK**, exige que **todos os contratos de posições PAPER configuradas** tenham um tick próprio realmente processado pelo D391, com timestamps de exchange e recebimento válidos e idade **máxima de 3 segundos**. Eventos de outros contratos N50 não atualizam esse estado nem dispensam a condição.

O ponte D410 encaminha explicitamente o opt-in. O ensaio de múltiplas leases **D428 liga esse guard obrigatoriamente**, preservando o lock AUTO4 e as reservas pendentes. Qualquer lease `abstained` aciona falha fechada D427 no encerramento da tentativa; não há rollback, retry financeiro, FILL inferido, ordem ou claim de supervisão ativa.

**Limitação temporal explícita:** a leitura de WebSocket pode bloquear por até 5 segundos entre chamadas. Assim, o limite de 3 segundos de idade é uma condição de **rejeição durante a observação**, não uma garantia de alerta exatamente 3 segundos após o último tick. A segurança ainda exige watchdog independente, reconciliação após crash, proteção nativa da corretora quando homologada e SLO validado; D429 NÃO garante stop em live nem 24×7.

## Testes e gates

`tests/test_j4_held_feed_silence_guard_d429.py` verifica em fixtures sem rede:

- ACK confirmado e ausência de quotes acionam `lease_abstained` por silêncio (não sucesso por ACK);
- pré-ACK jamais aciona detector nem reserva hipotética;
- feed de **outra altcoin** chegando após 5,5 s não esconde o silêncio do contrato PAPER;
- sucessivas atualizações do **próprio contrato** dentro do prazo não disparam falso alarme;
- chamadas sem PAPER roteado e opções booleanas inválidas abortam antes de rede;
- relatório não expõe IDs, preços ou dados de conta; nenhum pedido real pode ser enviado;
- regressões de D428 exigem `guard_held_feed_during_lease=True` em toda sessão.

Integração somente após gates Linux/docs/Python, Windows offline e Chrome no SHA exato e revisão das alterações. Merge de código sem publicação da VPS é permitido; **não instala supervisor contínuo**. Execução do processo owner no servidor exige gate operacional próprio e isolamento POSIX, que não deve ser contornado pelo gateway administrativo. Custo extra R$0.

**Próximo marco J6:** watchdog realmente independente do processo PAPER (detecta travamento/crash mesmo sem callback), reconciliador durável de intenções UNKNOWN, alarme mobile de falta de atualização, piloto owner não root com SLO; somente depois avaliar custos, slippage/funding/liquidação J3 e execução financeira real sob autorização separada.
