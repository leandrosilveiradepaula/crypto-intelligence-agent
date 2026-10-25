# Governança de direitos de dados de mercado — J1/WU17

## Descoberta documental verificada em 25/10/2026

A Kraken informa em seu guia oficial de APIs que **determinados usos requerem permissão prévia**, incluindo usos **comerciais não pessoais** de dados obtidos em endpoints publicamente acessíveis. O guia abrange REST e WebSocket, Spot e Futures.

- Fonte primária, seção **Notices**: https://docs-legacy.kraken.com/api/docs/guides/global-intro/#notices
- Introdução Derivatives (acessibilidade pública, sem key): https://support.kraken.com/articles/360022635512-introduction-derivatives
- Contato **indicado pela própria Kraken** para solicitar permissão de uso dos dados: `marketdata@kraken.com`.
- O fato de a API responder HTTP200 sem credenciais **não concede** automaticamente licença comercial, direito de redistribuição ou acesso ilimitado.
- Esta análise é um gate técnico/documental, **não parecer jurídico** nem interpretação definitiva dos termos aplicáveis a um usuário, entidade ou jurisdição. Termos podem mudar; verificar versão e direitos antes de qualquer lançamento.

## Matriz de cenários e gates

| Cenário previsto | Estado da evidência | Gate |
| --- | --- | --- |
| Código aberto no GitHub, sem dumps nem chaves | Código separado de dados; nenhum dado bruto de terceiros versionado | Permitido como desenvolvimento de software, observadas licenças do próprio código |
| Pesquisa pessoal/interna, sem redistribuição | Endpoints públicos tecnicamente acessíveis; sujeitos aos termos da Kraken | Prosseguir apenas em escopo de pesquisa conforme termos aplicáveis, sem tratar acesso como licença comercial |
| Painel privado autenticado para uso próprio | Não foi confirmada licença específica; modo de uso e modalidade ainda dependem da finalidade real | Não presumir direitos de exibição ou exploração comercial; avaliar termos e região antes de release |
| Painel para terceiros, com dados ou alertas derivados da Kraken | Nenhuma autorização comercial ou redistribuição verificada | **BLOQUEADO** até revisão do uso pretendido e direitos expressos para essa modalidade |
| API pública, retransmissão de preços, venda de dados, serviço comercial ou monetizado | Guia oficial cita exigência de permissão prévia para usos comerciais não pessoais | **BLOQUEADO** sem comprovação de permissão/licença apropriada |
| Divulgação de histórico bruto em repositório público | Não há direito de redistribuição comprovado | **BLOQUEADO** |

A tabela diferencia **código público** de **dados de mercado públicos**: disponibilizar o cliente de software em repositório público não é o mesmo que republicar candles/volumes/dados da exchange. A licença de software livre não transfere direitos sobre dados fornecidos por terceiros.

## Estado específico dos fornecedores

- **Kraken Futures:** contrato de cliente somente GET no módulo `KrakenPublicReadOnlyResearch`, rede desligada por padrão; a fonte de direitos para publicação/uso comercial não foi validada. Não publicar market data em UI pública nem exportar feeds comerciais sem autorização.
- **Bybit V5 (candidato puramente OFFLINE):** documentos oficiais distinguem `volume` base coin e `turnover` quote coin para linear USDT/USDC: https://bybit-exchange.github.io/docs/v5/market/kline . Os termos da API restringem exploração comercial/revenda de dados: https://www.bybit.com/en/help-center/article/API-Terms . Até avaliação de direitos/geografia/uso e fonte real, não consultar a exchange nesta work unit, não integrar para serviço público, nem supor licença geral.
- **Binance Futures:** a primeira consulta pública foi bloqueada HTTP451 no runner (issue #19). Não contornar a restrição, nem confundir acesso físico com direitos de uso.
- **CoinGecko Demo e CoinPaprika Free:** avaliações na `docs/CRYPTO_REGISTRY.md` indicaram limites para uso comercial gratuito; não incorporar feeds/asset registry ao produto sob a premissa de direitos ilimitados.
- **Trust Wallet Assets / Uniswap Token Lists:** bibliotecas ou listas abertas não certificam identidade do ativo futuro Kraken nem direitos de redistribuição de todos os dados e imagens. Não derivar licença de um logo ou licença MIT apenas do repositório de código.

## Política operacional: antes de dados em produção

1. Confirmar com o Product Owner a **modalidade efetiva de uso** (pessoal interno, painel privado para titular, painel público para usuários ou monetização) somente quando for necessário para decidir um release/material produto. Não fazer alterações materiais de finalidade implicitamente.
2. Mapear, por provedor e conjunto de dados (instrumentos, OHLC, volume, funding, derivados), quais dados serão lidos, armazenados, mostrados, transmitidos ou exportados. Dados agregados e alertas derivados também podem ter restrições; não presumir que transformação elimine direitos.
3. Obter **evidência explícita de licença ou autorização aplicável** para uso previsto; registrar texto, data, URL/canal, titular, abrangência e prazo no GitHub em referência sanitizada (nunca credenciais, e-mails privados ou documentos confidenciais no repositório público).
4. Manter estado `commercial_or_public_distribution_authorized = false` **como declaração de produto/documentação**, não como flag ou credencial de permissão implementada. Só alterar decisão com base comprovada e gate humano de release; na ausência de evidência, bloquear disponibilização pública/comercial.
5. Nunca converter a confirmação de read-only/HTTP200 em autorização para trading; validar separadamente elegibilidade legal/regional, margens, risco, liquidação e termos.
6. Custo adicional = **R$0,00**; não contratar serviço pago, disparar e-mail em nome do titular, solicitar licença paga ou liberar produção sem autorização apropriada.
7. Continuar **em modo offline e com fixtures sintéticas** nas work units que dependem de dados cuja licença ainda é incerta. Reutilizar apenas os endpoints públicos para pesquisa privada quando permitido pelos termos aplicáveis.

## Relação com as pendências técnicas

- **J1 #2**: ainda aberta. CI verde valida software, não direitos de uso, qualidade do mercado, estratégia, backtest ou produto.
- **WU10 #32**: identidade crypto-only positiva ainda exige base verificável e licença compatível; os metadados Kraken têm categoria `xStocks` com `tradfi=false`.
- **WU12 #36**: o campo `trade candles.volume` Kraken segue com unidade financeira não demonstrada; `unit_proof=false`.
- **WU16 #46 / PR #47**: cliente GET-only integrado SHA `6d5b37aba154b0fb6a950fbffa4ba3e18d01410e`, CI pós-merge #40203821568 SUCCESS (213 testes offline + 11 docs), sem novo acesso live nem serviço em produção.
- **WU17 #48**: esta política documenta riscos de licença/redistribuição. A questão externa de autorização comercial, se aplicável, continua **não resolvida**, mesmo depois de a documentação técnica passar na CI.

Próximos passos: conservar as evidências de licenciamento e arquitetura aqui, evitar novas sondagens live não necessárias, e avançar na validação independente de fontes/identidades sem inventar direitos de uso. Antes do release, reavaliar a modalidade de produto e os termos vigentes, com gate humano aplicável.


## WU19 — Gate de finalidade em código, sempre conservador (issue #52)
O módulo puro `crypto_intelligence_agent/provider_usage_gate.py` tipa os provedores Kraken/Bybit/Binance, datasets (instrumentos, candles, tickers, funding, alertas derivados) e finalidades distintas (pesquisa interna, painel privado, exibição pública, API pública e comercial). Aceita `RightsGrantEvidence` com revisão identificada, período de vigência, URL HTTPS, versão e declaração explícita do escopo, **mas não comprova autenticidade da licença nem substitui revisão jurídica/humana**. O resultado atual permanece `allowed=false` para todas as modalidades até existir processo externo real de confirmação e release: mesmo `grant_confirmed=true` e `externally_reviewed_release_gate=true` inseridos pelo chamador não autorizam distribuição. `INTERNAL_RESEARCH` retorna estado informativo `internal_research_subject_to_current_terms_review`, não licença automática. Ausência/obsolescência/futuro/escopo incompatível são recusados, e nenhuma resposta divulga dados comerciais. Não conectar esse gate diretamente a produção/UI: o release humano precisa validar a modalidade real do produto, território, contrato de licença e fornecedor. Fixtures de testes **sintéticas**, nunca autorização.
