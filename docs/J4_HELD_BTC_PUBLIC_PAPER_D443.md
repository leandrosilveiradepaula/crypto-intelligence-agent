# D443 — acompanhamento de posição PAPER persistida por ticker Bybit (sem J1)

## Resultado funcional e reaproveitamento

D442 demonstra um cenário efêmero de abertura fictícia → custos J3 → stop/target AUTO4. A posição fictícia desaparece ao terminar o ensaio. D443 oferece o complemento necessário: receber um preço público e acionar o **mesmo AUTO4 em uma posição PAPER previamente persistida**. Não cria segundo banco ou motor: D425 carrega as rotas da posição e obtém o lock de exclusividade AUTO4; D441 valida o contrato público BTCUSDT; D390/D385/D386 avaliam o ticker; D391/D389 reservam REDUCE_ONLY por stop/target e exigem fill explícito do ledger para alterar a quantidade confirmada. O **arquivo existente** da posição é preservado, não descartado.

## Separação e segurança

- NENHUMA leitura, importação operacional de estado, cron ou alteração de J1; o contrato BTCUSDT vem de um REST público independente e apenas da versão de pesquisa (não certifica elegibilidade N50).
- Modo real somente POSIX não-root, owner da pasta 0700, manifesto de rota D425 0600, lock do journal durante toda a sessão. Cinco opt-ins: rede pública, WS, pesquisa pessoal, elegibilidade regional e reservas PAPER no diário privado existente. Lock conflitado, rota diferente de BTCUSDT, status/qualidade inconsistente ou dado stale falha fechado, sem duplicar ordens.
- Sessão finita de até 60s, uma conexão, no máximo 100.000 frames; não prova supervisão 24×7. Falta de cotação fresca do contrato mantido causa abstenção mesmo com ACK, e quaisquer cotações pré-ACK não são entregues para PAPER.
- Em replay hermético com factory/scope/router injetados, reporta `injected_offline_protocol_replay` e não alega coleta pública. Em modo real são proibidas injeções de sessão, clock, owner e escopo.
- Nunca cria posição, fill automático, ordem de corretora, canal privado, credencial, sinal J2 aprovado, lucro financeiro, proteção nativa ou autorização live. Custo adicional R$0.

## Evidência e sequência funcional

Teste D443: usa **real SQLite AUTO4 persistido no diretório de testes**, com um fill inicial explicitamente fabricado antes do lease. Depois ACK e ticker de alvo → reserva de 30 unidades (sem filled units), ou ticker de stop → reserva protetiva 100 unidades. Reinicia roteador sobre o **mesmo arquivo**, envia o preço de alvo novamente e confirma uma única reserva. Também valida nenhum evento após apenas ACK e portas fechadas sem opt-in. Não precisa ranking, cache N50, nem uma nova coleta da J1.

## Pendências antes de produto pronto

Para acompanhar posições durante toda a vida útil: feed público N50 e contratos retidos fora do N50, controle de rotação e recomposição de snapshots, serviço owner de ciclo longo, watchdog e alertas J5/J6, fills PAPER causais, financiamento/risco/liquidação venue e walk-forward OOS validados na J3. A presente entrega não executa ordens, não assegura um stop real e não substitui esses gates.

### Comando de operador futuro (não executar em produção sem gate)

Há uma CLI sem instalação de serviço: `python -m scripts.run_j4_held_btc_paper_d443_once --private-paper-directory PASTA_PAPER_0700 --seconds 30 --max-frames 20000 --allow-public-network --allow-public-websocket --confirm-personal-readonly-research --confirm-region-eligible --allow-private-paper-reservations`. Requer manifesto D425 + journal persistente da própria posição PAPER e usuário owner POSIX não-root. A ausência de qualquer opt-in aborta antes de ler o journal ou abrir socket. O custo/slippage/risk-Gate de novas entradas permanece independente: D443 **não bloqueia stops/saídas de posição existente** porque um teste de entrada J3 ficou negativo.

O status de pesquisa ao fim do lease NÃO significa que a posição PAPER esteja protegida depois que o processo terminou. Reportar último lease encerrado, não um supervisor ativo.
