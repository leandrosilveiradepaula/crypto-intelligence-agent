# J2/J4 D410 — Top 50 atual + posições PAPER no mesmo feed, com bloqueio por cobertura

## Funcionalidade entregue em código

O adaptador `run_current_n50_paper_lease_once` liga os módulos existentes sem duplicá-los:

```text
Ponteiro owner J1 -> coorte N50 revalidada D406
                            |
                            +-- todas as posições explícitas do router AUTO4/D391
                            |
         Bybit V5 público D390/D386/D385 (ACK + snapshot/delta)
                            |
         Gate: N50 + posições com cotações frescas da MESMA sessão?
                       /                 \
                     NÃO                 SIM
                      |                   |
           não reservar PAPER    coordenador D389 stop ANTES do alvo
                                  |
                          journal financeiro AUTO4
                                  |
                    resumo sanitizado, sem fill presumido
```

**A principal mudança é o gate de cobertura completa e recente**, inexistente no fluxo opcional D401. No novo modo, uma cotação isolada que favorece uma parcial nunca cria reserva fictícia enquanto qualquer contrato do universo ou posição estiver sem cotação válida com book positivo **na sessão WebSocket atual**. Depois de desconexão, o gate reinicia; dados do socket anterior não contam. A janela máxima de frescor permanece a mesma da D385: 3.000 ms. Se um contrato ficar silencioso por mais tempo, o gate é fechado novamente até a cobertura voltar.

O monitor deriva automaticamente as posições de `paper_router.monitored_symbols`. Uma posição que esteja fora do Top50 é incluída nas assinaturas. O código lê o ponteiro J1 via D406 antes da sessão, com verificações PIT/catálogo/digests, e novamente após o fim para detectar rotação. Mudança entre leituras marca o resultado **degradado**; não apaga nem inventa FILL ou cancela unilateralmente reservas PAPER já persistidas.

## Gates e limites de segurança

- Cinco opt-ins booleanos **explícitos**: leitura owner J1, WebSocket público, pesquisa pessoal read-only, elegibilidade regional e autorização de **reservas de saída em diário PAPER sintético**. Sem eles, não lê o ponteiro owner nem abre rede nem tenta alterar o diário.
- Exige o router tipado D391 construído a partir de **posições AUTO4 existentes e explicitamente selecionadas**, com regras de stop/target e journal privado. Não há descoberta de carteira, criação automática de posição, habilitação de saldo financeiro ou exposição de credenciais.
- Sessão finita: máximo 60 segundos, até 100.000 frames e até duas tentativas de conexão. Padrão 20 segundos, 12.000 frames e uma sessão. Não roda em background e não instala systemd.
- Usa exclusivamente `wss://stream.bybit.com/v5/public/linear`, sem conta, REST privado ou endpoint de negociação. O socket pode usar transporte fake injetado apenas em testes. A resposta distingue explicitamente `data_mode=real_public_websocket` ou `injected_offline_fixture`, sem confundir fixture com feed real.
- O callback de PAPER preserva stop-first, idempotência de reservas, bloqueio por `UNKNOWN`, sem gerar fill a partir de preço e sem stop nativo da corretora.
- Resultados contêm apenas contagens, status, booleanos e nenhuma lista de símbolos, preços, IDs de posições ou conteúdo do diário privado. O status `finite_paper_lease_completed_with_fresh_scope` só é possível se **ao fim** houver cobertura fresca de todos os contratos e a época owner permanecer a mesma. Não significa proteção financeira ou continuidade após fechamento do lease.
- O modo legado D390 continua com o fluxo opt-in anterior. O novo parâmetro `require_complete_fresh_scope_for_paper=True` somente pode ser usado com `measure_public_coverage=True` e um router PAPER real; não muda o comportamento dos demais chamadores.

## Validação e evidências

```sh
python -m unittest discover -s tests -p 'test_j2_j4_current_n50_paper_lease_d410.py' -v
python -m unittest discover -s tests -p 'test_bybit_public_ticker_optin_d390.py' -v
python -m unittest discover -s tests -p 'test_paper_intrahour_quote_router_d391.py' -v
```

Testes isolados simulam **50 contratos da coorte e uma posição aberta fora dela** através do próprio receptor D390, com assinatura/ACK, validação de snapshots, gating por cobertura, reserva de primeira parcial no mesmo SQLite AUTO4, falta de um único contrato que impede a reserva, tick da posição antes da cobertura, mudança de época owner, recusa de autorização e ordens `UNKNOWN` que impedem duplicação. A prova offline não usa rede real nem simula entrada financeira validada.

## Próxima etapa necessária para uso operacional

Criar um operador de longa duração, somente depois de confirmar (i) ACK e ticks reais na VPS com o acesso autorizado, (ii) coorte owner íntegra, (iii) posições persistidas e políticas de stop carregadas com segurança, (iv) ciclo de rotação/renovação e heartbeat com alerta de stale e bloqueio de novas entradas. **Nenhum script deste incremento implanta, reinicia ou altera a VPS.** Um lease finito não equivale ao monitor 24×7.

Também não resolve o Top50 mercado-amplo crypto-only ainda não auditado, a auditoria SQLite J1 owner, slippage/funding/liquidação reais, walk-forward ou lucratividade.

Custo novo: R$ 0,00. Ordens reais: nenhuma.
