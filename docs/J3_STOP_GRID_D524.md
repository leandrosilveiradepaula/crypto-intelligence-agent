# D524 — cinco stops, uma única bateria

A pesquisa swing D523 compara 18 estratégias e os stops iniciais de 50, 75, 100, 125 e 150 bps (90 cenários). D524 executa o produto cartesiano sem recalcular os indicadores para cada stop: ler uma vez as evidências owner, calcular cada sinal causal e o caminho 5m uma vez, aplicar cada política de saída ao mesmo caminho. Mantém custos, alvos, tranches, margem, alavancagem e filtros do perfil lido, sem gravá-lo. A primeira distância é a referência das métricas detalhadas antigas; todas as distâncias têm suas próprias somas adversa/favorável, stops, recuperações, cobertura e demais métricas D523. Comparar cada nome, não a ordem do ranking. Nenhuma seleção automática de vencedor.

Grid editável 2..8 inteiros crescentes 1..1000 bps, mutuamente exclusivo com stop avulso. A UI e API privadas D522 permitem executar o grid em uma tarefa; o limite de cinco minutos e tamanho de relatório permanecem. O mesmo relatório guarda todos os stops, contagem de cenários e manifesto. Uma mudança no perfil durante a pesquisa invalida a resposta, conforme D522.

Execução real isolada com o cutoff D521, após aprovação do SHA:
```bash
python -m scripts.run_j3_combination_research_d520 \
  --historical-directory "$HISTORY" --policy-file "$POLICY" \
  --matrix-file docs/examples/d523_swing_rsi_research_matrix.json \
  --as-of-ms 1795547640289 --horizon-hours 4 \
  --research-stop-grid-bps 50 75 100 125 150
```
Sem novas consultas Bybit. O POST local aceita `{"preset":"swing","horizon_hours":4,"stop_grid_bps":[50,75,100,125,150],"as_of_ms":1795547640289}` depois de publicar D524 sob gate próprio. GET consulta estado e relatório; não inicia operação. O relatório é exploratório, pré-funding, não considera liquidação real, carteira ou OOS. 50x não torna executável um stop de 1,5% ou 10%. O horizonte atual segue limitado a 12h; não confundir esta bateria com swing de dias. Próxima frente: dados PIT mais extensos, janelas independentes de 24/48/72h e funding/mark/liquidação. Não modificar J1.
