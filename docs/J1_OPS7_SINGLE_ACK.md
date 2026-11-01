# J1/OPS7 — inscrição única e ACK compatível com Bybit linear

**Issue:** #429. **Estado:** implementação offline; nenhuma conexão nova na VPS, nenhuma ordem, nenhum deploy.

## Causa

O supervisor OPS3 usava seis pedidos de inscrição (10+10+10+10+10+2 tópicos) no mesmo socket, exigindo correlação com req_id em cada resposta. O ACK público linear da Bybit pode conter req_id vazio ou ausente; nesses casos os seis pedidos não têm correlação confiável. O controlador antigo era conservador e recusava o handshake, bloqueando também um cenário legítimo.

## Contrato corrigido

- Os 1–52 instrumentos revisados são convertidos em tópicos kline.60 e assinados **juntos**, em uma única solicitação por conexão, com lista ordenada e comprimento total args JSON <=21.000 caracteres.
- Não dividir a assinatura em lotes se o orçamento ultrapassar o limite: abster e impedir escrita no journal.
- O ACK só é aceito quando op=subscribe, success=true e campos válidos; req_id ausente, vazio ou exatamente cia-ws-1. Outro req_id é rejeitado; um segundo ACK na mesma sessão também falha fechado.
- Frames recebidos antes do ACK permanecem em quarentena limitada e só são processados após a confirmação válida; jamais declarar que a corretora assinou o universo com base apenas em frames parciais.
- Reutilizar o parser de velas fechadas confirm=true, idempotência, detecção de lacunas, relógio causal, heartbeat/pong, reconexão sob orçamento e SQLite WebSocket owner-only separada.
- O resultado continua marcado marketwide_top50_verified=false, source_authenticated=false, live_trading_authorized=false e orders_sent=false. Nenhum dado REST histórico antigo é migrado ou recapturado.

## Gates de validação

Testes offline exigidos: 52 tópicos/1 pedido; ACK sem req_id, vazio ou correto; ID errado, ACK duplicado, falha explícita e pré-ACK; gap, replay e heartbeat. Executar CI Linux/docs, Windows/offline e Chrome/PAPER no SHA revisado e após merge.

**Não é validação de rede real.** Antes de ativar systemd, uma sondagem finita owner-only deve confirmar ACK real de todo escopo, saúde do journal, número de horas fechadas e ausência de gaps/quotas. O Top50 entre todos os contratos elegíveis ainda depende da issue #319. O serviço OPS6 permanece off-by-default.

## Continuidade

Após integrar este contrato, priorizar homologação owner-only do handshake e coleta por 24h fechadas; se houver lacuna, abster até reconciliar com proveniência e orçamento em vez de tentar um novo backfill de 720h. Não executar ordens nem habilitar produção.
