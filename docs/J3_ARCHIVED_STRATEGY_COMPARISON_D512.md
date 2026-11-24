# D512 — Laboratório de comparação histórica de estratégias J3/J5

## Entrega
Compara rompimento e cruzamento EMA com períodos escolhidos no formulário J5 e os demais parâmetros/custos do perfil PAPER salvo. Não precisa trocar ou salvar a estratégia operacional para comparar as EMAs. Reusa D435/D461, sem outro coletor, motor de indicadores, journal ou exchange. O GET privado /api/strategy-comparison aceita somente três períodos inteiros crescentes (2..120). A interface mostra cobertura da amostra, hipóteses, observações posteriores disponíveis, marcas positivas/negativas antes de funding, média em bps, benchmark LONG e toques nos níveis de stop/alvos.

## Causalidade e limites
- Até 72 snapshots REST owner-only já congelados e no máximo 24 pares horários consecutivos; as horas com múltiplos fingerprints de coorte são omitidas. A escolha da coorte usa o arquivo da hora de decisão, nunca o ranking atual reconstruído retroativamente.
- Ambos os métodos recebem o mesmo prefixo causal de candles fechados. Para médias maiores, completa o aquecimento somente com arquivos anteriores que tenham barras contíguas e sem conflitos; se não houver, exclui a mesma observação de ambos. A coorte pode variar; se o ativo desaparecer ou o arquivo posterior divergir na barra de referência, o resultado futuro fica desconhecido e é contado separadamente.
- A entrada de referência é o close da hora t e a saída de referência o close de t+1h. São marcas ex post, não preços de execução: o arquivo de decisão pode ter sido capturado depois da abertura da hora seguinte. O benchmark LONG recebe as mesmas hipóteses econômicas. O notional fixo de referência é margem configurada x alavancagem, não exposição de uma carteira. Usa o cálculo PRE2 para fees/slippage com o mesmo notional nos dois lados; funding real não está disponível.
- As faixas high/low da hora seguinte permitem contar toques de stop e de cada alvo, inclusive ambiguidade stop+alvo. Não informam ordem de eventos, execução, parciais, liquidação ou mark price. As somas de marcas não são PnL de uma carteira, e não escolhem automaticamente uma configuração vencedora.
- O perfil pode ser escolhido depois da observação histórica; portanto, não afirmar OOS, retorno comprovado, cobertura PIT integral ou rentabilidade. O próximo aceite financeiro requer dados intrabar/mark/funding, protocolo pré-registrado e holdout cronológico.
- Nenhuma ordem, credencial, acesso externo, alteração de estratégia operacional ou VPS. A leitura é sob opt-in/UID já existente. Execução manual no painel, sem polling adicional ou custo.

## Validação
Testes D512 verificam prefixos causais, mesmas observações, ausência de preço posterior, conflito entre arquivos, custos e períodos longos. Fixtures são artificiais; não demonstram resultado real da Bybit. CI e revisão da HEAD precedem merge sem release; homologação com os arquivos reais owner exige acesso autorizado e publicação separada.
