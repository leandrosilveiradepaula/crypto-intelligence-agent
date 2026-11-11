# J1 / D287 — coorte N50 atual, manifesto privado e journal isolado

## Objetivo e dependências

O D286 introduziu o censo atual de perpétuos lineares USDT, excluindo marcadores TradFi, calculando 24 candles 1h FECHADOS de todos os candidatos em uma janela UTC e gerando um ranking provisório de 50 por turnover USDT. Em 11/11 o catálogo tinha 370 candidatos técnicos, e apenas 44 dos 50 membros D264 antigos ainda apareciam. **Não usar os 50 históricos D264 como a coorte atual.**

O writer REST M1 já implementa GET público com 2 segundos de intervalo, no-retry, candles fechados, SQLite com transações, cursor por símbolo, digest, single-writer flock, fail-stop para erros permanentes e catchup de no máximo 48h. O timer instalado usa M1 N2 em produção e NÃO muda nesta PR.

D287 conecta a seleção **atual** de pesquisa D286 ao MESMO M1, sem duplicar o motor de persistência, sem atualizar retroativamente D256/D264 e sem conectar ordens.

## Contrato do manifesto selado

Módulo crypto_intelligence_agent/j1_auto_research_epoch.py valida relatório JSON completo e bem-sucedido de D286 (deve ser produzido com --include-public-symbols e armazenado privadamente com umask 077, arquivo 0600). Exige:
- status específico de ranking D286, dois catálogos iguais, 50 resultados, no mínimo 50 séries fechadas, pool técnica de 50..400, clock pre/post entre +1 e +15min após fechamento;
- SHA-256 sintaticamente válido do ranking e da pool; lista pública de 50 contratos de pesquisa sem duplicatas, símbolo malformado ou negativos TradFi documentados;
- flags de execução, Top50 global e identidade cripto independente **falsas**; fonte GET-only e volume rolling ticker desabilitado;
- manifesto composto de campos com schema exato, digest sobre todas as propriedades (tempos, digests, lista ordenada), e validade **máxima de 48h** após o catálogo.

Isso vincula **um relatório de pesquisa operado pelo owner** a uma coorte fixa, mas NÃO fornece assinatura independente do provedor nem certificação cripto. O hash identifica a identidade da coorte e protege contra alteração acidental dos arquivos; quem controla a conta owner pode gerar outro relatório. Se a coorte mudar, criar **novo journal/epoch**; jamais mutar members_json nem substituir o manifest existente.

## Execução

scripts/run_j1_current_ranked_epoch_once.py tem três operações opt-in:

- seal: lê SOMENTE arquivo de relatório D286 já existente, owner POSIX não-root, pasta e arquivo 0700/0600, JSON bounded com rejeição de chaves duplicadas/NaN, e grava UMA VEZ (O_EXCL/fsync, sem overwrite) o arquivo privado j1-auto-ranked-research-scope-v1.json em diretório 0700 distinto. Não faz GET nem SQLite write.
- capture-seal: **comando único preferencial** para executar o D286 atual diretamente em memória com `include_public_symbols=True` (IDs somente no processo), pedir todos os opt-ins públicos + escrita de manifesto, filtrar/ranquear todos os candidatos e selar N50 sem arquivo intermediário nem emitir símbolos em stdout. Pré-valida que diretório privado 0700 está vazio antes do primeiro GET e abandona sem criar arquivo em falha, drift ou quota. O trabalho de ~370 GETs requer a janela UTC D286 e não substitui o timer N2.
- run: requer manifesto owner-only, output directory privado 0700 **novo e separado**, quatro flags explícitas (rede pública, armazenamento privado, região/pesquisa, leitura privada). Invoca o EXISTENTE run_hourly_once com seleção 50 por manifesto. O _frontier original D264 continua inalterado como default do serviço N2, e o caminho alternativo só é atingido por schema D287 explícito. O banco M1 de pesquisa é criado no diretório de saída separado, nunca no journal N2 nem D256/D264.

Uma rodada nova recebe até **50 GETs / 1.200 candles 24h fechados**, com janela M1 HH:01..HH:15 UTC. A rodada seguinte recebe no máximo uma nova vela fechada por ativo, sem refazer as 24 horas; repetir a mesma decisão dá 0 GET e 0 novos candles. Conflitos de scope, relógio, quota/10006, escala, DB corrompido ou manifesto expirado causam abstenção, não substituição da identidade anterior. O timer N2 instalado continua funcionando enquanto o D287 é apenas ferramenta de pesquisa executada em journal isolado.

A fase **capture-seal** evita manipular arquivos de relatório: em uma única janela D286 ela cria o manifesto privado com os 50 nomes apenas internamente. A fase `seal` offline continua disponível para relatórios D286 já capturados como JSON owner 0600, sem nova rede. É necessário um censo corrente D286 futuro para o N50 dinâmico. O job D286 previamente agendado para 16:01:08 UTC usa a saída sanitizada SEM lista de símbolos: ele é uma prova de ranking e **não produz um manifesto D287**. Não presumir sucesso do job enquanto não houver resultado real registrado.

## Validação e segurança

tests/test_j1_auto_research_epoch.py verifica:
- build do manifesto D286 e binding SHA, símbolos desconhecidos/TradFi, duplicata, timestamps incoerentes, coorte fora de 50 e expiração 48h;
- arquivo privado 0600, uma criação, nenhuma sobrescrita, report original intocado, opt-in OFF sem IO, rejeição de symlink e adulteração antes de GET;
- writer M1 com fake público **50×24=1.200 candles**, rodada seguinte 50 candles, repetição idempotente com 0 GET, 2 checkpoints reais;
- tentativa de trocar manifesto/rank com o MESMO journal rejeitada antes de GET, exigindo novo epoch.
Todos cenários são offline, sem ordens, API privada, taxas ou instruções de trading.

Gates: CI Linux/docs, Windows/offline e Chrome/PAPER SHA final, revisão e squash merge **sem deploy**. Prova owner na VPS de testes offline/pureza sem substituir o serviço atual; um futuro ensaio N50 real exige manifest D286 obtido causalmente, diretório privado isolado, relógio seguro e avaliação de rate budget. #429/#319 seguem abertas até coortes dinâmicas com rotação segura, atualização contínua de 370 candidatos e homologação de Top50 corrente com PIT verdadeiro. Nenhum resultado financeiro assegurado.


## Evidência de execução real — D289, 11/11/2026

A separação entre seleção D286, manifesto D287 e writer M1 foi exercitada na VPS como proprietário `cia-probe`, sem instalar novo timer. O job `08212abda5374f658db32b95c25aafff` completou `capture-seal` entre 21:01:05 e 21:13:28 UTC, 372 GETs, manifesto owner 0600, 50 candidatos e scope digest `b022c1211b230e0be4503bed52858954c7deb68c60a03976e5cd74243f1335cb`. O job `5d207d7d4dd9463594a67abb3958308f` completou `exit=0`: 22:03 UTC = 1.200 velas iniciais/50 GETs; 23:03 UTC = 50 novas velas/50 GETs. Auditoria privada somente leitura confirmou 50 contratos, 1.250 velas, dois checkpoints UTC consecutivos, `status=pass` e nenhuma ordem.

A **prova N50 de duas horas está concluída**, sem duplicar o backfill. Não transformar este resultado em alegação de coleta N50 autônoma 24/7: a execução foi um job finito e o manifesto expira em até 48h. O serviço N2 recorrente anterior ficou intacto. Para #429 é necessária supervisão e renovação causal de epochs (novo journal a cada mudança de composição), com validação da continuidade por mais horas e gate próprio para eventual instalação; para #319 permanecem não certificadas a identidade independente e elegibilidade para negociação. Não autorizar ordens.
