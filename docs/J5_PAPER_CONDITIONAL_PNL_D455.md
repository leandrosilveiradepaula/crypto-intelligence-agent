# D455 — Resultado financeiro PAPER na tela de posições J5

A experiência do produto agora liga o cálculo financeiro condicional D454 ao painel móvel existente, **sem importar JSON** quando o operador local de leitura está habilitado.

## Comportamento

1. `/api/owner-paper-positions` permanece acessível **somente no loopback, mediante opt-in**, e lê o mesmo journal AUTO2/AUTO4. Ele solicita `read_owner_paper_positions(include_conditional_pnl=True)`, o qual cruza FILLs hipotéticos, preços BBO persistidos e plano econômico imutável D448.
2. `web/app/persisted-paper.js` aceita posições legadas e um atributo opcional `conditional_paper_pnl` por posição. Contratos novos são validados integralmente, com `funding_settlement_unknown=true`, `true_realized_net_pnl_available=false`, sem ordens ou execução real. O navegador exige quantidades coerentes, alavancagem correspondente à posição e, via BigInt Decimal, `resultado_condicional = bruto - taxas - slippage`. Campos inesperados, NaN, spoof de resultados reais e alterações dos custos rejeitam a projeção inteira.
3. Para uma saída PAPER preenchida, o painel exibe “Resultado PAPER parcial estimado” com USDT, resultado bruto e aviso explícito de que funding e liquidação não foram verificados. Para diários sem eventos precificados, o painel explica que o resultado está indisponível; nunca inventa zero.
4. O endpoint mantém o limite estrito de 96 KB do cliente, não expõe dados de corretora e não aceita POST. Falha de journal faz a tela revogar dados locais anteriores, como já fazia no D407.

## Evidência de aceite

- `tests/test_j4_paper_conditional_pnl_d454.py`: LONG/SHORT com abertura e parcial em BBOs causais, taxas/slippage Decimal, reboot, leitura J5 opt-in.
- `tests/test_j5_conditional_paper_pnl_d455.py`: importação DOM em Node, compatibilidade com relatórios legados, perda PAPER negativa, violação de aritmética/campos/flags de financiamento recusada, texto seguro via `textContent`.
- `tests/test_j5_local_readonly_server.py`: endpoint existente exige `include_conditional_pnl=True`, não cria API nova nem remove bloqueio host/origin.
- Antes de homologar exigir CI Linux, Windows e navegador no SHA exato. Não equivale a prova financeira de taxa de corretora ou funding; nenhuma ordem real, produção ou serviço VPS instalado.

## Próximo gargalo de produto

Persistir cenário de financiamento **sem chamar estimativa de resultado realizado real**, e habilitar reconciliação PAPER de perdas/custos com orçamento agregado antes de estudar múltiplas entradas simultâneas. Homologação de serviço local residente J6 e observabilidade visual do status são gates operacionais independentes.
