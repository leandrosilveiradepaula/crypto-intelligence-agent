# J5/D301 — visão privada de pesquisa N50 em português, adequada ao celular

## Finalidade e fronteiras

A entrega J2/D300 integrou **apenas pesquisa descritiva**, estritamente após replay completo de SQLite N50 D290/D292. D301 transforma esse relatório em uma **página HTML local, imutável e sem scripts**, com resumos e cards dos movimentos passados e tabela dos 50 contratos. Não é uma tela de ordens, não chama exchange, não acessa contas, não instala servidor HTTP e não mistura posições PAPER sintéticas com preços privados reais.

A visualização só aceita o contrato fechado `j2-private-n50-24closed-research-v1` com exatamente 50 registros, ranks consecutivos, símbolos únicos USDT, último fechamento dentro de 2h da observação, fonte e identidade explicitamente NÃO certificadas, integridade owner real positiva e status observacional. Valores monetários e percentuais chegam como strings Decimals finitos e limitados; `NaN`, infinito, indicadores extras, flags de `live` ou HTML injetado bloqueiam a página. A renderização usa exclusivamente `html.escape`, sem `eval`, SQL, scripts ou requisições.

## Conteúdo e apresentação

- Título e aviso principal **PESQUISA PROVISÓRIA — NENHUMA ORDEM**; sem botões de compra/venda nem promessa de lucros.
- Última hora UTC publicada e data/hora da consulta, contexto BTC e contagens dos 50 ativos: rompimento observado da máxima/mínima anterior ou dentro da faixa.
- Quatro cartões com as maiores variações **já ocorridas**, não oportunidades sugeridas.
- Tabela navegável por teclado e rolagem horizontal no celular: símbolo, variação 24 barras, diferença relativa ao BTC (p.p.), mean true range de 14 barras, turnover de 24 barras em USDT e observação da última barra.
- `html lang=pt-BR`, viewport mobile, textos de acessibilidade, skip-link, `prefers-reduced-motion`, grid responsivo, alto contraste e `Content-Security-Policy` bloqueando rede, scripts, forms, frames e objetos.

## Execução, proteção e retenção

O renderer puro `j5_n50_private_html.render_n50_private_html` não grava arquivo nem consulta o banco. CLI opt-in:
```bash
python -m scripts.render_j5_n50_private_mobile_once \
  --allow-private-readonly-audit \
  --allow-private-report-write \
  --include-private-symbols
```
É obrigatório executar como proprietário não-root `cia-probe`, na VPS privada. As três flags são explícitas, porque o relatório contém nomes de contratos e métricas derivadas de dados privados. O comando valida novamente toda J1/J2 e só depois grava **um arquivo owner-only 0600** em pasta `/home/cia-probe/agent/j1-n50-managed-d296-private/reports/` 0700. O nome é derivado de `last_published_end_ms` e prefixo do SHA256 de janela; reexecução idêntica não sobrescreve nem reescreve. Se existir conteúdo diferente, recusa. A saída padrão do comando revela somente status, nome do arquivo e digest; não imprime símbolos ou OHLCV.

**Não publicar esse HTML num site público, proxy, repositório, canal ou dashboard sem autenticação.** O arquivo não atualiza automaticamente, não representa prova de 24h contínuas e não tem acesso remoto integrado. Disponibilização autenticada futura é tarefa independente sujeita a segurança e gate operacional J5/J6.

## Evidência e critérios

`tests/test_j5_n50_private_mobile.py` valida contrato exato, 50 registros, texto PT-BR, CSP, ausência de script/forms/links externos, teclado, mobile, simbolização da qualidade, BTC ausente, injeção de código, valores inválidos, 0600/0700, reexecução sem overwrite e flags CLI antes de acesso privado. VPS de desenvolvimento validou **10 testes** D301 no candidato `bb3ded25925ea75ef153fafe05be781be9b9fa10`. Não representa execução pública, real money, produto homologado ou conexão de contas. CI no SHA final e revisão/merge sem deploy são gates separados.
