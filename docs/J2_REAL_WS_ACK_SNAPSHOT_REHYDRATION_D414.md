# D414 — ACK real da Bybit seguido de delta sem snapshot inicial

## Evidência operacional — 17/11/2026 22h34 UTC

O operador executou no host `srv1319424`, sob `cia-probe`, os dois probes públicos finitos a partir de tarball GitHub **SHA `ca17da33a7cb91a16b15262643c3aa42bc60cacd`**. A coleta owner J1 não foi modificada nem reiniciada.

| Sessão | BTC único (D405) | N50 owner (D406) |
| --- | ---: | ---: |
| WebSocket real aberto | Sim | Sim |
| Frames recebidos | 9 | 265 |
| Pré-ACK sem callback | 7 | 263 |
| ACK de assinatura válido | **1** | **1** |
| Frames ticker admitidos pós-ACK | 0 | 0 |
| Motivo de abstinência | `snapshot_required` | `snapshot_required` |
| Duração | 1,671 s | 3,636 s |
| Quotes guardadas, ordens reais | 0 | 0 |

**Diagnóstico fundamentado:** a D413 corrigiu o abort prematuro dos 129 frames, permitindo observar um ACK real para BTC e N50, seguido de **um delta sem snapshot no estado interno**, o que gera `snapshot_required`. A lógica D386 descartava os frames recebidos antes do ACK; a Bybit V5 linear documenta snapshots + deltas, sendo omissões no delta continuidade dos valores anteriores. Os números são consistentes com snapshots iniciais chegando ANTES do ACK. **Não está provado** que cada frame pré-ACK seja snapshot íntegro: isso só é verificado pela execução e validação D414, jamais presumido. A falha é no bootstrap da janela inicial, não no TLS ou no envio do ACK.

## Correção de engenharia

No **mesmo** supervisor D386, sem outro coletor/journal:

1. Antes da confirmação, frames de tópicos estritamente pertencentes à assinatura ficam **em quarentena em memória da própria sessão**, com limites independentes de quantidade (D413: piso 128, 64/tópico, teto 4096), tamanho por frame (parser existente 16 KiB) e memória total (**8 MiB**). Nada é gravado, emitido ao callback, exposto ao monitor financeiro, incluído como tick pós-ACK ou persistido.
2. Se o ACK do `req_id` exato não vier, for rejeitado ou a conexão cair, o buffer morre com a sessão. Nenhum snapshot é confirmado, nenhum PAPER é atualizado.
3. Após o ACK **validado**, o sistema ingere os quadros em ordem de chegada, com os timestamps reais de recepção, no mesmo estado D385 já auditado, incluindo validação exata JSON, símbolo, sequência, relógio, snapshot obrigatório, preços, livro e duplicações. Se **qualquer** quadro da quarentena for inconsistente, toda a sessão termina fail-closed, o book é invalidado e nenhum quadro inicial vai ao PAPER.
4. Só **depois** de reconstruir todo o estado, os quadros seguintes ao ACK podem gerar callbacks / ticker aceito / cobertura e avaliação PAPER. Frames anteriores à confirmação não geram ordens, reservas, FILL, sinais ou prova de cobertura, mesmo quando são depois usados apenas para inicializar estado interno.
5. Reconexões criam outra quarentena e outro book vazio. É proibido reaproveitar snapshots ou sequências de socket anterior.

Para manter compatibilidade, `preack_frames_discarded` continua contando **frames pré-ACK que não foram encaminhados aos consumidores** (nome legado); o novo campo `preack_frames_bootstrapped_after_ack` identifica quantos deles foram validados como sequência inicial **somente depois** do ACK. Valores maiores que `preack_frames_discarded`, alegações de bootstrap sem ACK e importações adulteradas são rejeitados na interface J5. O app preserva leitura de arquivos D410 anteriores que não continham o campo.

## Aceite e testes

```sh
python -m unittest discover -s tests -p 'test_bybit_public_ticker_supervisor_d386.py' -v
python -m unittest discover -s tests -p 'test_bybit_public_ws_operational_probe_d405.py' -v
python -m unittest discover -s tests -p 'test_j5_paper_ws_health_d412.py' -v
```

Regressões D414 recriam os perfis observados: **7 pré-ACK + ACK + delta de BTC** e **263 pré-ACK + ACK + delta de BTC com 50 tópicos adicionais**, preservando campos omitidos em deltas. Verificam também falha na sequência pré-ACK, ACK ausente (nenhuma cotação), reconexão (nenhum bootstrap atravessa sessões), novo diagnóstico e limites. São testes offline com tráfego injetado, não medição de mercado.

## Próximo passo real e limite

A primeira prova de preço público verdadeiro exige refazer os mesmos **dois probes finitos**, com a versão D414 verificada e isolada do checkout owner, sem ligar PAPER ou serviço contínuo. Observar ACK, `preack_frames_bootstrapped_after_ack`, frames pós-ACK aceitos, cobertura, idade e razão se ainda falhar.

Se ainda ocorrer `snapshot_required`, não relaxar validação de sequências: investigar com diagnóstico estrutural anonimizante para distinguir quadro inicial `snapshot` ausente de mensagens parciais. A homologação J1 Top50 crypto-only, assinatura contínua WS/PAPER, slippage, funding e lucratividade não estão comprovadas por dois probes.

Fontes oficiais: https://bybit-exchange.github.io/docs/v5/websocket/public/ticker e https://bybit-exchange.github.io/docs/v5/ws/connect

Custo adicional R$ 0,00; nenhuma ordem real ou implantação VPS.
