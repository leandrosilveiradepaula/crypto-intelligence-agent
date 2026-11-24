# D516 — pesquisa histórica complementar, sem trocar a estratégia PAPER

## Entrega
D461 corrige o limite divergente de 72 versus 122 horas via paginação no mesmo cliente público; 24–72 horas continuam com 50 GETs, 73–122 com 100 GETs para o N50. Não muda J1, endpoints permitidos, nem pacing/retry. D516 acrescenta um suplemento de aquecimento retrospectivo ao D512, sem aumentar a amostra artificialmente usando o ranking atual.

A coleta usa os últimos 24 pares de decisões originais, a primeira âncora de cada símbolo não-BTC elegível, até 80 símbolos e 122 horas. Recupera no máximo 160 GETs com pacing existente, sem retry, opt-ins explícitos do proprietário e diretório owner. A sobreposição de todo o trecho congelado deve ser idêntica; gaps/revisões excluem o suplemento. O arquivo separado d516-retro-warmup-*.json tem digest, data real e modo 0600, sem editar D461, WS, perfil ou SQLite. O dashboard faz apenas leitura local, selecionável; nunca chama a Bybit durante GET do painel.

## Uso após integração e autorização de ambiente
No checkout da revisão aprovada, executar como UID proprietário (não root), com os caminhos já existentes do perfil e diretório histórico:
```bash
python -m scripts.run_j3_retrospective_warmup_d516 \
  --historical-directory "$HISTORY" --policy-file "$POLICY" \
  --history-hours 122 --ema-periods 10 30 60 \
  --allow-public-network --confirm-personal-readonly-research \
  --confirm-region-eligible --confirm-public-data-rights
```
Períodos acima são exemplos editáveis. `--reuse` usa a última captura local sem rede. Nunca afirmar que o download foi executado antes do recibo. Se a âncora não estiver mais nas últimas 72 observações, ela fica indisponível para a comparação; uma nova coleta pode ser solicitada. Não usar isso para sinais WS, trading real, ou comprovar OOS. A atualização do painel D516 requer gate de release separado; o CLI pode ser executado em checkout isolado sem parar o D515.

## Aceite
Testes de 122 velas e duas páginas por símbolo, validação de sobreposição/digest/data, ausência de preços posteriores, causalidade, cobertura e preservação de amostra; CI Linux/Windows e QA geral móvel antes de merge. Resultados reais ainda não obtidos nesta implementação. D515 continua operacional. Sem custos adicionais.
