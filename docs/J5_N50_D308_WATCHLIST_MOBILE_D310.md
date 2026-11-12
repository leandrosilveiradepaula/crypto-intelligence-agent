# J5/D310 — observações D308 no relatório privado móvel, sem execução

## Objetivo e fonte

Integrar a heurística **descritiva** já integrada em J2/D308 à interface estática J5/D301 em português, adequada ao celular, sem criar outra estratégia, ranking próprio, coleta nem transação. O renderer recebe o mesmo relatório privado D300 já auditado e usa **exclusivamente** `build_descriptive_watchlist(report, include_private_symbols=True)` de D308. Os símbolos só chegam ao HTML depois das três flags pré-existentes de leitura, gravação e identificação privada no CLI owner J5. Nenhum novo servidor ou endpoint é habilitado.

## Conteúdo

A nova seção “Rompimentos e força relativa — somente observação” mostra contagem completa de candidatos de alta e de baixa (critério D308: rompimento dos 23 fechamentos anteriores, força relativa ao BTC, turnover final pelo menos igual à média das 23 barras anteriores). Exibe até cinco nomes por sentido, força relativa histórica e intensidade do turnover. A apresentação usa `html.escape` e Decimal limitado, apenas markup local. A ordem é a própria ordem calculada por D308; **não** faz reclassificação pela tela.

Caso falte referência BTC ao relatório D300, a seção fica “Indisponível” e não inventa comparações, símbolos nem candidatos. Se D308 negar a origem, discordar do digest/UTC/quantidade ou flag de integridade, o renderer inteiro abstém antes de salvar. Texto visível afirma ausência de validade OOS, expectativa de retorno, autorização de sinais/ordens e cobertura crypto-only/Top50 global. Os antigos 50 registros detalhados e quatro cartões de maiores variações permanecem no HTML.

## Segurança e testes

- HTML ainda sem JavaScript, rede, links externos, formulários ou botões, com CSP `default-src 'none'`; caminho permanece privado 0700/0600, escrita uma vez sem sobrescrever, sob `cia-probe` owner.
- Teste D310 cobre renderização J2/D308, ausência de BTC, não promoção de flags, inconsistência de cálculo BTC, barreira de volume e HTML inerte/teclado/mobile. Regressão: suíte J5 D301 e J2 D308 inalteradas, Linux/docs, Windows/offline e Chrome/PAPER no SHA final.
- **Não executar publicação de HTML na VPS nesta PR**. GitHub merge sem deploy, sem ordens, sem alavancagem 50x, sem custo adicional e sem afirmar J1 concluída.
- #319 (identidade crypto-only) e #429 (24h real + renovação causal) permanecem abertas, e a J5 é somente visualização offline até homologação.

**Decisão D310:** exibir observações quantitativas causalmente justificadas pelo motor D308 no HTML móvel existente, evitando duplicar filtros e preservando os gates de integridade e privacidade.
