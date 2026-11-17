# Prova funcional — do feed público ao motor de saídas PAPER

Este é um teste **executável e integrado da ferramenta**, não apenas uma validação de arquivos. O operador pode executar um comando único que atravessa o adaptador público Bybit D390 (com transporte sintético injetado), a validação de dados D385/D386, a recuperação de sessão D400, o gestor automático J4 D391, e o diário transacional AUTO4.

## Como reproduzir

```bash
python -m scripts.run_paper_public_adapter_proof_d402 --scenario closed
python -m scripts.run_paper_public_adapter_proof_d402 --scenario unknown
```

Ambos geram JSON sanitizado na saída padrão. Nenhum acesso à Internet ou Bybit é feito; os dados e os fills declarados são **fixtures sintéticas**, com arquivo SQLite temporário removido no final.

No cenário `closed` a posição PAPER abre com 100 unidades confirmadas fictícias. Um ticker da sessão das 10h12 reserva parcial de 30, depois um **FILL explicitamente fictício** libera o saldo. Na sessão reconectada de 10h19 a segunda parcial de 20 é reservada, seguida de outro FILL fictício. Às 10h27, um ticker adverso solicita STOP PAPER para as 50 restantes, e o teste injeta o terceiro FILL fictício. Ao ler o SQLite de novo, verifica 100 unidades preenchidas, nenhuma reserva nem saldo aberto.

No cenário `unknown`, a primeira reserva de 30 permanece UNKNOWN: a nova cotação de alvo das 10h19 e a cotação adversa de 10h27 **não** emitem novas reduções. O saldo confirmado continua em 100, com reserva bloqueada em 30 e reconciliação obrigatória. Não se supõe que o stop foi realmente colocado na Bybit.

A saída traz sequência de decisões, reservas, quantidades e estado final, sem símbolos reais, valores de mercado privados, conta, credenciais ou IDs de posição. Exige JSON com `orders_sent=false`, `real_market_connected=false`, `real_fills_verified=false` e `approved_for_live_use=false`.

## O que melhora na ferramenta

É possível verificar que um único fluxo lógico atende **recepção de preço → decisão automatizada → reserva idempotente → gestão após fills explícitos → stop ou bloqueio seguro**, inclusive quando as mensagens chegam de sessões públicas independentes. O diário existente permanece a única contabilidade PAPER. A execução não exige candle horário seguinte para gerir a posição.

Isso não é robô operando ao vivo: ainda falta instalar e medir feed público contínuo 24×7, observar eventos reais na VPS, conciliar posições e risco com fontes autorizadas, montar interface operacional de posições e só depois avaliar testnet/live mediante gates específicos. Nenhum serviço J1, arquivo privado ou dinheiro é alterado.

## Testes automáticos

```bash
python -m unittest discover -s tests -p 'test_paper_public_adapter_proof_d402.py' -v
```

Cobrem fechamento, UNKNOWN, nenhuma rede, restrições financeiras e execução real do comando. CI Linux/Windows/navegador no commit revisado antes de integração.
