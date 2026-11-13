# J5/D330 — painel operacional N50 WebSocket, somente leitura

## Objetivo e fronteira

Apresentar no celular, em português, o estado auditado do coletor WS N50 com base **exclusivamente** no objeto sanitizado `j1-n50-ws-closed24h-owner-witness-v1` de J1/D323. Este módulo **não** coleta candles, não abre WebSocket, não consulta exchange, não calcula indicadores, não usa saldo/posição PAPER, não faz GET, não gerencia serviços e não cria sinal ou ordem. Não substitui o relatório J5/D301 da pesquisa N50 REST: fontes, arquivos e elegibilidade diferentes não são fundidos.

## Contrato de evidência

- Exige esquema e conjunto exatos de chaves D323. Status é uma enumeração fixa, sem incorporar texto arbitrário do fornecedor ao HTML.
- Tipos e limites são verificados estritamente: `int` sem `bool` para tempo/contadores, UTC fechado em grade, máximo uma hora de idade para `latest_eligible_closed_end_ms`, SHA256 para os digests reportados.
- `ws_24h_local_evidence_verified` só aparece com as flags D323, `verified_closed_hours=24`, `verified_contracts_per_hour=50`, pelo menos 1.200 registros do mesmo journal com integridade, último recibo, timers WS/rot ligados e N2/REST N50 desativados. Sem isso o painel permanece pendente/degradado.
- Estado `accumulating_or_incomplete_ws_24h` mostra número de linhas apenas se a integridade do journal foi auditada. **0/24 significa zero horas integralmente certificadas pela D323**, não que zero candles tenham sido observados. Não inferir progresso temporal do número de linhas.
- Timer habilitado não é coleta confirmada; `ws_service_not_failed` não prova continuidade 24/7. Se `n2_failback_observed`, destacar contingência, nunca sucesso N50.
- Flags `rotation_36h_live_verified`, `continuous_collector_verified`, `marketwide_top50_verified`, `crypto_identity_independently_verified`, `source_authenticated`, `approved_for_signals`, `live_trading_authorized`, `orders_sent`, `systemd_modified` continuam **false** nesse esquema. Valor diferente aborta renderização e exige revisão do contrato, não promoção automática de estado.

## Execução (após integração, sem implantação automática)

Somente como `cia-probe` não root, com diretório privado `/home/cia-probe/agent/j1-n50-ws-epochs` 0700, e **depois** do fechamento e da janela segura de auditoria D323:

```bash
python -m scripts.render_j5_n50_ws_operator_once \
  --allow-private-readonly-audit \
  --enable-ws-24h-witness \
  --allow-private-report-write
```

O CLI executa D323 owner-only uma vez e cria `operator-reports/n50-ws-ops-<timestamp_ms>.html` 0600, dentro do diretório root 0700, com `O_EXCL`, `O_NOFOLLOW`, `fsync` e proteção contra symlink/arquivo existente diferente. Nunca publica nem permite overwrite; não recebe caminho arbitrário por CLI. Saída de console possui apenas status, nome do arquivo e digest; nenhum símbolo, OHLC, preço ou segredo. Sem três flags explícitas, nenhuma leitura/escrita. Arquivo é estático: NÃO atualiza sozinho, NÃO é servidor HTTP e NÃO pode ser considerado acessível externamente a um celular.

## Experiência e testes

HTML sem JavaScript, sem links externos, sem formulário ou botão. CSP `default-src 'none'`, CSS inline, responsividade em 560px, salto de teclado, contraste e mensagens explícitas sobre o que está comprovado e o que falta. Quatro estados principais: agendamento, journal, N2 contingente, 24 horas verificadas localmente.

`tests/test_j5_n50_ws_operator_mobile_d330.py` cobre 24h sintéticas completas e 0/24, journal parcial, failback, relógio futuro, schema/tipos/flags alterados, SHA inválida, ausência de rede/ordens, sanitização, HTML móvel, owner opt-ins, DAC 0700/0600, symlink e idempotência. As fixtures **não** representam evidência real D329/J1.

## Critérios e limites

CI Linux/docs, Windows/offline e PAPER/mobile verde sobre SHA final, revisão das mudanças e merge sem deploy. A release VPS deste painel **não** está autorizada nem realizada. Próxima ação elegível independente: ler a primeira execução D329, depois auditorias D323 reais; somente essas leituras podem mudar o estado J1. J1 #2, cobertura #319, supervisor #429, WS-first #585 e J5 #6 continuam com gates próprios.

**Decisão D330:** exibir evidência operacional que já existe, sem duplicar coletor, inventar candles ou mascarar estados de contingência; relatório estático privado e observacional.
