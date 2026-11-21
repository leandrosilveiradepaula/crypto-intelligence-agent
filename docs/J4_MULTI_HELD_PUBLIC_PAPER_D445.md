# D445 — acompanhamento multicontrato de posições PAPER

## Resultado de produto no código

O processo D444 já podia repetir sessões, mas mantinha apenas BTCUSDT. D445 usa os contratos de **todas as posições PAPER já registradas no journal AUTO4**, sem exigir que ainda façam parte do N50. Quando o worker inicia novo ciclo, D425 relê o manifesto/diário de posições sob lock, e D445 constrói o universo exclusivo de ativos mantidos (1–50 símbolos USDT únicos). Não cria posições, nem altera seleção J2. Permite até 50 contratos mantidos; não significa que o agente já gere 50 entradas.

Para poupar quota, a consulta REST pública usa paginação completa de instrumentos lineares da Bybit (`limit=1000`, até 20 páginas, 10.000 linhas). Contratos detidos ausentes, inativos, TradFi, USDC, pré-listagem ou metadados incoerentes fazem a sessão falhar, sem substituir por fixture ou estado J1. O escopo transitório identifica somente o *instrumento de uma posição PAPER já aberta*, sem certificar identidade independente crypto-only, ranking N50 ou sinal financeiro.

Com todos os instrumentos de posição revistos na captura, o mesmo WebSocket D390 subscreve os tópicos de cada ativo. A observação pós-ACK e após snapshot chega ao D391/D389/AUTO4 por símbolo, com stop-first, alvo parcial, trailing e idempotência do SQLite original. Falta de cotação de um ativo degrada a classificação da sessão; **não apaga uma reserva já escrita nem impede um stop de outro ativo cuja própria quote esteja fresca**.

## Segurança

- Owner POSIX 0700/0600, lock do diário durante o ciclo, CLI D444 com sete opt-ins, status privado D444 para painel e backoff entre tentativas; nenhum acesso, recuperação ou auditoria da J1
- Apenas posições já existentes, sem novos fills inferidos, sem conta, sem APIs privadas, sem ordens reais, sem stop nativo, sem autorização de trading
- Dados de mercado públicos e não autenticados independentemente; direitos e elegibilidade regional continuam gates do operador, não são afirmados pelo código
- O estado do painel representa o processo e último lease, não garante conectividade contínua, execução financeira, custos reais, liquidação ou stop de corretora

## Evidência esperada

Replays de duas posições (BTCUSDT e ETHUSDT) no mesmo ledger AUTO4: target BTC reserva 30%, stop ETH reserva 100%, ambos com preenchimento confirmado zero; reinício reenvia o preço e não duplica as reservas. Scanner pagina, rejeita cursor incompleto/cíclico, contrato ausente ou fora das regras; não faz GET por ativo. Sem opt-in não lê journal ou rede. Validar suite completa no SHA final antes da incorporação.

## O que continua faltando ao agente completo

Uma fonte dinâmica N50 **para novas entradas** e sinais J2 validados; J3 com marcas intrabar, funding, slippage e liquidação em amostra e OOS; J6 com execução PAPER contínua comprovada na VPS, alertas e recuperação. D445 entrega gestão multicontrato em código, não implica produção instalada ou vantagem estatística.
