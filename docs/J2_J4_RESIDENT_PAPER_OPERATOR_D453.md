# D453 — operador residente PAPER, continuidade de posições e fallback N50

## Produto entregue no código

O caminho principal `run_resident_paper_observer` reinicia sucessivos ciclos D451/D450 na mesma conta local PAPER, sem recriar livros financeiros. A fonte REST seleciona a coorte dinâmica N50 provisória, J2 acumula candles confirmados em SQLite por epoch, D449 pesquisa e reserva novas entradas somente em modo PAPER, D448 registra fills hipotéticos e AUTO4 persiste posições, alavancagem individual, parciais e residual. As posições existentes recebem cotações com prioridade na D391.

Se REST/ranking de novos ativos não estiver disponível, se a sessão principal ficar degradada ou lançar exceção, o operador usa `run_held_paper_without_n50`: lê **apenas as posições já registradas** na D425/AUTO4 e abre uma sessão ticker pública independente para seus símbolos. Não abre posições nessa contingência. A cada cotação, toma o lock D425, reserva stops/parciais e, quando habilitado, D394 pode registrar no AUTO4 **FILL sintético** numa cotação posterior com latência/BBO/liquidez explícitos. O disparo de uma parcial continua diferente da confirmação hipotética de seu preenchimento.

O processo mantém um lock exclusivo de longa duração separado do lock de escrita por cotação e escreve `paper-operator-state-d453.json` privado 0600 com último estado, TTL, sessões e se foi necessário fallback. Qualquer erro da contingência produz estado terminal `degraded_no_held_coverage`; o relatório nunca diz que existe proteção nativa da corretora nem monitor ativo após o encerramento.

## Execução disponível (não instalada)

Entrada Python: `python -m scripts.run_j2_j4_public_paper_resident_d453` com diretórios J2/PAPER existentes e isolados, arquivo JSON de política owner-only e **seis opt-ins** para pesquisa pública e PAPER. O exemplo de política está em `docs/examples/d453_public_paper_policy.example.json`. As taxas, margem, 50x, limites de exposição e tranches são parâmetros de pesquisa, não configuração de negociação real. Sem flags, o comando recusa antes de abrir rede ou modificar qualquer diário.

Exemplo ilustrativo **somente depois** de preparar usuário não-root, pasta J2/PAPER 0700, política 0600 e obter aceite operacional para a sessão pública (não executar como root nem como deploy automático):

```sh
python -m scripts.run_j2_j4_public_paper_resident_d453 \
  --j2-directory /CAMINHO/PRIVADO/j2 \
  --paper-directory /CAMINHO/PRIVADO/paper \
  --policy-file /CAMINHO/PRIVADO/policy.json \
  --lease-seconds 60 \
  --allow-public-network --allow-public-websocket \
  --confirm-personal-readonly-research \
  --confirm-region-eligible --confirm-public-data-rights \
  --enable-hypothetical-paper-cycle
```

O operador é um **processo residente**, mas ainda não foi instalado em systemd nem implantado na VPS. Cada lease dura no máximo seu orçamento; um serviço systemd não converte ticker PAPER em stop nativo. Com o processo inativo, nenhuma saída é executada ou garantida.

## Limitações financeiras conscientes

- Preenchimentos AUTO2/AUTO4 são SIMULADOS; o sistema não envia pedidos à Bybit. Qualquer parcial ou stop anotado localmente não protege capital real.
- O D452 lê exposição, pending e kill-switch no diário persistido. Não existe ainda recibo obrigatório de preço, taxa, slippage e funding para **todos** os fills, nem PnL realizado completo. Portanto não há autorização para inventar loss=0 após uma posição preencher; novas aberturas com custo desconhecido continuam bloqueadas.
- A regra AUTO8 ainda impede abrir outras posições PAPER quando existe uma abertura que requer proteção não verificada; suporte a múltiplas posições no armazenamento não significa múltiplas entradas já autorizadas.
- N50 por turnover24h é provisório; composição pode mudar e exigir warmup de 24 candles; a origem das moedas não equivale a auditoria financeira da coorte. Sem backtest J3 OOS e homologação J6 contínua, não há alegação de rentabilidade.
- Custo adicional R$0. J1 intocada. Sem credenciais privadas, automação de ordens reais, publicação de serviço, migration ou release de produção.

## Provas e aceite

`tests/test_j2_j4_resident_paper_operator_d453.py` valida sessões repetidas, fallback com ACK e quote realista do parser D386, trigger de parcial, fill D394 em BBO posterior, cancelamento/erro de feed, isolamento, trava entre processos e status terminal. `tests/test_run_j2_j4_public_paper_resident_d453.py` valida carregamento da política 0600, 50x, margem, parciais, recusa sem opt-ins, symlink, floats e duplicatas JSON. Exigir CI Linux + Windows + navegador no SHA exato e uma demonstração host sem API privada antes de julgar o serviço homologado.

## Próxima entrega de produto

Construir **contabilidade econômica vinculada a fills**: preço BBO ao FILL, taxas de entrada/saída, slippage, funding e PnL realizado diário no mesmo fluxo financeiro PAPER. Só depois adaptar o gate AUTO8 para permitir mais de uma posição PAPER sob limites agregados reais de pesquisa (sem confundir stop simulado com proteção nativa). A seguir, instalação de serviço PAPER isolado sob gate de publicação, com watchdog e UI de status.