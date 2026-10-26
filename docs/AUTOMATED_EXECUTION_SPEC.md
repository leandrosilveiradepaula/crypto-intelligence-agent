# Contrato de execução automática — entradas, saídas e segurança

**Decisão de produto:** D77 / issue #147, 26/10/2026 UTC. **ALVO: operação automática** de entradas, stops, alvos parciais, trailing, manutenção de parcela residual e encerramento de posições em futuros perpétuos cripto na Binance USD-M ou Bybit V5 linear (venue final ainda não escolhida). Esta decisão **substitui** a interpretação anterior de execução exclusivamente MANUAL da J0/WU47. Registros históricos anteriores permanecem históricos, não orientações atuais.

**Estado em 26/10/2026:** somente preparação offline e pesquisa. **NENHUMA execução de ordens reais foi autorizada, nem existe motor de ordens homologado.** O Product Owner definiu a funcionalidade-alvo, mas não deu autorização para ativar trading real, implantar produção, criar ou utilizar chaves, nem assumir gastos. Custo adicional R$0,00.

## Fluxo-alvo

1. Fonte financeira com contratos/volumes/unidades/licenças verificadas, relógio UTC e qualidade; universo dinâmico Top50 elegível *point-in-time*. A corretora escolhida deve estar disponível na região e para o instrumento efetivo.
2. Motor de estratégia causal produz `Signal` com fonte, versão, instante, símbolo, lado, score e validade. Modelo estatístico/quantitativo decide; LLM não envia ordens.
3. `RiskGate` **fail-closed**, usando metadados **atuais da corretora de execução**: símbolo/contrato, quote/settle, limites de alavancagem e margem, tick/lot/min-notional, preço mark, spread, liquidez, funding, distância para liquidação, correlação, exposição por posição/carteira, saldo, limites de perda e idade de dados. 50x é configuração inicial de pesquisa e pode ser rejeitada por contrato/risco; alteração afeta somente posições futuras. Margem US$1–5 é exemplo, não executável sem mínimo da venue.
4. Gerador de intenção de ordem tipada e persistente, desacoplado de adaptadores específicos Binance/Bybit. O sinal não é ordem; sinal `approved` não equivale a ordem aceita ou executada.
5. Executor específico da **venue selecionada** envia intenções admitidas somente no modo autorizado. Entradas automáticas condicionais a limites; ordens de proteção/saída prioritárias. Gerenciamento de alvos em frações da quantidade inicial OU saldo remanescente, trailing, runner e encerramento conforme estratégia.
6. `Order/FillLedger` alimentado por confirmações da exchange, não por suposições: quantidades parciais, preço realizado, taxas, funding, status, saldo e reconciliação após desconexão/restart. UI PT-BR exibe ordens, posição, riscos, motivos, saúde do robô e controles.

## Modos de operação e autorização (não intercambiáveis)

| Modo | Comportamento | Gate |
| --- | --- | --- |
| `offline_paper` **default** | Modela ordens e fills **simulados**; não acessa endpoint de ordem, não requer segredo. Exibe claramente `SIMULADO`. | Desenvolvimento/replay com fixtures e dados autorizados |
| `testnet` | Integração separada com ambiente de teste, sem capital real, sujeita a conta/credenciais de teste e acesso permitidos. Não habilitada automaticamente por possuir conta em produção. | Autorização específica do titular, conformance e segurança; não confundir teste com mercado real |
| `live` | Ordens e gestão reais após todos os gates financeiros/operacionais/legais, instrumentais e de segurança, com release controlado. | **Bloqueado até autorização explícita separada do PO**, evidências de homologação e acesso estritamente necessário. Nenhum código ou fixture pode ativar por default |

`live_trading_enabled=false` e `order_submission_enabled=false` até gate técnico **e** humano comprovados. Variável de ambiente, JSON de fixtures, parâmetro CLI ou flag de CI, isoladamente, NÃO constituem autorização de produção. Deploy, testnet e live requerem revisões distintas; nenhum segredo no GitHub público nem em logs.

## Estado de ordens, deduplicação e reconciliação

- Estados mínimos (eventos versionados): `SIGNAL_CREATED -> RISK_REVIEWED -> INTENT_PERSISTED -> SUBMISSION_PENDING -> ACKNOWLEDGED / REJECTED / UNKNOWN -> PARTIALLY_FILLED / FILLED / CANCELLED / EXPIRED`. Descrever `UNKNOWN` explicitamente: timeout não prova rejeição; **não repetir automaticamente** uma abertura sem consultar ID e eventos da exchange.
- Persistir intenção e chave idempotente exclusiva por venue/conta/estratégia/sinal/tentativa antes de qualquer envio; usar identificador da ordem cliente estável. Reconcile REST+WebSocket/eventos com eventos duplicados, tardios, parciais e fora de ordem; sequência e cursor persistidos. Não alegar entrega exactly-once pela rede: obter **efeito idempotente** com validação e reconciliação.
- Cada preenchimento real confirma a posição; **ACK ≠ FILL**. Impedir duas ordens de abertura pelo mesmo sinal em restart, corrida ou resposta incerta. Ao recuperar, consultar ordens/posições reais antes de permitir novas entradas.
- Saídas parciais e stops devem usar **reduce-only ou semântica equivalente validada por venue e modo de posição**; não permitir que uma tentativa de fechar abra posição inversa. Recalcular restante/quantidade de proteção a partir de fills reais; reservar quotas de ordens condicionais. Preferir mecanismos nativos de stop quando homologados; se a proteção ficar ausente ou ambígua, travar novas entradas e alertar.
- Referências oficiais para integração posterior: [Bybit V5 Place Order](https://bybit-exchange.github.io/docs/v5/order/create-order) (`orderLinkId`, `reduceOnly`, `positionIdx`, TP/SL e ACK assíncrono) e [Binance USD-M New Order](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Order) (`newClientOrderId`, `reduceOnly`, `positionSide`). As regras **não são permutáveis** entre exchanges; validar endpoints atuais quando implementar. Esta especificação não envia qualquer POST.

## Controles de risco e emergência

- Limites **configuráveis e explícitos** por exposição, risco por posição, concentração, perdas acumuladas (dia/sessão), drawdown, ordens simultâneas, tentativas/erros e slippage adverso. Validar saldo, tiers e risco de liquidação da venue. **Não criar limites numéricos supostamente seguros por hardcode.**
- Feed obsoleto, relógio divergente, indisponibilidade da exchange, risco de liquidação, ordens pendentes sem reconciliação, alteração inesperada de regras, excesso de perdas ou inconsistência do ledger => **fail closed para novas entradas**. Sempre manter plano de proteção das posições existentes e política explícita para cancelamento/saída de emergência; um kill-switch NÃO deve cancelar cegamente stops de posições abertas.
- Kill-switch remoto/local autenticado e auditável, pausando imediatamente novas entradas. Reativação exige avaliação da saúde, reconciliação e gate de operador quando aplicável. Ações de fechamento reais somente dentro de uma política previamente aprovada e validada, não presumidas ao desligar.
- Segredos com escopo mínimo e preferência por permissões sem saques, rotação, proteção de armazenamento privado, allowlist IP quando suportada e não lesiva, revogação e observabilidade sem vazar dados. Não solicitar segredo no chat.

## Critérios de evolução / bloqueios

1. **J1:** dados e licenças, elegibilidade da venue, funding/mark/liquidez/histórico, no-loopholes HTTP451/geo, identidade crypto-only #32 e unidade Kraken #36 permanecem separados dos dados Binance/Bybit; rights #48 conforme origem e destino.
2. **J2/J3:** sinais causais, backtest com execução intrabar e liquidação, taxas/slippage/funding reais por cenário, walk-forward e fora da amostra. Resultados líquidos e ajustados ao risco; CI verde não demonstra lucro.
3. **J4:** evoluir planos sintéticos já existentes para ledger de intenções/fills e **simulador determinístico** com reversão idempotente e reconciliação de falhas, sem acesso a contas.
4. **J5:** dashboard responsivo PT-BR com estado do bot, estratégia, ordens e posições, modo `SIMULADO/TESTNET/LIVE` inequivocamente identificado, autorização e kill-switch.
5. **J6:** paper trading prospectivo/replay de incidentes e observabilidade contínua. Testnet somente após gate específico. Release `live` somente após revisão de segurança, riscos, licença, testes, acesso regional e aprovação humana documentada.
6. **J7:** ML/LLM só quando agregar valor validado; não controla diretamente envio de ordens.

Nenhum trabalho anterior de execução MANUAL é apagado: as PRs J4 são **protótipos sintéticos que podem ser reutilizados** para o novo destino. O contrato atual prevalece sobre rótulos históricos de `manual`, não sobre regras de segurança e comprovação financeira.


## J4/AUTO2 — diário SQLite PAPER (issue #151)
A infraestrutura de desenvolvimento adiciona `SQLitePaperOrderJournal` em `crypto_intelligence_agent/paper_order_store.py`, **somente `offline_paper`**. Ela reserva uma intenção fictícia (`intent_id`) antes de qualquer evento, grava eventos hipotéticos e seu checkpoint em **uma transação `BEGIN IMMEDIATE`**, e reconstrói snapshots verificando SHA-256 do payload, sequência e replay via `synthetic_order_lifecycle.py`. Banco dedicado, schema versionado, sem compatibilidade automática com SQLite de mercado J1 nem migrações de produção.

Uma intenção OPEN para o mesmo `fixture_signal_id` é única no arquivo, inclusive após restart e mesmo com `UNKNOWN`; IDs de eventos repetidos com payload exatamente igual não contabilizam fills duas vezes. Identificador repetido com payload distinto, evento retrodatado, overfill ou um segundo evento inválido **não confirmam qualquer escrita do batch**. Um ACK não demonstra fill; `UNKNOWN` não aciona reenvio. Como o catálogo não possui contas/estratégias reais, o filtro de unicidade de sinal é propositalmente **mais restritivo**, inclusive entre venues candidatas.

**Limites críticos:** hashes detectam corrupção acidental, não autenticação contra adulteração intencional do arquivo; deduplicação é **local PAPER**, não exactly-once contra exchanges. `REDUCE_ONLY` valida somente a quantidade declarada no fixture de **cada intenção**, sem reservas consolidadas entre várias ordens de saída sobre a mesma posição; não existe ledger de posição/funding/fees, validação de lot/tick ou proteção instalada na corretora. Ainda faltam reconciliação de posições e ordens entre processos/venues, semântica de stops nativos, backtest/intrabar realista e kill-switch operacional. `orders_sent=false`, `approved_for_live_use=false`, `persistent_idempotency_verified=false` (para execução real) permanecem invariantes. Não ativar testnet/live, criar chave ou apontar este SQLite para dados financeiros de produção.


## J4/AUTO3 — bloqueio preventivo de OPEN apenas em PAPER (#153)
O módulo `paper_risk_gate.py` avalia `PaperOrderIntent` já validada contra `PaperRiskLimits` e `PaperRiskObservation` fictícias, **sem enviar ordens**. Limites `Decimal` explícitos por notional de intenção, concentração por símbolo, exposição de carteira, perda diária e máximo de OPEN pendentes; `max_market_age_ms` em UTC. As entradas são negadas em `kill_switch_active`, `unresolved_open_exists`, excessos de risco ou dados obsoletos; dado futuro, simbologia/cotação divergente, floats, NaN e limites incoerentes são inválidos. Condições em modo `REDUCE_ONLY` podem permanecer elegíveis para **planejamento paper** mesmo quando novas entradas estão pausadas: isso não instala stop real, não confere saldo/posição verdadeira nem autoriza operação ou execução emergencial.

Todos os valores (`mark_price_quote`, `symbol_exposure_quote`, `portfolio_exposure_quote`, `realized_loss_today_quote`, flags de kill switch e ordens incertas) são **alegações do fixture, não dados autenticados**. A função não pode concluir que Binance/Bybit aceitam 50x, qual é o risco de liquidação, que a perda real está correta ou que a lista de ordens pendentes está completa. `allowed_for_paper_only=true` jamais significa `approved_for_live_use` nem `order_submission_enabled`. O gate Kraken `venue_leverage_gate.py` é específico de PF_/USD e NÃO é aplicado automaticamente a Binance/Bybit. O futuro RiskGate real requer feeds, reconciliador, ledger de posição, política de falhas e revisão específica das venues.
