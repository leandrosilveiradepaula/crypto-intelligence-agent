# J2/J4 D400 — reinício de sequência após reconexão do WebSocket público

## Problema funcional
O supervisor público D386 descarta snapshots ao desconectar e exige novo ACK + snapshot. A Bybit pode atribuir um novo cross-sequence menor ao iniciar outra sessão. O consumidor PAPER D391 mantinha o último cross-sequence da sessão anterior e rejeitava o novo snapshot legítimo como regressão, interrompendo a avaliação de stops, parciais e trailing na reconexão.

## Contrato da correção
- D386 recebe callback opcional `on_session_reset`, executado **antes da construção de cada nova conexão**, inclusive primeira tentativa. Sem callback, execução D386 existente permanece igual.
- D391 oferece `begin_new_market_session()` para limpar somente o baseline de sequência recebido via socket. A marca temporal monotônica por símbolo **não** é apagada durante reconexões, impedindo replay retroativo de preço enquanto o processo existir.
- O book D385 continua exigindo novo subscription ACK e snapshot; os journals AUTO4 e RUNNER não são reiniciados, o histórico não é regravado, UNKNOWN permanece bloqueante e nenhum FILL é criado por conexão.
- Falha do reset é propagada **antes** de abrir um novo socket. Sem bypass do age/gap gate nem aumento da confiança na fonte.
- A aplicação PAPER explícita conecta `on_quote=router.process` e `on_session_reset=router.begin_new_market_session`. Sem esse segundo callback, não existe garantia de recuperação do consumidor em reconnect.
- A marca temporal é mantida somente em memória: após reinício de processo, os journals AUTO4 preservam idempotência financeira; replay exato de preço pode reavaliar decisão, nunca comprovar FILL. O serviço 24×7 ainda não existe.

## Testes e gates
```bash
python -m unittest discover -s tests -p 'test_bybit_public_ticker_supervisor_d386.py' -v
python -m unittest discover -s tests -p 'test_paper_intrahour_quote_router_d391.py' -v
```
Cobrir recuperação depois de sequência 9 → 1, reset antes do socket, rejeição de tick igual/antigo após reconnect, não duplicação de reservas PAPER e ausência de ordens financeiras. A CI Linux/docs + Windows/offline e PAPER/Chrome afetada deve passar no SHA exato antes do merge.

## Limites
Esta alteração apenas prepara integração offline, sem autenticação, conexão real, envio de ordens, instalação VPS, alterações de coleta J1, migration, pagamento ou habilitação live. O piloto real Bybit, medições de 50+posições, gestão de stale cross-process e auditoria independente J1 #671 continuam pendentes.
