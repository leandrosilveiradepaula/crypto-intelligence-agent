# J5/D417 — qualidade do feed público N50 visível no celular

## Objetivo de produto

A prova real owner D416 em 18/11/2026 observou os 50 instrumentos
e 5.388 cotações pós-ACK, mas apenas 46 estavam frescos no encerramento
de 32,003 segundos. Os outros 4 tiveram cotações antes elegíveis,
que expiraram sob o limite de **3.000 ms de horário da exchange**.
Nenhum callback recebido estava acima de 3 segundos de atraso
exchange→recepção; isso **não garante** próxima atualização ou negociação.

O usuário não deve depender de ler JSON bruto para entender a saúde de
sua pesquisa. O aplicativo móvel PT-BR agora aceita, pelo **mesmo
seletor de arquivo local**, o sumário de `scripts.probe_current_j1_n50_bybit_ws_d406`
que já existia, e o apresenta separado do diagnóstico J2/J4/D410 de
reservas de stops/parciais PAPER.

## Comportamento

- Identifica exclusivamente `j2-current-owner-n50-ws-probe-d406-v1`,
  com chaves exatas, limites de contagem, prova de integridade aritmética
  do particionamento D416, digest com 64 hex e flags de rede/contas/ordens
  estritamente validadas. Rejeita campos desconhecidos, símbolos e
  metadados de conta adicionados ao arquivo.
- Mostra cobertura observada, cotações frescas no fim,
  anteriormente elegíveis agora expiradas, contratos sem cotação pós-ACK,
  callbacks sem cotação elegível, atrasos da exchange e reconexões.
- Mesmo `finite_coverage_fresh_at_end=true` significa **somente amostra
  finita** e nunca liberação de entradas, edge, stop nativo ou feed
  contínuo. Em cobertura parcial o painel exibe que entradas não estão
  autorizadas.
- Exibe explicitamente que **não há posições/saídas PAPER avaliadas**
  nesse arquivo de cotações públicas. O arquivo D410 continua no mesmo
  componente e preserva seu validador e renderização antigos. Não
  mistura os dois contratos, nem infere fills ou resultado financeiro.
- Retém tudo somente em memória do navegador. O celular não consulta a
  VPS, não usa WebSocket, não abre endpoint de ordem, não preserva o
  relatório em storage e não declara a origem do arquivo autenticada
  por um terceiro. DOM usa apenas `textContent`.

## Provas, limites e sequência de execução

`tests/test_j5_public_n50_ws_health_d417.py` contém fixture
inteiramente sintética e testes Node para importação, renderização de
46/50 e 4 expirados, recusa de falsificação de flags, chaves extras,
integridade de contadores e sha. A suíte prévia
`tests/test_j5_paper_ws_health_d412.py` assegura compatibilidade com o
relatório D410/PAPER.

A fonte real D416 já foi verificada em piloto isolado e registrada na
issue do feed; o arquivo bruto da VPS **não foi publicado** nem
injetado em `web/app`. Nenhum serviço local foi instalado ou
publicado. Pilotos de 24×7, autenticação, receitas financeiras,
testnet, ordens reais ou acesso a API privada da Bybit exigem etapas e
gates próprios. Preservar o único escritor J1.
Custo adicional autorizado: R$ 0,00.
