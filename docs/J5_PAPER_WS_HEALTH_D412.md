# J5 D412 — saúde do WebSocket e da gestão PAPER no aplicativo

## Entrega de produto

O aplicativo móvel em português pode importar um relatório de diagnóstico já gerado pelo **circuito J2/J4 D411** (`j2-j4-current-n50-paper-lease-d410-v1`) pelo mesmo seletor JSON existente, sem conectar a corretora ou expor um endpoint novo. Uma seção independente das posições persistidas mostra:

- **Origem**: fixture sintética ou sessão pública declarada pelo arquivo. Nenhum arquivo importado é autenticação independente da Bybit.
- **Saúde do universo**: quantos contratos do N50 + posições entregaram cotações causais e quantos estavam frescos ao fim da sessão.
- **Gestão PAPER**: quantidade de posições monitoradas, inclusive fora do Top50, quantos ticks das posições foram avaliados e quantas reservas hipotéticas de stop ou parcial foram registradas pelo coordenador.
- **Falhas e reconexões**: quantas reconexões ocorreram, cotações próprias descartadas por vencimento e se a época owner permaneceu a mesma antes/depois.
- **Separação de segurança D411**: um Top50 incompleto pode aparecer como **Mercado degradado** ao mesmo tempo que o stop da posição PAPER tenha sido avaliado por um ticker próprio recente. A tela não acusa a posição de desprotegida apenas por falta de preço de outro altcoin.

O relatório de sessão é **estático**: não prova monitoramento em tempo real, disponibilidade 24×7, ordens, fill, native stop, lucros, validação OOS ou elegibilidade crypto-only. Nenhuma entrada é autorizada.

## Contrato seguro

O módulo JS `web/app/paper-ws-health.js` valida chaves exatas da projeção D390/D410, tipos e limites numéricos, ausência de ordens, ausência de autenticação de mercado, consistência de cobertura e a política `fresh_held_position_quote_independent_of_n50`. Rejeita status financeiro supostamente live, flags de autorização, estados contraditórios, contagens excessivas, símbolos e IDs inesperados. Usa apenas `textContent`, nunca HTML, script injetado, download remoto, armazenamento local ou API de exchange.

Um relatório inválido preserva o painel válido anterior; o arquivo não modifica o laboratório de posições ou o diário AUTO4. Após reload a amostra desaparece. O servidor loopback J5 apenas passa a servir um JavaScript estático novo, sem leitura do SQLite ou novas permissões.

## Como usar

Quando um resultado D410/D411 estiver disponível em um ambiente de pesquisa **autorizado**, exportar seu dicionário sanitizado como JSON, abrir o aplicativo J5 e usar **Selecionar arquivo JSON local**. O painel exibirá o estado daquela sessão encerrada. Nenhuma execução na VPS foi realizada para gerar arquivo com dados reais nesta entrega.

É possível obter um relatório somente sintético nos testes `test_j2_j4_current_n50_paper_lease_d410.py`; este exercício mostra a UI e não substitui evidência de mercado.

## Validação

```sh
python -m unittest discover -s tests -p 'test_j5_paper_ws_health_d412.py' -v
python -m unittest discover -s tests -p 'test_j2_j4_current_n50_paper_lease_d410.py' -v
python -m scripts.audit_j5_product_app_browser
```

O teste D412 usa a saída **real do produtor D411 no journal AUTO4 sintético** e passa seu JSON para o validador/renderer Node. Exercita N50 incompleto com cotação de posição válida, estado de mercado degradado, rótulo de fixture, veto a falsa autenticidade/PnL/ordens, e contagem de posições externas. Chrome continua verificando a interface em diferentes larguras, sem acesso de rede.

## Pendente para o uso real

O primeiro ACK + ticker público real na VPS ainda depende do executor Python permitido pelo gate operacional. Falta um supervisor de longo prazo, observabilidade em caso de silêncio dos preços, concorrência segura dos journals e uma fonte privada de estado PPE reconciliado para atualização automática do celular. Nenhuma ordem real ou instalação na VPS foi autorizada. Custo adicional zero.
