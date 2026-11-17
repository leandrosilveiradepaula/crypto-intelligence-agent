# J2 / D396 — prova finita de cobertura N50 e posições durante rotação

## Por que esta entrega existe

D385 valida o ticker Bybit V5 público, D386 supervisiona uma sessão
WebSocket curta com ACK, reconexão e heartbeat, e D390 reutiliza o
transporte de rede existente mediante opt-in. Entretanto, **receber
ACK e algumas cotações não comprova cobertura dos 50 contratos**.
Sem essa prova, um futuro monitor contínuo pode parecer saudável
enquanto deixa posições sem preço.

D396 compõe D385 e D386, sem novo coletor ou segunda biblioteca,
em até quatro **leases finitas** de cobertura. O usuário ou
orquestrador deve fornecer, de forma independente, a relação
`ranked_symbols` e `position_symbols` para cada época PIT.

## Prova executável offline

```bash
python -m scripts.demo_public_n50_coverage_d396
python -m unittest discover -s tests -p 'test_bybit_public_ticker_coverage_d396.py' -v
```

O comando cria dois universos **sintéticos** de 50 contratos
cada. Na segunda época, um símbolo sai do ranking e outro entra;
o contrato excluído continua como posição aberta, junto a um
segundo contrato que já estava fora do Top50. Portanto, o
monitor passa de 51 para 52 assinaturas. Cada sessão emite
um ACK sintético + um snapshot válido para cada assinatura,
utilizando D386 com uma fábrica de sessão fake, sem internet.
O relatório mostra contagens de 50/50 por época,
2/2 posições monitoradas, 1 troca de ranking, snapshot
válido e frescor dos contratos no fim de cada lease.

**Não são 50 ativos reais verificados, nem prova de que a
Bybit enviou essas mensagens.** IDs de símbolos e preços
não entram no relatório; apenas contagens e SHA256 da
composição do escopo. O digest não autentica a corretora.

## Gate conservador de cobertura

Para cada época, a função
`run_finite_public_ticker_coverage_pilot` exige:
- exatamente 50 contratos ranqueados tipados, lista de
  posições abertas e timestamp PIT crescente;
- proíbe desaparecer com uma posição previamente aberta
  sem uma prova externa de fechamento/reconciliação
  (essa prova ainda não faz parte do piloto);
- assinatura ACK válida e snapshots aceitos por D385;
- timestamp de exchange **não anterior ao PIT admitido**
  e **não posterior ao recebimento local**; caso contrário,
  interromper a lease, mesmo que o D385 tolere pequenos
  desvios de relógio de rede;
- **uma cotação utilizável, com BBO positivo, por
  instrumento ranqueado E por posição aberta**, inclusive
  posições fora do ranking;
- ao encerrar a sessão, todas as cotações ainda precisam
  estar dentro do orçamento de frescor configurado
  no D385; não basta ter recebido todos os símbolos
  antes de uma queda de conexão;
- sessão D386 completada sem erro de validação, de
  heartbeat, de reconexão ou de orçamento.

Em qualquer falha, interrompe o restante do ciclo e
retorna `abstained_incomplete_coverage`, sem gerar
preços faltantes nem presumir que os próximos membros
substituem os anteriores. Leases desconectam e invalidam
o cache entre épocas; novos snapshots são obrigatórios.

A diferença entre tempo de exchange e recebimento é
apresentada como **faixas dos percentis P95 e P99
do histograma existente no D386**, nunca como números
exatos em milissegundos. Sem buffer de preços ou amostras
ilimitadas; máximo de quatro épocas, 60 segundos, 100 mil
frames e limite de sessões do D386 em cada etapa.

## Testes negativos e de estresse local

Testes offline cobrem: ACK sem dados; 50 ativos do
ranking sem a posição fora dele; 90 mensagens repetidas
do mesmo símbolo; profundidade BBO zero; desconexão e
reconexão com snapshots insuficientes; símbolo de fora
da inscrição; relógio PIT retroativo/futuro; perda de
posição sem reconciliação; orçamento inválido; P95 por
faixa; e comando real executado via subprocesso.

## O que permanece pendente

- Origem real autenticada da lista PIT de 50 e elegibilidade
  crypto-only Bybit. **O sufixo USDT não é prova por si só.**
- Medir throughput, CPU, memória, backlog, gaps e p95/p99
  de dados de rede reais com serviço isolado e tempo
  suficiente na VPS, sem duplicar J1.
- Adaptar assinaturas durante uma sessão longa ou rotacionar
  sessões com orçamento de indisponibilidade medido; D396
  só valida leases finitas, não 24×7.
- Integrar o feed prospectivo ao callback PAPER J4/D395,
  observando stop, saldo, falhas e custos com cautela.
- Conciliação da J1 após D384 sob #671; não alterar os
  timers, o processo owner, cache N50 ou SQLite privado.
- Qualquer piloto na VPS com rede pública exige gate
  operacional separado. Este commit não publica serviços
  nem consulta REST/WS real.

O status `finite_samples_observed_not_continuous`
**nunca** significa `continuous_24x7_verified`,
`marketwide_top50_verified` ou autorização para enviar
ordens de corretora. A fonte de valores no teste é
`SYNTHETIC`, sem custo adicional.
