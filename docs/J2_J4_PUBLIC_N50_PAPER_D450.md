# D449/D450 — fluxo público N50-capable até posições PAPER existentes

## Caminho funcional

A coordenação junta dois WebSockets públicos Bybit independentes no mesmo processo, preservando os validadores já existentes, sem recriar estratégias nem livros financeiros:

    WS público kline.60 (ACK confirmado)
      -> supervisor J2 / parser D434 -> SQLite dos closes da J2
      -> callback pós-append D450 -> coordenador D449
                                                |
    WS público tickers.* (ACK + snapshot/delta)  |
      -> supervisor D386/D385 -> callback D450 ---+
                                                |
                          -> primeiro: saídas existentes D391/D389
                          -> J2 D435 sobre 1..50 membros da mesma hora
                          -> força relativa vs BTC + intensidade de volume
                          -> D447 J3/PRE11/RiskGate -> OPEN PENDING AUTO2
                          -> estratégia D448 imutável, owner-only
                          -> nova cotação após latência -> FILL simulado AUTO2
                          -> posição/planos AUTO4 -> rota D425
                          -> monitor J4 D444/D445 e painel J5/D446

**Prioridade de saídas:** para cada cotação de uma posição registrada, o coordenador executa o roteador stop/targets/runner ANTES de considerar uma entrada. A falta de um dos 50 fechamentos impede novas oportunidades, mas não suspende o acompanhamento do ativo já mantido. Janela de hipótese limitada a 120s após fechamento. Kline não inventa entrada/fill: o ticker causal pode reservar intenção PAPER e só outro ticker posterior pode registrar um preenchimento explicitamente hipotético.

## Seleção, risco e configurações

Coorte de 1..50 contratos tipados, incluindo BTCUSDT, com closes síncronos no mesmo journal. Cada série é relida do SQLite já auditado. Só considera hipóteses D435 coerentes com a força relativa ao BTC; ordenação determinística por módulo da força relativa, razão de volume, turnover e símbolo. Não existe meta fixa de posições: cada abertura obedece aos limites vigentes, stop-health e kill-switch. 50 é o universo máximo inicial, não objetivo de posições.

A margem configurada é teto por posição. Decimal reduz quantidade ao múltiplo do passo hipotético; abster se desvio de margem for superior a 1 bp. Mudar leverage global altera somente novas posições. risk_for_quote e contract_for_quote são fontes tipadas explícitas de estado PAPER; nenhuma implementação presume saldo ou perda diária de conta igual a zero. AUTO2/AUTO8 sob transação são a autoridade local, sem validação de funding/liquidação da corretora.

## Continuidade e limites

- Candles J2 ficam no journal isolado; opening events + receipts no AUTO2; posições e reservas de stop/parciais no AUTO4. O manifesto D425 expõe posições ao monitor J4 e à consulta J5.
- Após reinício, entradas armadas PENDING podem ser retomadas; um FILL já gravado no AUTO2 reconstrói AUTO4/manifesto sem segundo evento. PENDING sem plano persistido falha fechado; não supor que parâmetros alterados representem o mesmo stop.
- Pasta PAPER: usuário POSIX não-root, modo 0700, journals 0600, sem symlink/hardlink e D425 flock; relatório sanitizado omite símbolos, preços e IDs.
- D450 permite sessão FINITA com dois sockets reais somente após opt-ins explícitos, ou sockets injetáveis com rótulo de replay offline. Nunca declara monitoramento 24x7 após seu término; não instala timer, serviço, VPS, ordem, credenciais, assinatura, J1, ou POST.
- **Ainda falta para operação autônoma:** provedor J2 independente de escopo N50 dinâmico por volume elegível; bootstrap 24h íntegro sem falsificar REST como WS; provedor durável do estado de risco PAPER; instalação autorizada com supervisão/watchdog e acesso privado no celular; avaliação J3 reproduzível walk-forward/OOS de taxas, funding, gaps e liquidação. Nenhuma rentabilidade ou segurança de 50x foi comprovada.

## Testes

- tests/test_j2_j4_public_paper_cycle_d449.py: coorte fixture de 50 contratos, 25 closes, seleção BTC-relative, OPEN -> FILL simulado posterior -> AUTO4 -> parcial e J5, restart sem duplicação, incompletude, staleness e inconsistência econômica.
- tests/test_j2_j4_dual_public_supervisor_d450.py: supervisores WS reais do código com sockets inteiramente INJETADOS, para 50 tópicos kline e 50 ticker concorrentes; ACK, callback pós-append, falta de fechamento e ausência de ordens.
- CI Linux/Windows/Chrome no SHA exato é exigência de integração; sockets fictícios não provam a fonte real da Bybit. Custo adicional R$0.


## D471 — reconexão de transporte no par público PAPER (21/11/2026)

A D450 anteriormente exigia `max_sessions=1` embora os supervisores J2 e D386 já suportassem reconexão limitada após `OSError/RuntimeError` do transporte. A CLI D453 agora permite `--public-ws-sessions 1..3`, padrão 3, simétrico para kline e ticker, mantendo o mesmo orçamento total da lease e os mesmos diários privados. Somente queda transportável é recuperada; ACK inválido, clocks impossíveis e dados corrompidos continuam falhando fechado. D467 interrompe o par apenas quando um supervisor termina degradado após esgotar as próprias tentativas; nenhuma vela ou preço é inventado. A regressão integrada simula 50 callbacks WS e desconexão de ticker seguida de novo ACK/BBO causal, com PAPER no diário e zero ordens reais. Essa alteração não diagnostica retroativamente a falha D466 nem prova funcionamento contínuo na VPS; ainda exige teste real pós-CI, sem release/J1/custos adicionais.
