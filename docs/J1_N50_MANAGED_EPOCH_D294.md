# J1/D294 — ciclo gerenciado N50 e renovação causal de epochs (OFF por padrão)

## Objetivo

D289 provou 50 contratos/1.250 candles/2h reais; D290–D292 criaram auditoria e recuperação na própria janela; D293 criou um **lock global** para impedir colisão entre censo D286 (~372 GETs) e writer M1 (~50 GETs). D294 adiciona ponto de entrada único `scripts.run_j1_n50_managed_once` que, numa invocação owner, decide entre iniciar/rotacionar manifesto N50 e executar uma hora incremental do **mesmo** M1. Nenhum segundo coletor ou sistema de ordens é implementado.

## Layout privado e estados

Raiz owner POSIX não-root 0700 preexistente: diretórios `lease/` e `epochs/` 0700. Dentro, o gerenciador mantém `.n50-manager.lock` 0600, ponteiro `n50-active-epoch.json` 0600, e diretórios imutáveis `epochs/epoch-<decision_utc_ms>/scope/` e `journal/` 0700, manifesto D287 0600. `lease/` usa o mesmo flock/claim D293 para *todas* as ações coordenadas. Não usar as saídas N2/D256/D264 ou tentar realocar bancos antigos. O ponteiro contém **somente** ID de epoch, digest de manifesto e observação UTC, sem nomes/valores privados; gravação via arquivo temporário 0600/fsync + rename atômico e fsync da pasta. Falha após escrita e antes do rename só permite reaproveitar staging com payload idêntico e owner válido.

- Sem ponteiro: exige raiz preparada e HH:01..HH:15; cria pasta de epoch **nova**, invoca uma única captura D286/D287 sob lease D293 e, somente após sucesso, publica o ponteiro.
- Ponteiro válido e idade menor que 36h: delega ao D293 `hourly_writer`, que usa D291/D292 e M1; não recria ranking/manifesto nem faz backfill de 24h se o cursor já existe.
- Ponteiro válido com idade de 36h ou mais: seleciona epoch **novo** e executa `capture_seal` em vez de coletar na mesma hora; ao obter novo manifesto validado, troca ponteiro de forma atômica. Todos os journals e manifestos anteriores permanecem íntegros e disponíveis para replay.
- Se ocorreu crash após captura/claim, mas antes da promoção, é possível adotar o manifesto privado já selado **somente no mesmo fechamento UTC e com claim D293 idêntica**; nunca confundir arquivo arbitrário com prova de captura. Falha de GET/quota, manifesto adulterado, HALT, hora incorreta, concorrência ou path inseguro não comuta o ponteiro. Uma interrupção de publicação na hora da rotação permanece explícita, sem fabricar PIT histórico.

## Segurança e escopo

Todos os sete opt-ins são exigidos: rede pública, storage privado, leitura privada do manifesto, auditoria read-only, escrita de manifesto, região/pesquisa pessoal e habilitação desta única execução. CLI:
`python -m scripts.run_j1_n50_managed_once --root-directory /RAIZ-PRIVADA-0700 --allow-public-network --allow-private-storage --allow-private-manifest-read --allow-private-readonly-audit --allow-private-manifest-write --confirm-region-and-personal-research --enable-managed-n50-tick`.

A CLI executa **uma** operação e termina. Não possui loop, daemon, cron ou systemd; **nenhum serviço é instalado ou iniciado nesta entrega**. A exclusão global cobre somente consumidores do mesmo lock D293. A inicialização da raiz, ativação de timer N50 e rollback seguem gate operacional separado (não afetar N2). Este ciclo ainda não certifica coleta N50 por 24h, atualização real permanente, identidade cripto independente, Top50 elegível ou ordens.

## Aceite e evidências exigidas

`tests/test_j1_n50_managed_cycle.py`: criação de epoch/pointer 0600; segunda hora incremental sem recaptura; rotação em 37h, expirado em 51h e preservação de originais; capture fail sem mover ponteiro; adoção de manifesto com claim real e recusa sem claim; corrupção de pointer; opt-in/owner/UTC; concorrência de duas chamadas. Reexecutar testes D287–D293, CI Linux/docs, Windows/offline e Chrome/PAPER no HEAD final; revisão, squash merge sem deploy. Próxima etapa: template de serviço/timer N50 **desligado** por default, preflight de coexistência N2 e gate de implantação supervisionada na VPS, seguido por soak real ≥24h antes de afirmar continuidade.
