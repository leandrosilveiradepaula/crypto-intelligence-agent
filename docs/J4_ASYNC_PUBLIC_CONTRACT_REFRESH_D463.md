# D463 — renovação assíncrona de metadados para entradas PAPER causais

## Problema funcional corrigido no código

O aquecimento D461 de 50 contratos pode levar mais de 100 segundos. O D451 exige que os metadados de margem, lot step, preço mínimo e alavancagem usados em uma **nova entrada PAPER** tenham no máximo 60 segundos; o PRE11/D449 restringe a validade a 30 segundos. O resultado, sem correção, seria o J2 avaliar a vela ao vivo, mas impedir toda nova posição por um contrato historicamente observado e agora velho.

**Nunca** se deve colocar `observed_at_ms` igual ao recebimento de uma cotação para fingir atualização de instrumentos, nem aumentar arbitrariamente o TTL, nem aceitar um contrato modificado sem reexaminar lot/limites.

## Implementação

- `j4_public_paper_contract_refresh_d463.AsyncPublicPaperContractTerms` é um provedor independente, não bloqueante no callback do ticker. No primeiro BBO de um candidato que ainda não tem contrato recente, enfileira apenas o símbolo (limite 50), nega a abertura e não cria AUTO2.
- Um **terceiro worker controlado pela lease D450** consulta somente a API REST pública `/v5/market/instruments-info?category=linear&symbol=...`, usando o mesmo cliente Bybit público limitado e suas regras conservadoras de intervalo, tamanho e não-retry. Tenta no máximo uma consulta por símbolo a cada 15 segundos.
- `bybit_dynamic_contract_shape_d463._check_contract_identity` exige contrato trading USDT LinearPerpetual, identidade/launch time/cap alavancagem/tick/lot/minNotional/maxOrderQty **exatamente iguais** aos do N50 original. Qualquer alteração ou campo incompleto veta novas aberturas.
- O timestamp recente do contrato é o **recebimento do GET** após o fornecedor responder, nunca antes dele. O próximo BBO, com `quote.received_at_ms >= observed_at_ms` e idade <= `config.max_contract_age_ms` (max 60s), poderá realizar os controles PRE11/RiskGate existentes. Enquanto o GET está pendente ou nega, a candidata não consome ordem, sidecar, margem nem posição.
- D449 remove o bloqueio de tentativa **somente para a condição transitória do contrato ainda não atualizado**. Falhas do livro, de risco, funding desconhecido ou planilha econômica não são convertidas em aprovação; RiskGate continua obrigatório. O refresh pode ocorrer em paralelo à supervisão de posições existentes, sem paralisar o ticker de saídas.
- O encerramento do terceiro worker está vinculado à mesma `ThreadPoolExecutor` do D450; ele não fica executando após a lease. Seu relatório sanitizado apresenta pedidos, contratos idênticos aceitos, rejeições e fila, sem preços, URLs arbitrárias ou segredos.

## Validações e limites

- Testes unitários D463: fonte local injetada, nenhuma chamada HTTP em callback ticker, GET posterior, impossibilidade de usar um BBO anterior ao GET, rejeição de alteração contratual, renovação por TTL, encerramento de thread inativa e opt-in obrigatório.
- Regressão D449: primeira cotação aguarda atualização, segunda cotação posterior pode reservar OPEN PAPER sob limites já existentes, sem duplicar ordens.
- Integração D462: 50 símbolos, histórico REST 24h, último WS `confirm:true` e J2 calculado; contratos só refrescados **para candidatos**, não para todo o universo a cada tick.
- O endpoint REST é público, sem API key, sem ordens de corretora; contratos e alavancagens permanecem **hipóteses de pesquisa**, nunca certificação de margens/tier reais.
- Ainda faltam prova pública real de candle horário WS no código novo, validação de contingência e CI do SHA final. O serviço systemd candidate continua desativado; **não houve release na VPS**.

**J1 intocada, despesas adicionais R$0, negociação automática real proibida.**
