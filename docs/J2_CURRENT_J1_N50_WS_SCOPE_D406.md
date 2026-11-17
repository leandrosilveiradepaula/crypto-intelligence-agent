# J2 D406 — reutilizar automaticamente o Top 50 ativo da J1 no WebSocket público

## Evolução funcional

Até D405, o teste WebSocket exigia que alguém digitasse `--symbols` com cada um dos contratos monitorados. Isso não serve como origem recorrente de um universo dinâmico.

D406 passa a ler **somente em memória** a coorte N50 que a J1 já mantém na sua época ativa. Não cria novo ranking, não consulta instrumentos, não repete REST, não lê o SQLite de velas e **não muda o writer J1**. O monitor recebe exatamente os cinquenta símbolos do manifesto causal provisório existente e pode incluir símbolos de posições PAPER abertas fora desse grupo.

O encadeamento usa os validadores J1 originais, sem confiar apenas em nomes de arquivos:

1. Resolver o ponteiro privado da época ativa com a política de permissões do owner e os digests de manifesto/metadata.
2. Carregar e revalidar o cache privado imutável da admissão WS, que contém o catálogo e a coorte relacionados ao mesmo digest PIT.
3. Reexecutar o validador D287 de cinquenta membros e conferir identidade exata contra o catálogo D314.
4. **Reler o ponteiro ativo**, recusando mudança de época/manifesto/cache durante a consulta. Uma rotação nunca deve causar subscrição de escopo misturado.
5. Passar a lista apenas como argumento **interno** ao observador D405, acrescentando posições admitidas pelo owner. Diagnóstico JSON externo contém apenas contagens/digests, jamais os símbolos.

Nenhum desses passos eleva a prova J1 provisória a classificação mercado-amplo de todas as criptomoedas. O sistema continua dizendo `marketwide_top50_verified=false` e `crypto_identity_independently_verified=false`. Falha de acesso, validade de até 48 h, permissionamento, integridade, digest, número de contratos ou rotação simultânea **aborta antes de abrir o WebSocket**.

## Como o teste poderá ser executado

Para um operador autorizado com checkout revisado, UID dono do cache e `state-directory` efetivamente configurado:

```bash
python -m scripts.probe_current_j1_n50_bybit_ws_d406 \
  --state-directory "$CIA_OWNER_EPOCH_DIRECTORY" \
  --seconds 20 \
  --allow-private-pointer-read \
  --allow-public-websocket \
  --confirm-personal-readonly-research \
  --confirm-region-eligible
```

Não é necessário passar manualmente os cinquenta contratos. Opcionalmente, o caller seguro fornece `--positions` para incluir posições PAPER fora do ranking; essa lista deverá vir de uma fonte de posições versionada/reconciliada, nunca ser presumida pela existência do símbolo. Os quatro gates são obrigatórios para ler o cache E abrir socket. Sem eles, nenhuma leitura privada ou tentativa de rede ocorre.

O leitor da J1 verifica **permissões de dono não-root**, modo dos arquivos, digest, momento PIT e cache de metadados. Não introduzir novo acesso como root nem copiar o cache para área pública. Essa operação ainda exige o executor de Python autorizado pela política da VPS; o MCP atual retorna `exec_unavailable`, portanto não foi executada sessão de ticker real, nem há aprovação de release.

## Comportamento PAPER e segurança

Este módulo alimenta o mesmo `observe_finite_public_ws_once` de D405, que utiliza D390/D386/D385. Ele mostra cobertura de contratos e posições admitidas na lista, perda de frescor e faixas de latência. Uma posição fora dos cinquenta membros não desaparece do monitor. D401 possui conexão opcional separada ao journal PAPER existente, mas D406 **não ativa essa conexão, não cria intenção, não simula FILL, não instala serviço 24×7 nem envia ordens de corretora**.

A interface móvel e a amostra REST D404 permanecem independentes deste feed e a J1 continua recebendo fechamentos horários. Nenhuma implantação, conta, chave, ordem, migração ou custo novo.

## Aceite reprodutível

```bash
python -m unittest discover -s tests -p 'test_j2_current_j1_n50_public_scope_d406.py' -v
python -m unittest discover -s tests -p 'test_bybit_public_ws_operational_probe_d405.py' -v
```

Fixtures artificiais de ponteiro/cache validado para simular o lado J1 (sem leitura real de pastas privadas na CI), seguidas por ACK e 51 snapshots injetados atravessando D405/D390/D386/D385: 50 da coorte + 1 posição externa. Verifica retenção da posição externa, ausência de cotações frescas ao fim, recusa da rotação concorrente e corrupção de manifesto/cache, nenhuma leitura privada sem os gates, nenhum preço/símbolo/ID no relatório e nenhuma ordem.

## Próxima ação elegível

Com essa ligação, o futuro operador não precisará escolher manualmente o Top 50. Falta medir **ACK e snapshots reais da Bybit**, carga/latência e integridade do monitoramento longo no host; depois um supervisor independente deve revalidar a coorte em cada rotação, conciliar as posições PAPER e permitir acionamento do gestor de risco sem depender do celular, sempre com controle de stale e sem duplicar o escritor J1. O gate de instalação na VPS e negociação real continuam fechados.
