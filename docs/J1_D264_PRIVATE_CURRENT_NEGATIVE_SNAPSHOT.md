# J1 D264 — snapshot privado imutável dos vetos atuais e replay offline

## Contexto validado

Owner VPS D263 (08/11/2026 01:03 UTC): 8/8 testes PASS, `main=1bef59b646bee6b429a5c670beb453b67784f8c3`, 930 linhas de catálogo, 822 contratos básicos atuais e congelados (0 mudanças de membros), 297 com indícios TradFi de metadados da Bybit, 525 sem tais indícios mas **não certificados cripto**, 24 negativos documentais dos quais 3 sem indicador atual. Uma única consulta GET, 0 writes/ordens. A resposta tinha apenas contagens; **os 297 símbolos não são recuperáveis da saída D263**. O corte histórico de 819×24 candles é 06/11/2026 13:00 UTC, digests preservados e 3 séries curtas.

## Nova evidência D264

Uma **nova** consulta atual de metadados deve ser explicitamente autorizada na VPS (não reaproveitar contagens como se fossem dados). O `--save-private-snapshot` de `scripts.audit_j1_bybit_current_metadata_negative` acrescenta salvamento privado, não habilitado por padrão; preserva os gates non-root, lock, replay D256, um único GET com client oficial, relógio, sem cursor, sem retry, allowlist de contratos. Depois da validação completa, cria arquivo privado `d264-bybit-current-metadata-negative-v1.json` no mesmo diretório 0700, modo 0600, publicação atômica no-clobber, sem expor nomes no stdout. Conteúdo mínimo: corte congelado, timestamps reais da **nova** resposta, contagem e digest de membros, lista dos símbolos com indicador TradFi (NEGATIVO, contemporâneo), lista de campos ausentes, flags falsas e hash do JSON canônico; não há preço, candles, símbolo em log público, payload bruto ou credencial. Se o catálogo mudou (churn), o snapshot de sobreposição idêntica abstém sem gravar. Se arquivo já existe, interrupção ANTES do GET.

**Replay** `python -m scripts.j1_d264_private_metadata_snapshot` lê só o SQLite privado D256 e snapshot local 0600, valida hash, schema, tempo, escopo, 819 somas Decimal e digest bruto; excluir símbolos indicados como TradFi **agora** mais negativos documentais D259 apenas de uma nova **fila exploratória retrospectiva** de até 50. A fila NÃO é Top50 cripto de 06/11, não é identidade positiva, não possui PIT autenticado e NÃO permite negociação. Default relatório só contagens e hashes; `--include-private-symbols` lista identificadores apenas no terminal privado owner (não publicar em GitHub). Datas atuais não podem ser retrodatadas. O catálogo negativo não é comprovadamente exaustivo.

## Validação e operação

Exigir CI Linux/docs, Windows/offline e Chrome/PAPER no HEAD exato, revisão e merge sem produção. Prova na VPS requer checkout clean FF-only no SHA do merge, testes focais e operador `cia-probe` non-root.

Primeiro, replay estritamente offline sem rede, se houver arquivo existente:

```bash
/home/cia-probe/agent/ws-venv/bin/python -m scripts.j1_d264_private_metadata_snapshot \
  --directory /home/cia-probe/agent/j1-global-closed24h-private/run
```

A captura nova é **um único GET adicional, por decisão owner**, não automática:

```bash
/home/cia-probe/agent/ws-venv/bin/python -m scripts.audit_j1_bybit_current_metadata_negative \
  --directory /home/cia-probe/agent/j1-global-closed24h-private/run \
  --allow-public-network \
  --confirm-region-and-personal-research \
  --save-private-snapshot
```

Em caso de sucesso, rodar replay sem flags de rede. Qualquer abstain, clock drift, 10006/429/403/451, cursor ou arquivo existente => não repetir a operação. Este código não altera `j1-marketwide-closed24h.sqlite` e não migra o banco histórico privado 0600. Não instalar timer, alterar infraestrutura, publicar símbolos, credenciais nem enviar ordens. Próximas entregas #319 (fontes independentes sobre as 50 hipóteses) e #429 (coleta contínua com supervisor).

## Limitação relevante

A D263 não reteve o catálogo da execução anterior; o arquivo D264 resultará de nova observação, com data real posterior. O hash assegura integridade local e NÃO autentica o provedor nem certifica identidade cripto. O replay apenas prioriza revisão humana/independente dos 50 contratos; mercados TradFi não documentados ou símbolos de ticker colidido continuam sem aprovação.
