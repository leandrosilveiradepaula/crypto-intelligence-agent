# J1/D285 — auditoria de 1 a 50 contratos REST, sem novo coletor

## Motivação

A VPS executa desde D284 o timer horário recorrente no M1 com 2 contratos. O worker M1 EXISTENTE já aceita até 50, mas a auditoria owner-only de readiness exigia exatamente 2. O objetivo desta entrega é retirar o hardcode da **auditoria**, não trocar o banco, instalar worker novo ou habilitar ordens.

## Contrato

- A mesma auditoria aceita expected_members=1..50, default 2 para retrocompatibilidade; CLI opt-in permite --expected-members 50.
- Owner POSIX, pasta 0700, arquivo 0600, SQLite URI mode=ro/query_only/BEGIN, integrity_check, cursor, digest de TODOS os candles e checkpoints UTC reais permanecem obrigatórios.
- Após replay, somar exatamente 24 velas 1h fechadas por ativo, em Decimal de quote_turnover USDT. Ranqueia por volume decrescente e símbolo em empates. Retorna apenas contagem, digest de ranking e timestamp do fechamento, sem símbolos, preços, acesso privado, rede ou escrita.
- Flags fixas: rank_is_sample_only_not_marketwide=true, activation_authorized=false, continuous_collector_verified=false, marketwide_top50_verified=false, orders_sent=false.
- Nunca recriar publicações perdidas: as horas faltantes no histórico são registradas separadamente dos candles íntegros.
- Escopo M1 é IMUTÁVEL por digest/membros. Mudar serviço instalado 2→50 no mesmo DB rejeita a operação. O ensaio N50 precisa de **outro diretório e outro journal**, sem alterar o serviço/timer N2.

## Testes e prova

Fixtures SQLite real de 50 membros com 50 candles por símbolo (2500 linhas), 26 checkpoints e 1 lacuna de publicação: replay positivo e digest determinístico, inclusive rejeição por contagem divergente, universo adulterado ou expected_members fora de 1..50. Testes existentes do N2 permanecem válidos.

O CLI M1 já existente pode testar **uma vez** 50 contratos escolhidos pelo frontier D264 congelado, com max-assets 50 e três opt-ins explícitos de rede, storage e região, usando diretório privado NOVO. Primeira rodada chega a 1200 candles em até 50 GETs, excluindo downloads completos de 720h. O auditor D285 então verifica as 24h e o ranking **dessa amostra PINADA**.

AVISO: esse frontier D264 não é o pool atual D279 de 370 candidatos, e seu ranking NÃO representa o Top50 atual. A próxima entrega de #319/#429 é o epoch dinâmico, selecionado por metadados atuais e pelo turnover **atual**, com histórico preservado. Nenhuma ordem real, trading ou ampliação automática da unidade de produção.

## Gates

CI Linux/Windows/Chrome no SHA final, revisão e merge sem deploy; validar N2 read-only na VPS. Ensaio isolado N50 somente sob o mesmo owner não root e janela UTC M1, e sem concorrer com a coleta periódica N2. Falhas do provedor devem preservar journal parcial para auditoria; nunca limpar ou retroagir PIT.
