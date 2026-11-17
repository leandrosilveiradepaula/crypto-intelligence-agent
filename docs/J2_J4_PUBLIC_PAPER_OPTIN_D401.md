# J2/J4 D401 — conector Bybit público opt-in ligado ao ledger PAPER

## Resultado
O conector D390 já obtinha cotações Bybit V5 public linear por uma sessão finita mediante três autorizações de rede existentes, mas descartava os eventos no encerramento: nenhuma gestão PAPER recebia esses preços. D401 acrescenta parâmetro opcional **tipado** `paper_router: PaperIntrahourQuoteRouter`, usando exclusivamente o callback e o reset de sessão D386/D400.

- O D385 recebe snapshots/deltas públicos e valida fonte, sequência, BBO e relógios; D386 só notifica o consumidor **depois do ACK**.
- O D391 decide stops/alvos/trailing PAPER via AUTO4, sem ordem de exchange e sem FILL implícito. Um evento pode criar no máximo intenção fictícia sujeita à idempotência já persistida.
- O D400 zera o baseline efêmero de cross-sequence a cada tentativa de conexão, mas preserva o relógio monotônico por símbolo e as reservas existentes.
- A lista de posições do roteador DEVE estar contida nos símbolos efetivamente assinados (ranking + posições fora do ranking) antes que qualquer socket seja construído. Membros ausentes abortam com `DataValidationError`, sem transporte.
- A saída agrega `paper_monitoring` sanitizado apenas quando `paper_router` é fornecido; nunca IDs de posição, símbolos, preços ou credenciais. Por padrão, D390 não muda o comportamento nem cria journal.
- Os três gates públicos existentes são obrigatórios mesmo com socket injetado; nenhuma rede é aberta na CI. Budget de lease finita D386 continua sendo aplicado. Uma lease concluída não valida cobertura N50 e não cria serviço 24×7.

## Teste offline
```bash
python -m unittest discover -s tests -p 'test_paper_intrahour_quote_router_d391.py' -v
python -m unittest discover -s tests -p 'test_bybit_public_ticker_optin_d390.py' -v
```
A regressão integrada D401 passa pelo mesmo código D390→D386→D385→D391 e verifica ACK, reserva fictícia após ticker, nenhum fill implícito, relatório sanitizado e veto antes do socket quando a posição não está na subscrição. Gates CI Linux, Windows e PAPER/Chrome no SHA da PR.

## Limites e próximas ações
O teste sintetiza os frames. **Não confirma preço, liquidez, cobertura, latência ou disponibilidade real da Bybit.** O feed D390 é finito e não deve ser usado para proteção produtiva ou promessa de stop: reconectar e acompanhar posições 24×7 exige operador independente com observabilidade, checklist, piloto VPS isolado e autorização específica de release. A J1 #671 e seu único escritor SQLite não são afetados. Nenhuma ordem real, testnet, credencial, publicação, migration ou custo.
