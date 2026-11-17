# D409 — fluxo completo PAPER do ticker até o aplicativo

## Resultado funcional

O demonstrador já existente D402 conecta cotações WebSocket **sintéticas e injetadas** ao adaptador público D390/D386/D385, roteador de posições D391, reservas automáticas J4/AUTO4, reconciliação e stop prioritário. O novo modo opcional `--mobile-snapshot` acrescenta uma leitura do **mesmo SQLite AUTO4** após o ciclo e entrega o schema `paper_positions_snapshot_v1` consumido pela seção de posições persistidas J5.

Não foi criado outro diário, carteira, modelagem paralela de saldos nem backend HTTP. O snapshot é obtido pelo leitor existente `inspect_paper_positions`, seguido da projeção `multi_paper_snapshot`; antes de exportar, D409 confere que filled/reserved/remaining e pendência de reconciliação correspondem ao saldo verificado do demonstrador.

### Como reproduzir sem rede

```sh
python -m scripts.run_paper_public_adapter_proof_d402 --scenario closed --mobile-snapshot
python -m scripts.run_paper_public_adapter_proof_d402 --scenario unknown --mobile-snapshot
```

A resposta do CLI com `--mobile-snapshot` é um JSON único com o relatório original em `steps` e a chave `mobile_snapshot`. Para gerar um arquivo **diretamente importável no aplicativo**, sem copiar ou extrair JSON manualmente, use:

```sh
python -m scripts.run_paper_public_adapter_proof_d402 --scenario closed --mobile-output /tmp/cia-paper-mobile.json
```

O comando cria um arquivo **novo**, privado (0600 no POSIX), e recusa sobrescrevê-lo ou seguir symlink. Neste modo, o stdout mantém apenas o relatório D402; o arquivo tem exatamente o schema `paper_positions_snapshot_v1` da interface J5, sem wrapper. O modo sem flags novas não muda o contrato legado e não expõe IDs nem símbolos no relatório original. Os caminhos acima são ilustrativos; nenhuma instalação na VPS foi realizada.

- **Ciclo encerrado:** três ticks injetados, duas reservas de saídas parciais, fills **explicitamente sintéticos** e reserva de stop, com preenchimento sintético confirmado ao final. O saldo do diário AUTO4 fica zerado.
- **Ciclo com UNKNOWN:** uma saída simulada em estado desconhecido, nenhuma nova redução concorrente; as posições ficam com reserva pendente e o aplicativo deve mostrar **Reconciliação pendente**. Nenhum fill é inventado.
- Ambos os cenários ocorrem em ambiente temporário (SQLite local transitório), sem rede, Binance/Bybit real, credenciais ou ordens. O laboratório do navegador e seus cenários continuam independentes do snapshot importado.

### Critérios de aceite

```sh
python -m unittest discover -s tests -p 'test_paper_public_adapter_proof_d402.py' -v
python -m unittest discover -s tests -p 'test_j5_persisted_paper_mobile_d407.py' -v
python -m scripts.audit_j5_product_app_browser
```

Os testes exercitam o código original do pipeline WS/PAPER e o validador real do aplicativo Node, os cenários closed/unknown, o bloqueio de reservas durante UNKNOWN e a compatibilidade do modo CLI legado. A prova não usa mocks para projetar saldos; usa o leitor do SQLite que foi escrito no próprio teste.

### Limite operacional

Esta é uma prova do fluxo **fim a fim de engenharia**, não evidência de funcionamento em mercado real, resultados, liquidação, vantagem estatística, fills da Bybit ou operação contínua. Mesmo com a conexão WebSocket HTTP 101 comprovada anteriormente na VPS, ainda falta executar o probe com subscrição/ticks reais no ambiente autorizado, alimentar o operador persistente, demonstrar abertura PAPER de uma hipótese J2 causalmente elegível e assegurar corte por stale/falha e custos. O gate da VPS e a política de ordens permanecem fechados.

Custo adicional: R$ 0,00.
