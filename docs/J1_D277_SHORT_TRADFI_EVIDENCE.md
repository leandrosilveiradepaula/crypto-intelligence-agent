# J1/D277 — os três instrumentos com 24h incompletas são TradFi documentado

Data da diligência retrospectiva: **11/11/2026 UTC**. Issues #319, #517. Evidências do banco congelado em 06/11/2026 com fim UTC `1793970000000`.

## Resultado real auditado na VPS

A tarefa administrativa auditável `4cdf91aaf75e41f5b89c3d3b3d0dde7a`, sob a identidade efetiva `cia-probe`, abriu o censo D256 owner em SQLite somente leitura, lock compartilhado, `PRAGMA query_only=ON`, `integrity_check` e replay `_replay` (exit code 0). Entre 822 contratos, **819** têm 24 velas completas e **3** têm apenas 2 candles cada:

| Símbolo | Qtd. | Ativo subjacente anunciado | Hora de listagem anunciada | Indício D264 |
|---|---:|---|---|---|
| DUOLUSDT | 2 | Duolingo | 06/11/2026 11:00 UTC | Negativo TradFi |
| FISVUSDT | 2 | Fiserv | 06/11/2026 11:00 UTC | Negativo TradFi |
| FNUSDT | 2 | Fabrinet | 06/11/2026 11:00 UTC | Negativo TradFi |

Os hints de listagem salvos no censo ficam próximos de 09:51 UTC, mas **não são** confirmação independente de listagem, e a hora da publicação não é uma observação PIT. Esses contratos referenciam **ações**, não tokens cripto.

## Fontes oficiais

A Bybit publica anúncios **individuais** datados de 06/11/2026 de futuros perpétuos TradFi, com texto explícito `Underlying Equity/Index`:

- [DUOLUSDT — Duolingo](https://announcements.bybit.com/en/article/new-listing-listing-of-duolusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--artde830783f6d5/)
- [FISVUSDT — Fiserv](https://announcements.bybit.com/en/article/new-listing-listing-of-fisvusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--art5e5431016814/)
- [FNUSDT — Fabrinet](https://announcements.bybit.com/en/article/new-listing-listing-of-fnusdt-on-bybit-tradfi-perpetual-on-nov-6-2026-11-00am-utc--artff454659fb47/)

Há também três indicadores de tipo TradFi no snapshot contemporâneo D264 capturado depois da janela. Em conjunto, isso estabelece uma **forte exclusão documental retrospectiva** dos 3 contratos curtos. Contudo, o snapshot de 08/11 não atesta como o catálogo estava classificado em 06/11; os anúncios foram revisitados em 11/11; não dizer que a identidade estava autenticada no instante de decisão. A prova cobre os 3 casos **específicos**, não o universo global de 822.

## Integração técnica

`j1_short_tradfi_primary.audit_short_tradfi` mantém URL oficial versionada, vínculo nominal exato e horário anunciado para as três, rejeita duplicatas/dados inválidos e distingue documentação TradFi posterior de certificação temporal PIT. Ela só recebe a lista de `incomplete` já validada pelo replay D256.

O próprio `scripts.j1_d264_private_metadata_snapshot.replay_private_snapshot` acrescenta `short_tradfi_documentary_research` aos seus dados, consultando apenas as linhas da tabela `incomplete` no **mesmo SQLite somente leitura**. Saída padrão é apenas contagem e digest; nomes e URLs aparecem somente com opt-in `--include-private-symbols`. Não modifica o censo, snapshot, timer, universo de trading ou parâmetros de alavancagem.

**Flags invariantes:** `all_short_rivals_independently_disqualified_pit=false`, `historical_provider_identity_pit_authenticated=false`, `marketwide_top50_verified=false`, `trading_enabled=false`. **Nunca** atribuir zero de volume aos contratos curtos e afirmar classificação global.

## Próximo passo

Após CI Linux/docs + Windows/offline + Chrome/PAPER e merge SHA exato, executar o novo replay já integrado como `cia-probe` na VPS, verificar contagens `3/3`, zero acesso externo e digests. Depois concentrar a diligência nos 50 candidatos de pesquisa e cinco substitutos de fronteira (LYN/DOT/ICNT/ELSA/AERO), incluindo riscos de migração de token AERO. A exclusão documental dos 3 shorts reduz a dúvida comercial, mas não preenche a identidade dos 50 nem transforma ranking retrospectivo em PIT.
