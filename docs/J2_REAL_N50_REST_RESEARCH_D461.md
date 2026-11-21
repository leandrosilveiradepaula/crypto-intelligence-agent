# D461 — pesquisa quantitativa imediata com histórico REST real da Bybit

## Entrega funcional comprovada — 21/11/2026

A primeira execução integrada da J2 com **N50 dinâmica + histórico REST fechado + motor D435** foi executada na VPS como `cia-probe` (UID999), usando o SHA de implementação `87479504883f50e25ad7bcaf7db2b72c02a1c66d` e a política PAPER de pesquisa já existente, sem instalar serviço permanente.

Resultado observado da execução `227e8d049ef44006991e6d93c1bde0e3`:
- N50 real por turnover24h: **50 símbolos** selecionados.
- Histórico REST validado: **24 velas de uma hora para cada símbolo, total 1.200**.
- Pesquisa existente D435 executada sobre **50/50 símbolos**, produzindo **9 hipóteses históricas** (não sinais nem ordens).
- Duração do processamento real: **104,8 s**, sem serviços pagos, ordens reais ou qualquer mutação J1.
- Arquivo proprietário 0600 em diretório separado 0700 `/home/cia-probe/agent/d461-rest-n50-research`, **98.136 bytes**, SHA-256 de conteúdo `9ea87ed1101352e1ac9f221df0e833a136c04bff957fa8c2697edd7fdda5162d`. Verificação independente owner-only posterior confirmou checksum=true, 50 símbolos e 1.200 linhas.
- Janela fechada avaliada até o instante UTC `1795266000000` ms, identificador do fluxo `public_rest_observed_unverified`.
- Antes da captura completa, prova pública real separada de BTCUSDT e ETHUSDT havia validado 24/24 candles de cada um no mesmo parser.

## Arquitetura e integridade

`crypto_intelligence_agent/j2_rest_n50_history_d461.py` captura com o cliente HTTP público limitado já existente (somente transporte, sem modificar J1), valida payload e janela de 24h completos, publica **uma única fotografia imutável 0600 com hash e write-at-once**, sem importar dados REST para o journal WebSocket-only D451. Ativos incompletos abortam o conjunto inteiro sem arquivo parcial. Releitura verifica schema, checksum, janela UTC, coorte, 24 linhas por símbolo e OHLC/volume usando o parser oficial. Os dados são explicitamente classificados como **histórico REST de origem pública não autenticada**, jamais `confirm:true` de WebSocket.

`scripts/run_j2_n50_rest_research_d461.py` expõe **um único comando owner-only** para executar seleção N50, 50 downloads e indicadores D435, com 4 opt-ins explícitos e saída sanitizada. O D435 aceita a qualidade REST **apenas quando o cálculo histórico explicitamente solicita**, preservando a validação WS-only do percurso D447/AUTO2 de novas aberturas PAPER.

Testes: `tests/test_j2_rest_n50_history_d461.py` — **5 PASS na VPS**, incluindo 1.200 candles em 50 instrumentos, reabertura/identidade, adulteração, rejeição all-or-none, bloqueio de rest como WS e opt-ins de rede. Publicações separadas ficam no mesmo branch de entrega existente, PR draft #734; não criar outro PR.

## Limite honesto e próximo trabalho

As **9 hipóteses são classificações históricas de pesquisa**, não previsões nem recomendações; retorno futuro não foi validado. Essa entrega elimina a espera de 24h para *pesquisar* o conjunto N50; não resolve isoladamente a ingestão do último close WebSocket de uma hora (D460) nem permite PAPER opens sem a prova causal de preço, risk gate e último candle público confirmado. Próxima etapa de produto é combinar os 23 candles de aquecimento REST com o último candle real **WS-confirmed** em um leitor de proveniência mista auditável, sem forjar receipt nem contaminar diários. Depois, operação PAPER contínua e J5 visível no celular após gate de release.

**Custo R$0; J1 intocada; zero ordens; sem release VPS.**
