# J1/D314 — coorte N50 dinâmica no WebSocket, sem depender de 52 contratos fixos

## Decisão

O piloto WS J1/OPS4 recebe `OfflineReviewedStreamScope` formado por um registro local `expanded-52`. O N50 D287, em contraste, sela **50 símbolos USDT perpétuos dinâmicos** ranqueados causalmente por 24 candles fechados de um universo provisório mais amplo. O escopo WS fixo não basta: se um dos 50 não aparecer entre os 52 cadastrados, D313 não gera prova 50/50, mesmo que os 50 tenham dados WS.

**D314 cria uma admissão de metadados separada e provisória**, derivada exatamente do manifesto D287, para alimentar as interfaces existentes `_topic_batches`, `parse_offline_confirmed_kline`, `SQLiteOfflineClosedStreamJournal` e `attest_n50_ws_hour_once`. Não altera nem enfraquece o antigo `OfflineReviewedStreamScope.from_scan` que continua exigindo o registro independente local.

## Contrato

`admit_dynamic_n50_ws_scope` é puro e offline: recebe o manifesto D287 com 50 nomes já selado, páginas `instruments-info?category=linear` fornecidas pelo chamador, cursores solicitados e timestamps efetivos de recepção. Não abre rede, nem socket, nem SQLite e não salva arquivos.

- Revalida D287 hash, hora UTC, TTL, flags de pesquisa e conjunto de 50 símbolos sem duplicação. Nenhum outro membro das páginas pode ser promovido para a assinatura WS.
- Admite apenas cadeia de paginação completa, até 4 páginas de no máximo 1.000 linhas (4.000 no total), com retCode0, resposta `category=linear`, horas de servidor não regressivas, cursores vinculados às páginas e terminal inequívoco. Timestamp deve ser causal ao `catalog_post_observed_at_ms` de D287 e não mais que 15 minutos posterior; cada página tem limite de 30 segundos de atraso do relógio servidor.
- Para cada **um dos 50 símbolos esperados**, exige linha única `LinearPerpetual/Trading`, `baseCoin+USDT` idêntico ao símbolo, `quoteCoin=settleCoin=USDT`, campos TradFi/region/underlying vazios, não pré-listagem, `deliveryTime="0"`, `launchTime` <= clock observado, leverage mínimo/máximo e `tickSize`/`qtyStep` em Decimal finito positivo. Ausência, duplicação, falha de um membro, símbolo de ações, futuro com entrega, revisão causal inválida ou janela expirada **bloqueiam tudo**.
- Cria um `OfflineReviewedStreamScope` interno com `registry_sha256` igual ao **digest da vinculação provisória de D287 + 50 metadados presentes**; essa SHA *não* significa registro independente de identidade nem fonte Bybit autenticada. O campo `source` declara o modo `bybit_v5_dynamic_n50_provisional_metadata_unverified`, não imita o contrato antigo reviewed. O objeto `DynamicN50WSAdmission.ws_scope` é restrito ao chamador privado; `sanitized_report()` contém só contagem/hashes/UTC/flags false, não nomes nem preços.
- Uma validação 50/50 posterior via D313 usa o mesmo escopo e o journal WS dedicado. Continua **não sendo PIT REST**, nem validação de 24h contínuas, elegibilidade global crypto-only independente (#319), troca de ordem ou prova de conexão real.

## Provas offline e gates de aceitação

`tests/test_j1_n50_ws_dynamic_scope_d314.py` deve provar: 50 membros variáveis do D287 passam no plano de tópicos do supervisor já existente; 50 `confirm=true` sintéticos geram D313 50/50 no SQLite de teste; duas páginas ordenadas coerentes; falha de uma linha, duplicate/cursor forjado, retCode, status não Trading, TradFi, região/underlying, prelisting, não USDT, futuro não perpétuo, unidade decimal ruim, skew, catálogo antigo/futuro e digest/flag D287 adulterados recusados; nenhuma rede/SQL produção/sistema/ordem. Regredir D313, WS supervisor, J1 D286-D294, Linux/docs, Windows/offline, Chrome/PAPER **no SHA final**, revisão e merge sem deploy.

## Limites necessários para concluir #585 / J1

1. **Coleta real das páginas fornecidas:** a interface D314 é offline e não reexecuta GET por conta própria. O chamador owner futuro deve usar apenas o cliente público Bybit existente com origem HTTPS fixa, orçamento, 10006 fail-closed, logs sanitizados e comparação causal dos digests, sem retentar a coleta por quota.
2. **Persistência owner exclusiva:** criar/ler escopo D314 e journal WS dedicado sob lock, DAC 0700/0600, nunca sobrescrever REST antigo. O supervisor WS já tem ACK/heartbeat/reconexão limitada; futura integração precisa iniciar o lease antes do fechamento, manter fonte explícita e publicar somente 50/50 por hora. Se houver gap, sinalizar e somente reconciliar via REST com quota e proveniência própria.
3. **Deploy/root separado:** N50 REST está desativado por 10006 desde 16:01 UTC 12/11; N2 fallback ativo. D312 preparou auditor do HALT e release OFF por padrão, sem ainda receber permissão root/DAC para implantação. D314 não muda systemd. 24 PITs reais, rotação >=36h e #319 exigem provas distintas.

**Custo:** R$0 adicional, sem ordens e sem serviços externos pagos.
