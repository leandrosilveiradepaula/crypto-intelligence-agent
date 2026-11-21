# D448 — Entrada PAPER até posição persistida, stops e parciais

## Resultado funcional

Esta entrega conecta os componentes existentes sem criar um segundo motor de ordens:

1. **J2 (D434/D435)** avalia a última vela pública Bybit `kline.60` confirmada sem reclassificar a origem como fixture.
2. **J3/PRE2 + PRE11 + RiskGate (D447)** validam custos hipotéticos, primeiro alvo, perda no stop, margem efetiva, alavancagem e risco. Uma hipótese permitida produz apenas `OPEN PENDING` no AUTO2.
3. **J4 (D448)** grava uma estratégia de stop/targets imutável e owner-only antes do fill, num arquivo descritivo que **não contém outro livro financeiro**.
4. Uma cotação **pública D385 posterior**, pós-ACK e com latência mínima, BBO não cruzado, spread e tamanho simulado de livro suficientes, pode gerar um **evento FILL explicitamente hipotético** no mesmo AUTO2, sob opt-in. O alvo líquido e a margem após um stop hipotético são reavaliados no BBO posterior usando custos declarados; um preço desfavorável bloqueia o fill simulado.
5. O AUTO4 registra a posição somente a partir do FILL do AUTO2 e conserva receipt de margem/alavancagem, plano de duas ou mais saídas e residual. Um manifesto D425 owner-only passa a incluir automaticamente a posição, que o worker D444/D445 monitorará no próximo ciclo e que a J5/D446 poderá visualizar. As cotações posteriores acionam as reservas existentes D389 de **stop-first ou realização parcial**.

## Recuperação e comportamento de falha

- Um mesmo símbolo/hora do J2 não cria outra intenção de abertura no AUTO2. A estratégia é imutável: tentativa de armamento com stop/targets modificados é recusada.
- Se o processo cair **depois do FILL AUTO2 mas antes de criar AUTO4**, uma retomada usando o plano persistido e `quote=None` registra a mesma posição sem inventar segundo fill.
- Se cair **depois de AUTO4 mas antes do manifesto**, a mesma retomada recria apenas a rota de monitoramento sem apagar saídas anteriores.
- O FILL hipotético novo também respeita o kill-switch persistente e a saúde AUTO8 **no mesmo BEGIN IMMEDIATE do AUTO2**; posições já abertas ou incertas continuam bloqueando novas aberturas, e uma saída de emergência existente não é suspensa.
- Arquivos privados mantêm proprietário não-root, diretório 0700, arquivos 0600, abertura sem symlink e `flock` D425. Falhas de leitura/manifesto/identidade abortam; nunca se infere confirmação da corretora.

## Limites e questões ainda abertas

- Nenhum `POST`, assinatura, endpoint privado, ordem real, fill real, stop nativo ou alteração da J1. A participação no melhor nível do livro é **hipótese para paper**, não prova de execução. Funding, gaps, risco de liquidação e custos da venue não estão homologados.
- Uma posição só é monitorada quando o worker D444 está de fato executando, com feed disponível; o registro no manifesto **não instala serviço** nem garante proteção durante uma falha. O fluxo D448 ainda exige a integração de um operador contínuo que forneça J2 fechado + as duas cotações causais e processe a retomada. A proteção via exchange segue inexistente.
- O Gate AUTO8 intencionalmente não considera uma proteção PAPER hipotética como proteção nativa de risco; por isso novas aberturas simultâneas podem ser vetadas, mesmo existindo suporte a múltiplas rotas em D445. Não contornar o gate para inflar contagem de posições.
- A coorte N50 dinâmica e a avaliação financeira J3 fora da amostra são trabalho de integração posterior. Nenhum resultado de rentabilidade foi alegado.

## Como verificar

`tests/test_j2_observed_paper_entry_d447.py` e `tests/test_j4_automatic_entry_materializer_d448.py` executam em SQLite temporário sem rede: LONG e SHORT, recibos com alavancagem 50x, entrada simulada BBO posterior, saída parcial e stop-first pelo D391/D389, leitura J5, repetição após restart, injeção de crash nas duas fronteiras de persistência, custo/stop/spread/liquidez inviáveis, fonte/tempo adulterados, plano mutável, permissões e kill-switch.

Exigir CI Linux/Windows/browser do SHA exato antes de merge; nenhuma publicação operacional autorizada. O código permanece em revisão e custo extra R$0.