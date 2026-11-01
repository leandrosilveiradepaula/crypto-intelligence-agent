# J1/OPS8 — Prova limitada de assinatura WebSocket linear com 52 tópicos

**Status de desenvolvimento:** ferramenta independente, somente leitura, desativada por padrão. **Questão de origem:** #429; dependência de universo #319; jornada J1 #2. **Custo extra:** R$ 0. Nenhuma ordem, credencial, REST ou escrita em SQLite.

## O que a sondagem comprova (e o que não comprova)

A Bybit V5 documenta o WebSocket público linear, a assinatura de múltiplos tópicos no mesmo pedido, um limite de 21.000 caracteres para o array `args`, heartbeat a cada 20 segundos e respostas de inscrição cujo `req_id` pode ser vazio. O tópico `kline.60` envia atualizações entre 1 e 60 segundos; `confirm=true` indica vela encerrada. Referências: https://bybit-exchange.github.io/docs/v5/ws/connect e https://bybit-exchange.github.io/docs/v5/websocket/public/kline.

O OPS8 oferece uma **única** sondagem real, opcional e curta para aferir se a Bybit aceita a inscrição agregada dos **52 nomes candidatos** do registro revisado, se chegam frames de mercado válidos e quantos tópicos distintos foram efetivamente observados. Não consulta o catálogo REST e **não presume** que os 52 nomes ainda estejam listados, que todos os tópicos foram entregues, que existe janela completa de 24 horas, que o Top50 cobre o mercado inteiro ou que o provedor está autenticado.

O resultado contém somente status categórico e contadores agregados: tópicos solicitados, ACK, frames, mercado após ACK, tópicos distintos vistos, eventos de candle fechado validados, tópicos distintos com fechamento e pongs. Não imprime símbolos, preços, volume, turnover, `req_id`, URL, tokens ou dados brutos. Nunca salva os frames. Mesmo com ACK aceito, `all_topics_delivered_verified=false` e `closed_24h_complete=false` permanecem.

## Segurança e orçamento

`crypto_intelligence_agent/bybit_ws_linear_live_probe.py` só abre um socket depois dos três opt-ins explícitos e de confirmar usuário POSIX **não-root**. A consulta ao registro local ocorre **depois** desses gates. A duração padrão é 35 segundos (máximo 90); orçamento padrão 512 frames (máximo 1.024); sem retry, sem backfill, sem GET e sem processo background. Só uma assinatura com todos os tópicos, req_id ausente/vazio/esperado no ACK. O frame de dados antes do ACK não é aceito como prova, e ACK duplicado, ID inesperado, tópico fora da lista, campo inválido ou dado temporal/financeiro inconsistente resultam em abstenção.

Para uma prova de fechamento é necessário atravessar um UTC boundary enquanto o socket recebe atualizações. A ausência de um `confirm=true` num teste de 35 segundos **não significa falha** da conexão, somente ausência de evidência de fechamento nessa janela.

## Invocação futura pelo proprietário, uma vez, com HEAD aprovado

O repositório mantém a CLI `python3 -m scripts.probe_bybit_ws_linear_live`. A invocação pública da CLI é:

```bash
python3 -m scripts.probe_bybit_ws_linear_live \
  --allow-public-network --allow-public-websocket \
  --confirm-region-and-personal-research \
  --seconds 45 --max-frames 512
```

**Não executar como `root`, não instalar systemd e não misturar este probe com a coleta histórica.** Na VPS, deve ser usado o usuário não privilegiado da pesquisa e checkout no SHA aprovado da `main`. O operador deve validar primeiro a versão do Python e a presença da dependência `websockets`. A sondagem não exige nem cria diretório de dados, banco, pidfile ou configurações do sistema.

## Matriz de aceitação offline

Executar `python3 -m unittest discover -s tests -p test_j1_ws_linear_live_probe.py -v`: 52 tópicos num só request, ACK com `req_id` ausente/vazio/esperado, NACK, ACK duplicado, ID errado, frames antes do ACK, velas abertas/fechadas estritas, tópico desconhecido, frames malformados, pings/pongs, falha de socket, timeout, limites, opt-in negativo e usuário root. Prova de que testes offline não criam socket real nem fazem GET. CI Linux/docs, Windows/offline e Chrome/PAPER, revisão SHA e CI pós-merge são gates de engenharia; **não** equivalem a sucesso live.

## Próxima etapa operacional da #429

Após a CI no SHA exato e um resultado real sanitizado dessa sondagem: decidir se o socket/handshake de 52 tópicos foi aceito, corrigir o comportamento específico observado, executar um piloto finito owner-only de candles confirmados em diretório **novo e separado**, e só então discutir a instalação/ativação de supervisão `systemd` com teste de 24h. Se o resultado for bloqueio regional, erro de rede ou indisponibilidade, não criar retries nem improvisar PIT. O principal trabalho J1 #319 ainda requer cobertura independente de todos os perpétuos elegíveis.