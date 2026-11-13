# J5/APP-DATA1 — exportação N50 local para o aplicativo mobile

## Problema resolvido
O console J5/MVP1 `web/app/index.html` consegue importar `j5-n50-ws-log-progress-v1`, mas os relatórios N50 da VPS ficam no journal de serviço `cia-j1-n50-ws.service`. O exportador `scripts/export_j5_n50_ws_journald_once.py` traduz **somente** a saída JSON sanitizada do journald para esse schema, sem duplicar o cálculo de janela de 24h (usa o projetor J5/PROGRESS1 existente).

## Leitura separada, não publicação
O script só lê bytes NDJSON de **stdin** após `--allow-sanitized-journald-stdin`; nunca chama `journalctl`, abre arquivo de dados privados, acessa SQLite, mexe em `systemctl`, consulta a rede ou envia ordens. Verifica por linha `_SYSTEMD_UNIT=cia-j1-n50-ws.service`, `__REALTIME_TIMESTAMP` (µs, UTC), `MESSAGE` JSON do `j1-n50-ws-cached-owner-window-v1`. Ignora textos de systemd e outras mensagens de schema, mas falha fechado em relato da hora com campos/contagens inválidos. Tamanho total <=1MiB, até 4096 linhas, cada `MESSAGE` <=8KiB. JSON aceita apenas chaves únicas e não aceita NaN/Inf. O pipeline deve ser executado quando a última hora estiver liquidada (+3 minutos UTC), com privilégio previamente autorizado para ler logs. Saída são apenas 24 slots e contagens, nunca símbolos, preços, SHA privado ou caminhos.

Exemplo de uso **posterior**, quando o código estiver instalado no checkout autorizado da VPS e o titular liberar o acesso aos logs (não executar apenas com base no merge GitHub):

```bash
journalctl -u cia-j1-n50-ws.service \
  --since "26 hours ago" --output=json --no-pager |
python -m scripts.export_j5_n50_ws_journald_once \
  --allow-sanitized-journald-stdin > n50-progress.json
```

Importar `n50-progress.json` diretamente em **Configurações > Selecionar arquivo JSON local** no aplicativo J5. A importação é voluntária, não transmitida nem persistida pela tela. Nenhum endpoint público foi criado. Se houver gaps, 50 appends com auditoria abstida não são horas 50/50; duplicatas não pontuam. `owner_d323_24h_audit_verified=false` mesmo que 24 relatórios indiquem sucesso: o journal SQLite privado e a continuidade real exigem o gate owner D323 separado. A fonte do journald não é autenticada como corretora e não promove sinais/ordens.

## Testes e aceite
`tests/test_j5_n50_ws_journald_export.py`: dois fechamentos 50/50, 50 appends mas auditoria falha, duplicata, evento futuro/janela prematura, campo não string/booleans, SHA e preço privados que não são emitidos, JSON malformado/duplicado, limite 1MiB/4096, opt-in antes de ler stdin, ausência de rede/banco, equivalência do JSON ao schema aceito pelo console. CI Linux/docs, Windows/offline e PAPER/mobile no SHA revisado; merge sem deploy. Sem alterar sistema de coleta J1 nem fazer release na VPS. Issue #628, parent J5 #6, custo adicional R$0.
