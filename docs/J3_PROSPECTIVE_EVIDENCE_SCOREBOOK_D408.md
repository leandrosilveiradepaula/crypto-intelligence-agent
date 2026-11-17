# J2/J3 D408 — Evidência acumulada de oportunidades prospectivas por horizonte

## Problema de produto resolvido

Já existem o registro horário de observações J2, antes do resultado, e a avaliação posterior J3 para horizontes de 1, 4 e 8 horas. Até aqui, cada execução produzia um relatório isolado. D408 permite **revisar várias decisões e horizontes juntos**, sem reprocessar mercado, gerar outro ranking, selecionar trades, alterar custos ou ler diretamente a base owner.

O módulo puro `j3_ws_prospective_evidence_summary_d408.py` recebe **1 a 256 relatórios J3 já gerados** pelo avaliador owner e aplica a validação rigorosa existente de `_projection` D667, inclusive schema exato, validações temporais, invariantes de maturação e flags de segurança. Cada par `(hora_de_decisao, horizonte)` pode entrar **apenas uma vez**; duplicação aborta, não duplica observações. Uma decisão com zero candidatos permanece **abstenção** e não é falsamente contada como perda.

O relatório informa separadamente, para 1h, 4h e 8h: quantas decisões com dados pontuados, quantas sem candidatos, quantidade de observações maduras, quantas ficaram favoráveis ou contrárias no fechamento, somas e média dos retornos **de referência** em bps após custos hipotéticos. Não produz lista de ativos ou ordem de compra.

## Limites estatísticos essenciais

Este é um **scorebook descritivo**, não avaliação financeira aprovada. Relatórios de J3 medem preço de fechamento futuro; não têm prova de caminho intrabar, trade/mark fill, funding completo, book de liquidez, liquidação, custo real, independência temporal de timestamps ou walk-forward. Mesmo uma média positiva **NÃO** comprova capacidade preditiva.

- O denominador contém **somente os relatórios fornecidos**. Horas sem arquivo, sinais filtrados por falha de fonte e backfills que não foram registrados são invisíveis. Portanto `all_decision_windows_present_verified=false`, sempre.
- Cada decisão J3 pode ter sido calculada com premissas de custo diferentes; os registros existentes **não vinculam criptograficamente a mesma política de fees/slippage/funding**. Portanto `cost_assumptions_consistent_across_decisions_verified=false`, sempre.
- Um registro local owner com digest não possui atestação independente de quando a decisão foi capturada. Portanto `prospective_registration_independently_verified=false` e `out_of_sample_results_validated=false`.
- Retorno líquido de referência `bps` **não é PnL**, acerto em ordens, retorno sobre margem nem estimativa de segurança em 50x. Não inferir ranking de estratégias nem alterar o motor de entradas com essas médias.

O código aborta para arquivos alterados ou incoerentes, status de pontuação ausente, dias duplicados por horizonte, valores não finitos, dados com alegação de ordens ou pesquisa autorizada e qualquer score que não corresponda ao contrato J3 owner validado.

## Como utilizar sem escrever um programa

Quando os relatórios JSON **já existirem** no ambiente de pesquisa, usar o CLI com nomes explícitos:

```bash
python -m scripts.summarize_ws_prospective_evidence_d408 \
  --score /diretorio/autorizado/score-decisao-1.json \
  --score /diretorio/autorizado/score-decisao-2.json \
  --output /novo/local/scorebook-j3.json
```

Os caminhos são exemplos; não presumir que existam na VPS. A CLI valida arquivos regulares absolutos, tamanho máximo 8 KiB por item, JSON sem chaves duplicadas, sem symlinks e sem leitura implícita de diretórios. O arquivo final é criado **novo** em modo 0600; segundo uso do mesmo destino falha em vez de sobrescrever. Sem `--output`, emite somente JSON no stdout. Em erro não imprime caminho/símbolo, dados privados, score ou stack trace.

## Testes

```bash
python -m unittest discover -s tests -p 'test_j3_ws_prospective_evidence_summary_d408.py' -v
```

O teste integra o **avaliador J3 existente** ao novo resumo, cobrindo horizontes distintos, duas decisões, abstenção sem candidatos, deduplicação por hora/horizonte, fraude por flags, inconsistência numérica, arquivos inválidos, saída JSON privada e recusa de sobrescrita.

## Próxima evidência necessária

Capturar decisões owner ex-ante em janelas reais (pendência de execução VPS), registrar também **todas as horas sem observação**, fixar política de custos e splits treino/validação/teste com instantes auditáveis, comparar regimes e calcular retorno líquido com simulação intrabar conservadora em J3. Após evidência prospectiva suficiente, usar o scorebook como insumo de avaliação — jamais como gatilho direto de abertura.

Nenhuma função de negociação real, rede, chave, VPS, J1, SQLite, serviço, instalação ou gasto está no escopo desta entrega.
