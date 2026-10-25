# Decisões do produto

Estas decisões foram confirmadas pelo Product Owner e não podem ser alteradas silenciosamente.

- D01: mercado inicial de futuros perpétuos de criptomoedas. Universo dinâmico, referência inicial nos 50 contratos elegíveis de maior volume.
- D02: alavancagem global inicial 50x, configurável. Mudanças afetam apenas novas posições; cada posição preserva a alavancagem de abertura.
- D03: margem configurável por posição; US$ 1 a US$ 5 são exemplos, não limites. Quantidade de posições é variável, sem meta fixa.
- D04: núcleo de decisões quantitativo/estatístico. Regimes, BTC, tendência, rompimentos, compressão, correções, força relativa, volume, liquidez, volatilidade e derivativos.
- D05: saídas fragmentadas configuráveis sobre posição inicial ou saldo remanescente; manter parcela residual para tendências longas.
- D06: entradas e saídas reais executadas manualmente na primeira versão; não implementar ordens automáticas.
- D07: custo adicional autorizado R$ 0. Sem serviços pagos ou APIs pagas. Créditos Codex existentes são permitidos nos limites da conta.
- D08: interface responsiva, simples, mobile-first e em português.
- D09: engenharia começa pelo Codex direto; ChatGPT coordena. Factory somente após comprovação de autonomia.
- D10: autonomia por jornada, sem pedidos repetidos de "prossiga"; merges de PRs sem produção podem ocorrer após gates verdes e SHA verificado.
- D11: GitHub é a fonte de verdade; contexto deve sobreviver a novos chats por documentos, issues, PRs e estado operacional.
- D12: validação rigorosa com trajetória intrabar, custos, funding, slippage, liquidação, walk-forward e teste fora da amostra.
- D13: repositório público, por decisão expressa do Product Owner em 25/10/2026. Jamais publicar credenciais ou informações privadas.

Hipóteses ainda não aprovadas: parâmetros dos sinais, seleção final de tecnologia, percentuais ótimos de realização, gatilhos de trailing e modelos de ML. Cada decisão nova deve receber justificativa e evidência.

## D14 — Adaptador público read-only e testes por fixture (J1/WU1)

O primeiro adaptador implementado atende apenas endpoints públicos de futuros USD-M e não possui qualquer capacidade de autenticação ou envio de ordens. O domínio conserva `Decimal` e UTC em milissegundos; o transporte HTTP é injetável para que CI e regressões usem fixtures offline. Throttling recebe no máximo duas novas tentativas, com backoff exponencial configurável, antes de falhar explicitamente. O provedor é uma implementação inicial substituível, não uma escolha definitiva de fonte histórica nem uma validação de disponibilidade/cobertura gratuita.

## D15 — Integridade temporal e validação Python na CI (J1/WU1)
Decisão técnica: rejeitar OHLC/volume inválidos, timestamps truncados, durações incoerentes, duplicatas de ticker divergentes e horários de observação impossíveis. Não permitir rotular dados atuais de metadados ou volume móvel de 24 horas como snapshots históricos. Testes Python offline passam a integrar o gate obrigatório da CI para PRs que modificarem código Python. Limitação: histórico genuíno ponto-no-tempo ainda depende de persistência futura.

## D16 — SQLite transacional de referência para J1/WU2

SQLite da biblioteca padrão é o backend local de referência, encapsulado por `MarketDataStore`, sem compromisso de adoção em produção. Candles, contratos e snapshots preservam `Decimal` como texto e UTC em milissegundos. Cada página de candles e seu checkpoint são uma transação indivisível; replay igual é idempotente e conflito ou lacuna falha fechado. A janela histórica é `[start_open_ms, end_open_ms)` para evitar ambiguidade de limite. Limitação: este backend não cria disponibilidade histórica, nem substitui a necessidade posterior de retenção, backup, concorrência operacional e fonte ponto-no-tempo validada.


## D17 — Checkpoints fail-closed e metadados históricos imutáveis (revisão J1/WU2)
Revisão técnica confirmou que CI verde com paginação nominal não basta para garantir uma série histórica íntegra. Antes de saltar por um checkpoint, validar a cobertura real e a proveniência da série. Rejeitar janelas anteriores ou desconexas e mudanças de fonte/versão, preservar início da linhagem ao estender e exigir continuidade atômica. Gravação direta de páginas verifica OHLC, identidade, tempo e volume. Contratos existentes com o mesmo instante não podem ser substituídos silenciosamente. Relatório de conflitos não medidos usa `None`, não zero. Candles semanais seguem início de segunda-feira UTC. Esta é uma decisão técnica de segurança/reprodutibilidade, não alteração do produto.

## D18 — Pipeline offline por padrão e rede pública apenas sob opção explícita (J1/WU3)
A primeira execução de ponta a ponta deve ser reproduzível sem acesso externo e sem credenciais. CLI stdlib usa por padrão fixtures sintéticas identificadas como tal. O modo live, estritamente read-only, exige `--mode live --allow-public-network` e não é executado em CI. Auditoria local registra endpoints públicos, fontes, hora de captura em UTC-ms, versão do ranking, símbolos, falhas e resultados de coleta. Snapshots de volume móvel atual não são histórico de elegibilidade. SQLite mantém uma tabela aditiva de eventos, sem migration destrutiva. Esta decisão é técnica e não constitui autorização para operar ordens, fazer gastos ou implantar na VPS.

## D19 — Gatilho fail-closed de diferença de relógios (J1/WU4)
Antes de qualquer captura de mercado, comparar `GET /fapi/v1/time` ao relógio local em UTC-ms com amostras antes/depois do request. Adotar limite conservador de `abs(offset) + ceil(RTT/2) <= max_clock_skew_ms`, com padrão de 5 segundos configurável. Recusar discrepâncias, payload/HTTP inválidos e registrar evento de origem da falha sem avançar o histórico. Não ativar qualquer rede em CI, execução de ordens ou API paga. Esta é uma regra de qualidade temporal; não substitui validação de feed real e não modifica requisitos de produto.

## D20 — Classificação de acesso público e Retry-After conservador (J1/WU5)
Endpoint público HTTP 403/418 deve falhar sem retentativas automáticas; a causa de bloqueio depende de evidência e não pode ser inferida somente do código de status. HTTP 429 é tratado com número limitado de tentativas, backoff configurável e respeito a `Retry-After` numérico, desde que não exceda o tempo máximo seguro; atraso acima do limite encerra a tentativa sem colocar o IP em risco. Somente cabeçalhos públicos de limite são inspecionados, sem credenciais. CI continua offline. Ainda não há evidência de sucesso live nem de cobertura histórica completa; a WU5 permanece condicionada à execução real autorizada do smoke em ambiente com rede.

## D21 — Smoke GET público sob comando restrito na issue #19 (J1/WU5)
Para resolver o bloqueio DNS local sem pagamento ou VPS, utilizar runner padrão gratuito do GitHub Actions em repositório público. O workflow não pertence à CI de push/PR e só inicia com comentário literal do proprietário na issue #19. Sem segredos, permissões de escrita, deploy, operações financeiras, agendamento, banco persistente ou repetição automática. Limite: 1 símbolo e 3 candles; observar logs e registrar evidência datada. Teste online mal sucedido é bloqueio operacional, não prova de problema sistêmico na exchange. A J1 requer avaliação real de cobertura e confiabilidade para o aceite.

## D22 — HTTP 451 observado em runner GitHub, sem contornar restrições (J1/WU5)
Em 25/10/2026 UTC, o smoke GET público iniciado pela issue #19 no GitHub Actions (run `40197499250`) recebeu HTTP 451 na primeira consulta (`/fapi/v1/time`), **sem candles ou snapshots reais**. Esse status significa `Unavailable For Legal Reasons`; o corpo exato/motivo/território não foi estabelecido, portanto não atribuir causa específica sem evidência. Classificar como `ExchangeAccessError`, falhar sem retry nem proxy/VPN para contornar restrições e manter a J1 aberta. É permitida pesquisa técnica sobre fontes públicas **independentes** legalmente acessíveis, respeitando seus próprios termos e o custo R$0. RFC: https://www.rfc-editor.org/rfc/rfc7725 .

## D23 — Avaliar provedor independente antes de implementar outra integração (J1/WU6)
Após HTTP451 na Binance, a primeira alternativa de pesquisa é **Kraken Futures**, cuja API pública de instrumentos e candles é documentada sem exigência de chave para leitura. Isso não constitui troca de provedor principal nem garantia de oferta de 50 perpétuos elegíveis. A fase de viabilidade faz **uma única chamada GET** a `https://futures.kraken.com/derivatives/api/v3/instruments`, com autorização explícita, sem redirects, timeout curto, resposta limitada e JSON sanitizado. Símbolos com prefixos `PI_` e `PF_` contam apenas como **candidatos heurísticos**; a elegibilidade de perps, liquidez, volume comparável e histórico precisam de validação antes de selecionar universo. Respeitar regras e limites da fonte; nunca tentar contornar o bloqueio observado em outra API. Documentação: https://support.kraken.com/articles/360022839491-api-urls-derivatives e https://docs.kraken.com/api/docs/futures-api/charts/candles .


## D24 — Confirmar schema e taxonomia antes de adaptar Kraken Futures (J1/WU7)
A WU6 confirmou acessibilidade de `GET /derivatives/api/v3/instruments` em runner padrão: run `40198042787`, HTTP 200, 231 instrumentos, 213 símbolos com prefixos PI_/PF_. Essa contagem é **apenas heurística**; inclui ativos tokenizados não cripto (por exemplo `PF_AAPLXUSD`). Antes de construir segundo adaptador e montar universo Top50, observar instrumentos, tickers e candles de BTC via no máximo três GETs Kraken independentes, sem autenticação, evitando dumps brutos e com permissão dupla na CLI. O ticker pode oferecer volume cotado, mas devem ser estabelecidas unidades, múltiplos contratuais, duração/fechamento de velas, classe do ativo e elegibilidade histórica. Não substituir silenciosamente o provedor principal nem usar esta pesquisa para ordens reais.

## D25 — Probes reutilizáveis devem executar como módulos do projeto
O primeiro run real de conformance da WU7 (40198556326) falhou antes de acessar a Kraken, pois `python3 scripts/probe_kraken_market_schema.py` não incluía a raiz do repositório no `sys.path` para importar `scripts.probe_public_kraken`. Corrigir a invocação para `python3 -m scripts.probe_kraken_market_schema` dentro da raiz, testar em CI e não registrar falha de Python como bloqueio de fornecedor. Nenhuma segunda requisição deve ser tentada antes do workflow corrigido ser integrado com CI verde.

## D26 — Taxonomia de ativos por metadados da própria Kraken (J1/WU8)
A sondagem Kraken WU7 confirmou HTTP200 para 231 instrumentos/tickers e 3 candles BTC, mas `type=flexible_futures` e `tradeable=true` são compartilhados por BTC e tokenizado `AAPLx`. A elegibilidade crypto-only não pode derivar de prefixos PI_/PF_ ou do tipo de contrato. Reutilizar o único GET de instrumentos já documentado e, sob comando owner-only, registrar **apenas** distribuição de `category`, `tradfi`, `tags` e metadados allowlist para PF_XBTUSD/PF_ETHUSD/PF_AAPLXUSD. A execução não seleciona automaticamente ativos nem muda provedor; declarar filtro crypto-only somente após valores reais e regras testadas com exclusões de tokenizados. Preservar R$0, sem ordens, sem segredos ou contorno de restrições.

## D27 — Ranking Kraken só com registro crypto-only positivo e exclusão de ativos tokenizados (J1/WU9)
Após run `40199111677` identificar `xStocks` com `tradfi=false`, qualquer seleção Kraken deve falhar se não receber **registro versionado de bases cripto verificadas**. Requerer também exclusões por categorias não cripto, contrato ativo linear USD e ticker `tag=perpetual` com volumeQuote positivo Decimal; reduzir universo dinamicamente até `max_symbols` 50, sem hardcode de ativos nem meta de posições. `type=flexible_futures`/PF_/PI_/tradfi=false isolados não bastam. Módulo é instrumento de **pesquisa**, não aprovação de fonte principal/Top50 ou trade automático. Registro crypto-only independente permanece dependência a validar.
