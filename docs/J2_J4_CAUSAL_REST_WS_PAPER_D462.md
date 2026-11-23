# D462 — J2/J4: aquecimento histórico REST e fechamento causal por WebSocket

## Entrega no produto

O operador PAPER pode usar **24 horas históricas REST** antes do último candle de uma hora **confirmado e anexado pelo WebSocket público da Bybit**. O histórico preserva a qualidade `bybit_public_rest_historical_closed_unverified`; a última vela preserva `bybit_public_ws_confirmed_unverified`. São **25 velas por símbolo** na análise corrente; 24 para aquecimento e a 25ª para avaliação causal. Esse requisito é intencional: o motor D435 exige 24 barras anteriores para computar referências e confrontar o rompimento posterior. Não se misturam fontes num único diário inventado.

Fluxo implementado na mesma branch J2/J4/J6:

1. Seleção N50 pública conservadora e dinâmica por turnover24h, incluindo BTC contexto (D451).
2. **Opt-in explícito `--auto-capture-rest-warmup`**: D461 recupera/valida um snapshot histórico imutável de 50×24 candles do UTC hour corrente; cada GET é público, limitado, sem ordens, com pacing conservador. Não inicia nova captura se faltarem menos de 180 segundos para a próxima virada horária. Quem já possui snapshot pode fornecer `--rest-warmup-filename`; os dois modos não podem ser usados juntos.
3. O WebSocket `kline.60` deve enviar `confirm:true` **após o ACK**. O supervisor D450 valida clocks/OHLCV e anexa 1 evento por símbolo ao diário WS SQLite D451. `tickers` tem canal separado e fornece BBO real para o motor PAPER, sem negociação automática.
4. D462 lê, em modo owner-only, o snapshot REST inteiro com hash e o **evento exato** do journal WS com hash, registro da coorte, trade/server/received clocks e instante de abertura. Exige janela contígua, mesmo fingerprint N50, snapshot anterior à confirmação e campos econômicos não alterados. A série resultante leva digest combinado de proveniência.
5. D435 avalia a série mista somente sob `allow_causal_rest_ws_warmup=True`. D449/D447 exigem o mesmo opt-in, coorte completa e convergência de horários, análise relativa ao BTC e filtros econômicos PRE11/RiskGate para qualquer possível abertura **PAPER**. Histórico REST puro permanece incapaz de criar abertura ou falsa confirmação WS.
6. O relatório da sessão passa a conter o número exato de candles REST validados (até 1.200), SHA-256 e UTC da janela, mais contagens de closes aceitos pelo WS e estado das posições PAPER. O candidate systemd da VPS continua **desativado**, com o parâmetro de aquecimento automático pronto para instalação após gate de release.

## Evidência e limites

- Evidência **real** já existente D461: 50 contratos públicos e 1.200 candles REST de uma hora armazenados na VPS, checksum válido, 9 hipóteses históricas reproduzíveis sem rede. Não é evidência de candle atual WS.
- Teste integrado D462 **com sessões WS offline injetadas** em UID `cia-probe`: 50 históricos de 24 candles, 50 fechamentos `confirm:true` pós-ACK gravados somente no SQLite WS, callback D449 e cálculo de coorte pelo D435 concluídos, sem ordens reais ou faturas. A versão inicial falhou por etiqueta de proveniência inconsistente; corrigida e o teste pontual passou na VPS.
- Teste negativo: se 1/50 fechamentos WS estiver ausente, o ciclo não deve admitir a coorte para novas entradas PAPER. Testes de proteção do REST D461 também cobrem checksums, janelas, identidade e ausência de write parcial.
- **Ainda não foi demonstrado o último fechamento real de 1h via WS na versão D462 na VPS**. Não declarar J6 homologada ou papel operando continuamente até obter essa prova. O candidate systemd e o painel atual ainda não foram publicados no host.
- **Correção de validade contratual D463 já implementada, pendente de validação integral/live:** o D451 exige metadados com até 60s e o PRE11 até 30s, mas obter os 50 históricos pode durar mais de 100s. O novo worker HTTP público atualiza **somente** contratos candidatos, verifica que o lote/tick/alavancagem não mudaram e espera o próximo BBO pós-GET; não aumenta TTL, não bloqueia o fluxo de saídas e não garante ordens reais. Consulte `docs/J4_ASYNC_PUBLIC_CONTRACT_REFRESH_D463.md`. Ainda exige comprovação real da operação permanente e dos gates financeiros.
- O histórico é de origem pública não autenticada; nem `confirm:true` sozinho certifica contratos cripto, funding, lucro, execução ou proteção na corretora. Alavancagem 50x continua parâmetro de simulação. O operador não envia ordens reais e a J1 permanece intocada.

## Critério funcional de aceite seguinte

Executar uma janela pública real com **aquecimento REST persistido, novo `confirm:true` 60m de todos os 50 ativos e pesquisa J2 causal**; inspecionar hashes e duas proveniências, provar recuperação e habilitar metadados recentes sem nova entrada inventada. Então finalizar monitoramento de posições e status J5 e aplicar os gates para um serviço PAPER permanente. Nenhuma dependência de compras; R$0 adicional.
