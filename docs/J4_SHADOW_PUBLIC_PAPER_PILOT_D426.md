# D426 — piloto de uma sessão PAPER sombra, referenciado por preço público real

## Que problema resolve

O operador D425 já acompanha contratos existentes com Bybit pública, mas ainda depende de **criação manual prévia de diário AUTO4 e configuração de preços**. A simulação D392 usava preços fixos de teste (por exemplo 100 USDT), que não correspondem à cotação real contemporânea de BTC ou das demais moedas. Isso impede validar, sem intervenção do Product Owner, um ciclo útil de *tick público genuíno → cenário PAPER → stop/parcial*.

D426 constrói um laboratório **temporário e descartável** em **uma única sessão WS pública finita**. O primeiro ticker próprio **após ACK**, validado pelo decoder existente D385/D386, com livro positivo, idade <=3 s e spread compatível, ancora uma **entrada inventada de pesquisa ao preço mark recebido**. Esse evento **NÃO** é uma ordem executada, trade real, fill deduzido, lucro ou sinal de estratégia. O código registra um FILL exclusivamente **fabricado e declarado**, apenas para construir o estado PAPER local que o AUTO4 exige. **O mesmo ticker não pode disparar sua própria saída.** Tickers posteriores do contrato, com relógio da exchange estritamente após o instante de abertura hipotética, são enviados ao mesmo roteador D391/D389 e diário AUTO4 já existentes, que podem reservar reduções stop-first ou alvos.

Assim evitamos abrir um feed paralelo ou escrever outra contabilidade financeira. O supervisor existente gerencia ACK, mensagens pré-ACK em quarentena, snapshot/delta, heartbeat, reconexão, orçamento de frames e latência. Usa a coorte J1 N50 ativa somente leitura D406 e acrescenta o símbolo solicitado se estiver fora do ranking. Depois do lease, revalida a época owner, retorna **somente contagens** e destrói o arquivo PAPER temporário. Nenhum símbolo, marca, ID privado ou payload da Bybit é exposto no relatório.

## Parâmetros de pesquisa e limitações

Padrões da CLI: margem hipotética 3 USDT, alavancagem hipotética 50x, stop a 100 bps e dois alvos a 10 e 20 bps em relação ao **mark inicial**, saídas 30% + 20% sobre o inicial e residual de 50%. LONG e SHORT configuráveis. Isso é configuração de **cenário de teste**, não uma hipótese de alpha ou recomendação; nenhum sinal de entrada foi computado.

Quantidade base é **sintética**, truncada a 12 casas decimais para não ultrapassar o notional solicitado; se divergir por mais de 1 bp, o piloto se abstém. O passo sintético deriva da própria quantidade, **não é o lote da Bybit**. Não atesta `minOrderQty`, `minNotional`, mark executável, alavancagem aceita, margem real, funding, custos, liquidação, slippage, preenchimentos pós-latência, profitabilidade ou segurança de 50x. Só o stop hipotético pode produzir intenção reduce-only, jamais stop nativo da venue.

Todas as opções de acesso (owner J1, WS público, pesquisa regional, PAPER hipotético) são opt-in. Sem elas a função retorna **antes de leitura/arquivo/socket**. Limites: 1–2 sessões, até 60 s e 100 mil frames, sem daemon/timer/escrita J1. A CLI real exige usuário não root, POSIX e pasta owner existente. Não publicar D426 na VPS sem gate **distinto** de piloto/release. A implantação D423 atualmente executada deve permanecer imutável.

### Formato de execução após gate operacional futuro

```sh
python -m scripts.run_j4_shadow_public_paper_once_d426 \
  --state-directory /caminho/owner/j1-ativo \
  --symbol BTCUSDT --side LONG \
  --margin-usdt 3 --leverage 50 \
  --stop-bps 100 --target1-bps 10 --target2-bps 20 \
  --seconds 30 --max-frames 100000 \
  --allow-private-pointer-read \
  --allow-public-websocket \
  --confirm-personal-readonly-research \
  --confirm-region-eligible \
  --allow-hypothetical-paper-open
```

Usar apenas após revisão de elegibilidade de ambiente e fonte e gate de publicação de pesquisa. `--symbol` seleciona **um contrato a observar para um cenário fictício**, não ativo recomendado nem símbolo da posição financeira verdadeira. O operador gera no máximo uma posição hipotética por sessão, sem quantidade-alvo operacional de posições. Não altera a política futura de múltiplas posições reais.

## Evidências exigidas e próximos gates

- Teste hermético D426 usa um socket fake e o verdadeiro decoder D386, com ACK, evento-semente e evento posterior, real AUTO4 em diretório temporário, stop primeiro, alvo LONG/SHORT, ausência de autorização, mensagens pré-ACK, relógios stale, margem e leverage inválidos, retorno sanitizado.
- CI Linux/Python, Windows/offline e Chrome do HEAD exato; merge sem deploy se os gates passarem.
- Piloto público **real** posterior precisa fixar SHA, confirmar fonte/região, estado J1 e isolamento de CPU, reutilizar diretório temporário, medir se houve ACK/primeiro snapshot/segundo tick, contagens de reservas, faixas de latency e eventuais interrupções. Sem posição real, conta, senha, ordem ou exposição de rede.
- Depois do piloto temporário: fazer o monitor de posições persistidas D425 acompanhar PAPER prospectivamente com regras de entrada quantitativas causalmente validadas, reconciliando FILLs somente por eventos explícitos; então avaliar custos/risco/OOS no J3 e homologação J6.

**Não afirmar que o motor está negociando em produção por um teste synthetic ou pela simples presença de websocket público.** Custo adicional R$0,00.
