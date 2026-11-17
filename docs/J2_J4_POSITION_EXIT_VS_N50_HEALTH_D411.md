# D411 — proteger posições existentes mesmo quando outro ativo do N50 está sem preço

## Problema financeiro corrigido

O gate de cobertura do D410, integrado previamente, condicionava **todas** as reservas hipotéticas de saídas PAPER a receber cotação válida e recente **dos cinquenta ativos**. Isso parecia prudente para um motor de **entradas**, mas criava um risco operacional desnecessário para posições já abertas: um altcoin silencioso poderia bloquear o stop de uma posição de BTC com preço perfeitamente válido.

**Decisão:** a qualidade da lista de oportunidades e a proteção de posições são dois controles diferentes.

- **Entradas e aprovação de oportunidades:** cobertura incompleta do Top50, lacunas e fontes não auditadas continuam proibindo qualquer declaração de prontidão, entrada automática ou lucro.
- **Saídas de posições PAPER existentes:** cada tick pós-ACK do **próprio ativo da posição**, causal, com livro positivo e idade máxima de 3.000 ms, pode chegar ao coordenador D389 e ser avaliado com **stop antes da parcial**. A ausência de cotações de instrumentos sem posição não suprime esse stop.
- **Sem preço confiável da própria posição:** nenhuma reserva, fill ou preço substituto é inventado; exigir nova amostra da posição.
- **Reconexão:** a D386 só entrega ticks após novo ACK e snapshot, D390 descarta a cobertura da sessão anterior e D391 conserva a monotonicidade de timestamps para impedir replay. O diário AUTO4 preserva reservas/UNKNOWN para reconciliação.
- **Saídas parciais de posição existente:** com cotação própria válida, continuam elegíveis ao coordenador após a verificação de stop. Não é motor de abertura e não equivale a negociação real.

D411 introduz um modo opt-in em D390, `require_fresh_held_position_for_paper=True`. A opção de pesquisa legada `require_complete_fresh_scope_for_paper` permanece isolada para não quebrar chamadas anteriores, **mas não deve ser usada para proteção PAPER operacional**. Ambas ao mesmo tempo são recusadas. D410 passa a usar **somente o novo modo**.

## Métricas e limites

O relatório separa `paper_coverage_gate.mode=fresh_held_position_quote_independent_of_n50`, `quote_frames_delivered_to_paper`, `quote_frames_deferred` e `unrelated_market_frames_ignored_for_paper`. A saúde do N50 continua no resumo independente: `finite_coverage_observed_once`, `finite_coverage_fresh_at_end`. Um N50 incompleto sinaliza `finite_paper_lease_degraded_or_incomplete`, **mesmo que uma reserva protetiva PAPER tenha sido corretamente persistida**.

A flag `universe_health_sufficient_for_new_entries` permanece sempre `false`: a leitura provisória owner não certifica elegibilidade, OOS ou segurança. Nenhuma ordem, stop nativo, FILL, posição de exchange ou resultado financeiro real é criado. Ainda não existe monitor 24×7 instalado.

## Cenários de aceitação

```sh
python -m unittest discover -s tests -p 'test_j2_j4_current_n50_paper_lease_d410.py' -v
python -m unittest discover -s tests -p 'test_bybit_public_ticker_optin_d390.py' -v
python -m unittest discover -s tests -p 'test_paper_intrahour_quote_router_d391.py' -v
```

A suíte usa os componentes originais e **o mesmo diário AUTO4** para demonstrar:
- cinquenta símbolos + uma posição externa ao N50 são assinados sem ranking alternativo;
- falta de um altcoin não impede uma parcial PAPER sobre BTC com preço válido;
- **zero** cotações do N50 não impede reservar o stop hipotético em BTC se o próprio BTC tem ticker válido e novo;
- ticker de BTC com atraso superior a 3 segundos não cria saída, mesmo que todo N50 esteja atualizado;
- reconciliação `UNKNOWN` e idempotência continuam válidas, e nenhuma ordem real é enviada.

## Implicações para J2/J4 e operação

Isso corrige o **modelo de isolamento de risco do produto**, não demonstra confiabilidade real da exchange. O usuário nunca deve depender do PAPER para proteção financeira de uma posição real. Próxima capacidade: receber ACK/ticks reais da Bybit no host autorizado, medição de heartbeat, rotatividade do Top 50, idade dos preços por posição, recuperação após falha e sinalização de dados degradados no celular. Antes de um serviço 24×7, verificar concorrência de writers e gate de instalação VPS. O acesso Python VPS segue sujeito à política do executor; não contornar.

Custo adicional: R$ 0,00; ordens reais: zero.

## Correção adicional: horário de recebimento não renova preço velho

A telemetria de cobertura D390/D405 anteriormente podia contar como **fresco** um frame recebido agora, mesmo que seu timestamp da exchange estivesse atrasado vários segundos. D411 passa a admitir no censo de contratos somente observações com `0 <= received_at_ms - exchange_at_ms <= 3.000`, além da origem causal, book positivo e escopo de época. O teste D405 injeta frame antigo recebido no instante atual e exige zero contratos observados/frescos, sem mascarar a latência elevada do histograma. Isso afeta diagnóstico de qualidade de mercado, não altera preços nem faz ordens.
