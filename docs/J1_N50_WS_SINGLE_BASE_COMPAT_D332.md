# J1/D332 — um caractere de base USDT no validador N50 WS

## Incidente comprovado

Em 13/11/2026, a D331 operacional (SHA `c1fbd4cd46bba108be14859b9a04bb4184c3e91f`) iniciou o lease de WS N50 em **14:59:31 UTC**, processou 677 frames, uma confirmação ACK, descartou 50 preACK e gravou 42 candles confirmados postclose. Encerramento às **15:00:03 UTC**, exit65, `failure_category=ws_scope_member_invalid`, sem auditoria 50/50 (`confirmed_contracts=0` é default no ramo de erro). O serviço OnFailure restaurou N2 às 15:00:05 UTC, desativando ambos timers WS; 0 GET e nenhuma ordem. Evidência pública sanitizada em issues #585 e #429.

**A classificação D331 NÃO expõe a identidade do frame.** `ws_scope_member_invalid` aglutina os literais locais `WS symbol not present in reviewed scan` e `Bybit symbol and quote currency mismatch`. Na cadeia `supervise_ws_research`, um tópico deve estar na lista de `scope.contracts`, antes do parser. Assim, a hipótese forte é discrepância de **formato** na transformação para `stage_bybit_linear_kline`, não ausência de assinatura. Sem o frame privado, a causa exata continua **não demonstrada**.

## Divergência concreta do código (independente de payload)

- `j1_auto_usdt_perp._SYMBOL`: `[A-Z0-9]{1,28}USDT`. Um ticker com uma letra de base mais USDT é *tecnicamente candidato* (NÃO identidade de cripto certificada).
- `bybit_linear_candle_research._SYMBOL` na D331: `^[A-Z0-9]{2,30}(?:USDT|USDC)$`. Um membro autorizado pelo universo, com base de uma letra, seria rejeitado após o ACK em `stage_bybit_linear_kline`.
- D332 altera **somente o mínimo 2→1**, preservando máximo 30, ASCII uppercase, quote USDT/USDC e todas as exigências: `scope.member`, lançamento, contrato `LinearPerpetual` `Trading`, clock UTC/servidor/recebimento, preço/OHLC/volume/turnover, hashes e idempotência SQLite. Não permite símbolo não inscrito na coorte nem TradFi fora da seleção.
- A taxonomia passa a distinguir `ws_closed_symbol_format_invalid` de `ws_scope_member_invalid`, ambas sem nomes, horários de frames, OHLC ou mensagens brutas.

## Regressão e responsabilidade

`tests/test_j1_n50_ws_single_letter_usdt_d332.py` fornece **membro sintético** `AUSDT` em uma coorte 50 e exige que todos os 50 CLOSED sejam gravados e auditados, sem REST/ordens/rede, mantendo negativas de membro externo, clock, OHLC, confirm=false, base excessiva e quote errada. **Não afirmar** que `AUSDT` está listado na Bybit ou presente na coorte real: ele é um teste de formato. As evidências públicas de mercado não identificam os frames privados do usuário.

`deploy/vps/recover_j1_n50_ws_d332_once.sh` adapta recovery D331 com `OLD_SHA=c1fbd4cd46bba108be14859b9a04bb4184c3e91f`, checkout clean no mesmo caminho owner, preflight NTP/systemd/epoch, **6 suítes offline** no Python da VPS antes de desligar N2, rollback N2 em falha e zero novo bootstrap/rank/372 GET/SQL/ordens. Teste estático `test_j1_n50_ws_recovery_release_d332.py`. CI Linux/docs + Windows/offline + PAPER no head final; merge revisado sem deploy. **Gate root separado**, não assumir que timer ativo prova candle.

No próximo lease após gate root: se 50/50, manter coletor para J1/D323 24 horas e rotação >=36h; se falhar, usar classe sanitizada específica, preservar N2, não improvisar. #319 identidade/Top50 global é gate separado. R$0.
