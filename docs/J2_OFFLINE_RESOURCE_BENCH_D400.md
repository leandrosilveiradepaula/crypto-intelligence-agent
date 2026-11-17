# J2 / D400 — orçamento de CPU e memória no replay N50 inteiramente offline

Issue #677. Complementa D396 sem duplicar o supervisor D386, o seletor PIT ou o ledger J1. Mede o custo **do fluxo Python de validação existente** em duas épocas de 50 instrumentos, incluindo posição fora do ranking (51/52 assinaturas), repetido de 1 a 20 vezes. Não cria API, socket, serviço, coletor, conta, credencial, ordem, chave ou preço persistido.

```bash
python -m scripts.benchmark_public_n50_resources_d400 --runs 5
python -m unittest discover -s tests -p 'test_benchmark_public_n50_resources_d400.py' -v
```

Saída JSON sanitizada: quantidade de runs, épocas, frames sintéticos aceitos, duração monotônica, tempo CPU do processo, pico alocado por tracemalloc e frames/s do benchmark **local sintético**. O temporizador de wall-clock não é relógio da corretora; tracemalloc **não** mede RSS do SO, runtime de socket ou consumo total da VPS. A ordem de grandeza de throughput em CI não é SLA. Nenhum limite absoluto/threshold de produção é inferido de runners compartilhados.

A operação falha se a coorte D396 deixar de ter cobertura íntegra. Os gates negativos permanecem false: `real_network_latency_or_load_verified`, `continuous_24x7_verified`, `marketwide_top50_verified`, `orders_sent`, `order_submission_enabled`, `approved_for_live_use`. Sem prova real de recursos, nenhum piloto 24/7 está autorizado.

**Próximo avanço da issue #677:** piloto isolado read-only com aprovação operacional específica, medindo memória RSS, CPU, frames recebidos/dropped, idade e reconexões reais para 50 instrumentos e posições fora do ranking, sem tocar journal, WS horário ou timers J1. A auditoria J1 #671 permanece independente.
