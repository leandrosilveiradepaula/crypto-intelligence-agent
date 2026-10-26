# J1/WU42 — CandleFeed Free: estudo privado de volume-base e USD, sem ativação externa

## Resultado da diligência (26/10/2026 UTC)
Fontes originais: [documentação](https://candlefeed.ai/docs/), [preços e plano Free](https://candlefeed.ai/), [termos de serviço 2026-10-18](https://candlefeed.ai/terms/).

O serviço CandleFeed.ai (Foxsoft LLC) declara no plano grátis **US$ 0,00, sem cartão**, acesso aos **últimos 30 dias** para **até cinco símbolos** (BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT e DOGEUSDT, originados da Binance), **OHLCV + funding** e **100 chamadas por dia**. Não inclui universo elegível histórico Top 50, acesso multi-exchange no Free, backfill completo plurianual, funding de todos contratos, mark data, liquidação ou qualidade contratual já auditada.

Segundo a documentação do endpoint `GET /api/v1/candles`, `volume` é unidade BASE (BTC no BTCUSDT) e `quote_volume` é o total **reportado/normalizado em USD** pela agregadora. A venue de origem Binance BTCUSDT negocia par cotado em **USDT**; NÃO declarar que `quote_volume` em USD é montante líquido de settlement em USDT, que a moeda de margem do contrato é USD ou que o registro foi autenticado na Binance. Não combinar com candles da Kraken ou com o seletor de volume USD da Kraken sem alinhar contratos e origem.

Os termos §5.3 concedem licença limitada, não exclusiva, intransferível e revogável para uso **interno** em pesquisas, backtest e modelos próprios; proíbem redistribuir/revender dados brutos ou derivados substancialmente equivalentes e criar um produto de feed concorrente sem acordo escrito. O uso de gráficos/estatísticas agregadas é condicionado a não revelar os registros originais. **Seção 6 mantém obrigações aplicáveis de direitos das exchanges fonte** e o serviço pode remover datasets sob disputa de direitos. Isto NÃO é um grant público/comercial de feed Kraken, Binance ou CandleFeed, tampouco parecer jurídico de uso em uma interface para terceiros. Uma conta CandleFeed exige nome, e-mail e aceite de termos (somente o titular pode autorizar).

## Entregue no código
- `crypto_intelligence_agent/candlefeed_ohlcv_research.py`: parser research-only BTCUSDT/binance, 24 barras 1h fechadas UTC e contíguas, OHLC Decimal exato, `reported_base_volume_btc` e `reported_quote_volume_usd` separados, registry real BTC point-in-time (até 7 dias), data/cursor/paginação/status/contador rigorosos, e flags `canonical_ohlcv=false`, `live_exchange_origin_verified=false`, `public_or_commercial_redistribution_authorized=false`.
- `scripts.probe_candlefeed_private_ohlcv`: por padrão sem rede. Só faz **um GET**, via HTTPS, quando o titular já tem `CANDLEFEED_API_KEY` em ambiente **privado** e ativa `--allow-public-network --allow-private-research`. Usa (X-API-Key) no cabeçalho (não URL), endpoint fixo, redirecionamento/proxy/retry proibidos, corpo <=128KiB, JSON exato (sem floats binários nem chaves duplicadas), tempo de captura <=30s. O output exibe apenas status, hashes, flags e número de candles. Nenhum dado bruto, chave, preço ou volume é gravado.
- Testes automatizados OFFLINE, com servidor HTTP simulado (opener injetável); nenhuma chave válida é versionada, nenhuma chamada externa é realizada na CI.

## Gate externo — não executado
O usuário precisaria optar conscientemente por criar a conta Free sob os termos, e disponibilizar a chave **somente em ambiente privado protegido**, jamais enviá-la no chat, issue, PR, repositório público ou logs. Não há integração de secret no GitHub Actions por padrão; adicioná-la seria ampliação sensível de acesso e exige gate apropriado. Depois disso, teste manual e read-only para apenas **24 candles BTCUSDT 1h, uma requisição**, não replay automático nem scrape. Se `401/403/418/429/451` ocorrer, parar sem proxy ou novas tentativas automáticas.

Exemplo **sem chave no comando** (não executado pela entrega):

```sh
# A chave deve ter sido configurada em ambiente privado, fora do shell history.
python3 -m scripts.probe_candlefeed_private_ohlcv \
  --allow-public-network --allow-private-research
```

O código local não representa uma autorização para execução na VPS, release, cron, trading ou migração. O Free é insuficiente para Top 50 e para pesquisa fora da janela de 30 dias; qualquer upgrade pago violaria o orçamento autorizado R$ 0. Permanecem abertas J1 épica #2, crypto-only #32, unidade de volume **Kraken** #36 e direitos Kraken/publicação #48. Fonte CandleFeed pode sustentar um estudo PRIVADO com contrato/qualidade checados e elegibilidade regional, mas a etapa LIVE da WU42 não foi realizada.
