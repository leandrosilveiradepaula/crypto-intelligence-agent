# D522 — pesquisa local de combinações, com monitor disponível

## Fluxo
O painel owner existente apresenta seção 6, botão Executar bateria e horizonte 1–12h. A matriz padrão tem 25 estratégias. A execução escolhe o último suplemento 5m disponível para fixar o cutoff. Nenhuma gravação de política, dados de mercado, diário ou posição. Consulta de status não dispara trabalho; apenas POST explícito inicia uma bateria. O worker usa subprocesso Python fixo com prioridade reduzida, timeout de 300s, um job por vez. A política é lida e verificada por revisão; alteração concorrente invalida resultado. O relatório fica somente na memória do processo, substituído na próxima execução ou perdido em reinício.

## API privada
GET /api/combination-research: idle/running/completed/failed, id, parâmetros, último relatório. POST no mesmo endpoint requer loopback, Host, Origin e header X-CIA-Paper-Profile: 1, Content-Type application/json. Corpo limitado a 70k; campos horizon_hours (obrigatório), as_of_ms (opcional, cutoff), matrix (opcional, esquema D520 até 24 perfis adicionais, JSON tipado). O padrão é a matriz versionada. Nenhum caminho, comando ou credencial é aceito. Exemplo de execução de 4h via cliente local autorizado:
```bash
curl --fail --silent --show-error \
  -H 'Origin: http://127.0.0.1:8766' \
  -H 'X-CIA-Paper-Profile: 1' \
  -H 'Content-Type: application/json' \
  --data '{"horizon_hours":4}' \
  http://127.0.0.1:8766/api/combination-research
```
Consultar GET até estado terminal. Não presumir que o MCP permite POST; se negar, respeitar o limite. Não habilitar porta pública.

## Aceite e limites
Testes de corpo/limites, processo único, timeout, integridade da revisão do perfil e matriz, gate loopback/same-origin e GET somente leitura. CI/revisão antes do merge; publicação sob gate próprio. O trabalho usa hipóteses independentes em amostra já conhecida, sem OOS, funding/liquidação, carteira ou execução. Não há escolha/ativação automática, nem backtest aprovado. A matriz D520/D521 já está integrada, mas nenhum resultado real novo está comprovado nesta nota. Sem ordem real ou custo.
