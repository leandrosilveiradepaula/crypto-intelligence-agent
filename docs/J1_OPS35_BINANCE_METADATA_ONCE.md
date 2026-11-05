# J1/OPS35 — auditoria finita Binance exchangeInfo, sem candles

## Missão e limites

Após a prova de duas velas `x=true` OPS33 e o auditor de contrato/Top50 OPS34, a OPS35 prepara a primeira auditoria pública Binance somente de *metadados de instrumentos*. A execução real não é parte desta PR. Não há autenticação de perpétuo USD-M a partir de URL, stream, símbolo ou hash, nem prova marketwide Top50; `usdm_contract_verified=false`, `canonical_ohlcv_approved=false`, `marketwide_top50_verified=false`, `continuous_collector_authorized=false` e `orders_sent=false` invariáveis.

A CLI `python -m scripts.probe_binance_exchange_info_once` é **off por padrão**, recusa root e exige `--allow-public-network --confirm-region-and-personal-research` (gate explícito da região/pesquisa pessoal). Ela carrega o registro de identidades revisadas existente e recusa revisão PIT obsoleta/futura antes de chamar a rede. Como a última revisão 52 bases é de 29/10/2026, sua janela D240 de sete dias pode estar vencida. Nesse caso o comportamento correto é `metadata_local_registry_or_config_abstain` sem GET. **Não relaxar a idade do registro nem inventar nova revisão para forçar o piloto.** Revisão pública independente é necessária.

A conexão read-only usa apenas URL fixa `https://fapi.binance.com/fapi/v1/exchangeInfo`, **até duas GETs**, timeout de oito segundos, tamanho de body <=2 MiB, sem redirect, sem proxy ambiental, sem autenticação, cabeçalhos personalizados mínimos, sem retry de HTTP 403/418/429/451, sem contornar georrestrições, sem persistência e sem imprimir payloads ou corpo de erro. O adaptador de transporte é injetável para testes e não inicia rede por importação. O HTTP client existente `market_data.UrllibTransport` foi inspecionado, mas seu `read()` ilimitado e redirecionamento padrão não satisfazem os gates desta prova isolada; a nova operação reusa os tipos/regras do módulo OPS34 em vez de alterar o adaptador geral em produção.

Após a captura o código revalida cada JSON com proibição de chaves duplicadas e NaN, horário request/response, hash canônico do payload e `_catalog` OPS34. Exige duas respostas com catálogo idêntico por instrumento, descartando `serverTime` apenas para diff: o provedor documenta que esse campo não deve ser usado como relógio. A declaração de corpo completo ainda não é prova autônoma de marketwide; o relatório preserva `catalog_completeness_authenticated=false` e contabiliza somente candidatos revisados e desconhecidos, sem publicar símbolos, preços, URLs ou tempos absolutos.

## Testes e decisão

Executar `python -m unittest discover -s tests -p test_j1_binance_metadata_probe.py -q`, regressões OPS34/OPS33/OPS32, validação de sintaxe/docs, CI Linux/docs, Windows/offline e Chrome/PAPER pré e pós-merge. Casos de 0 opt-in, root, limite de duas GETs, erro HTTP sem retries, oversized/empty/nonbytes, JSON duplicate/NaN, mudança de catálogo, campos duplicados, relógio NTP/captura, registro PIT futuro/velho, TradFi/expiring, sem autenticidade, saída allowlisted e ausência de rede/dados em defaults.

**Próximo gate:** somente após PR/CI e nova revisão válida do registro PIT caso necessário, considerar um único comando de homologação owner-only na VPS para consultar catálogo, com SHA Git limpo, acesso regional permitido, custo R$0, claims OPS23/25/26/31/33 intactos e ausência de serviço concorrente. A execução é informativa e não deve iniciar 24h, backfill, SQLite ou ordens. Issues J1 #2, Top50 #319 e OPS1 #429 continuam abertas.

## Continuidade offline proposta — captura isolada da revisão PIT

A revisão de identidade com sete dias de validade e a captura de *metadados*
representam duas evidências diferentes. Para evitar que um registro expirado
inviabilize qualquer auditoria descritiva do catálogo, uma ampliação de escopo
**explícita e separada** da OPS35 aceita `--catalog-only-unverified` em conjunto
com os dois opt-ins de rede e a verificação non-root. Esse modo **não carrega
registro de identidades**, não classifica qualquer candidato como crypto
revisado, e não converte um GET em prova de identidade USD-M. A saída tem
`status=metadata_catalog_only_unverified`, `identity_registry_applied=false`,
`reviewed_crypto_perpetuals=0`, a contagem de contratos com formato potencial,
a contagem de excluídos e o hash agregado dos catálogos pre/post. Nunca contém
símbolos ou velas. Os invariantes de autorização de persistência, Top50,
contrato, fonte e ordens permanecem **false**.

A auditoria convencional **continua exigindo o registro atual antes do primeiro
GET**. Se a revisão vencer durante a janela de duas consultas, o primeiro
resultado não é promovido e a segunda requisição é bloqueada caso ainda não
seja iniciada. Não se alteram carimbos PIT, janela de sete dias nem versões
registradas. Nas duas modalidades continuam obrigatórios os opt-ins, restrição
regional aplicável, resposta limitada, URL fixa, não-root e fail-stop HTTP.

Este adendo especifica o contrato de engenharia da D242. A validação e a
integração do código são etapas separadas de qualquer execução real na VPS:
**não autoriza disparar consulta, instalar serviço nem ativar coleta contínua**.
A aprovação de um relatório de metadados não equivale à homologação de sinais,
identidade de contratos, Top50 marketwide, fonte canônica ou negociação.
