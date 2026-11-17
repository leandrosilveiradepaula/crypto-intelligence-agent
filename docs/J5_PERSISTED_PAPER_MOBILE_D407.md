# J4/J5 D407 — Posições persistidas PAPER aparecem no aplicativo móvel

## Entrega funcional

O console em português `web/app` passou a aceitar diretamente o JSON **já produzido pelo leitor de posições persistidas AUTO4**: `python -m scripts.inspect_paper_positions --format json`. Não foi criado outro ledger ou outro leitor SQLite.

Uma seção independente chamada **Posições registradas no diário PAPER** mostra, por posição selecionada: ativo fictício, LONG/SHORT, quantidade inicial confirmada por FILL fictício, quantidade de saídas preenchidas, quantidade restante, reservas não preenchidas, saldo disponível, status de runner, número de ordens pendentes/`UNKNOWN`, data UTC e margem/alavancagem solicitadas quando o comprovante existe. Não soma unidades diferentes entre instrumentos, não mostra PnL ou preço de marcação e não declara stop nativo ativo. A presença de reserva incerta vira indicação explícita de **Reconciliação pendente** e de bloqueio a novas reduções até reconciliação.

Essa seção **não é o laboratório de posições criadas no navegador**; o estado do laboratório permanece intacto. Uma amostra importada aparece só na sessão atual e some após reload, não é enviada para servidor nem gravada no `localStorage`. Somente a leitura do próprio JSON é feita no browser; a página não abre SQLite.

## Fluxo de uso

Com um diário AUTO4 de simulação já criado e permissão local para leitura, selecionar explicitamente posições e gerar um arquivo NOVO:

```bash
python -m scripts.inspect_paper_positions \
  --journal /caminho/para/paper-positions.sqlite \
  --position-id fixture_position_A \
  --position-id fixture_position_B \
  --format json --output /tmp/paper-positions-readonly.json
```

Os caminhos e IDs acima são **ilustrativos**: o operador deve usar sua própria origem autorizada. A ferramenta existente recusa listar automaticamente todas as posições, aceita somente IDs explícitos (até 128), lê um snapshot SQLite em modo read-only, confere schema/checkpoints/digest e não substitui arquivos. O arquivo pode ser importado no seletor JSON da interface.

Se for incluído `--opening-order-journal`, o exportador atual também confere as aberturas contra o diário AUTO2. Sem esse argumento, a UI informa que a abertura não foi cruzada; nenhum check é inventado.

## Proteções

- O importador D407 valida **chaves e tipos exatos**, `mode=offline_paper`, proveniência de journal sintético e flags de não negociação; recusa qualquer sinal de conta, PnL ou stop nativo verificado.
- Quantidades são comparadas com `BigInt` decimal exato, sem conversão `Number` de valores de posição: `saídas preenchidas + saldo confirmado = inicial` e `reservado + disponível = saldo confirmado`.
- Os valores da posição e seu ID são apresentados somente por `textContent`, jamais HTML, para impedir injeção.
- Exige IDs `fixture_`, contratos da família USDT, checkpoint UTC, estados RUNNER e opcionais de margem/recovery estritamente tipados. Falha parcial em qualquer posição rejeita todo o novo arquivo e conserva a última amostra válida da sessão.
- A UI não cria posições, fills, ordens ou reservas e não presume lucro financeiro. Uma nota explícita diferencia *solicitado PAPER* de executado na Bybit.
- O serviço local `serve_j5_local_readonly.py` só passa a servir o ativo estático `/persisted-paper.js`, **não** recebe um endpoint de leitura de SQLite nem amplia acesso de conta/arquivos privados.

## Verificação

```bash
python -m unittest discover -s tests -p 'test_j5_persisted_paper_mobile_d407.py' -v
python -m unittest discover -s tests -p 'test_multi_paper_positions.py' -v
python -m scripts.audit_j5_product_app_browser
```

Os testes conectam a saída **real** do exportador AUTO4 à validação Node, impedem alteração de flags de ordem/lucro/stop, verificam conservação da posição e comprovam a importação no navegador real, o veto de JSON forjado e o descarte da amostra após reload.

## Próxima etapa

A atualização automática da seção dependerá de uma fonte de estado PAPER persistido acessível por um serviço privado com controle de permissões, explicitamente autorizada e homologada. **Não** expor o banco AUTO4 por HTTP nem conectar o REST pontual D404 a posições para executar stops. Antes de monitorar intrabar em produção PAPER, medir WebSocket público real D405/D406, cobertura de 50 + posições e estado stale/reconciliação, com gate de implantação VPS independente.

Custo adicional: zero. Nenhuma ordem, chave, deployment ou alteração J1 foi feita.
