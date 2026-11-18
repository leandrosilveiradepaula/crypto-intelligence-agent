# D425 — posições PAPER existentes no WebSocket público Bybit, sessão finita

## Entrega de produto

Antes deste trabalho, o operador J2/J4 D410 já continha a composição causal **D406 (coorte N50 ativa) → D390/D386/D385 (WebSocket público, ACK, snapshot/delta) → D391/D389 (stop primeiro, parciais e runner) → AUTO4 (reserva transacional)**, mas faltava uma forma segura e explícita de carregar as regras das **posições PAPER persistidas** e iniciar a sessão a partir do próprio operador. D425 acrescenta somente esse limite operacional de entrada; não duplica motor, feed, seleção, posição ou ledger.

O CLI `python -m scripts.run_j4_current_paper_ws_once_d425` usa somente os contratos existentes. O WebSocket público da Bybit é de mercado, **sem credencial ou envio de ordens**. Posição PAPER dentro ou fora da coorte dinâmica recebe monitoramento. Stop do contrato mantido não fica bloqueado por ticker obsoleto de outro símbolo. Um evento elegível pode **reservar** redução hipotética no diário; ACK público nunca prova FILL e a reserva pendente/UNKNOWN continua pendente após reinício.

## Pasta privada exigida (não versionar)

Um operador não root deve criar previamente uma pasta privada de pesquisa (owner `0700`) **fora do diretório J1**. O programa não cria posições ou saldos e não importa conta da corretora. Dentro dela:

- `paper-positions.sqlite`: diário AUTO4 **já existente**, owner `0600`, link-count 1, não symlink. Contém as posições PAPER fictícias e respectivos planos/confirmações de fill fictícias, criados por fluxos de simulação anteriores.
- `paper-routes.json`: owner `0600`, até 32 KiB, JSON estrito, sem campos extras, números financeiros como strings decimais. Deve corresponder aos IDs e versões do mesmo diário. Exemplo **apenas de formato**, sem gerar posições:

```json
{
  "schema_version": "j4-private-paper-routes-d425-v1",
  "positions": [
    {
      "position_id": "fixture_example_paper_position",
      "plan_version": "fixture-plan-v1",
      "stop_mark_price": "99",
      "target_prices": ["101", "103"],
      "max_spread_bps": "30",
      "runner": null
    }
  ]
}
```

Quando as parciais já tiverem FILL PAPER explícito e saldo runner elegível, pode-se configurar `runner` com `file` (`runner-*.sqlite`, mesmo diretório), `activation_bps`, `trail_distance_bps`, `max_tick_gap_ms`, `max_last_tick_age_ms`. O journal RUNNER2 permanece próprio e não recebe ordens. Arquivo existente deve ter `0600`, sem symlink.

## Invocação limitada

```sh
python -m scripts.run_j4_current_paper_ws_once_d425 \
  --state-directory /caminho/owner/j1-active \
  --private-paper-directory /caminho/privado/paper \
  --seconds 30 --max-frames 100000 --max-sessions 1 \
  --allow-private-pointer-read \
  --allow-public-websocket \
  --confirm-personal-readonly-research \
  --confirm-region-eligible \
  --allow-synthetic-paper-reservations
```

Exige cada opção explícita; na ausência de autorização não lê owner, não abre WebSocket e não altera PAPER. Limites: `seconds <= 60`, sessões até 2, frames até 100 mil e máximo 50 posições (limite do **piloto**, não meta operacional). É exclusivamente opt-in e finito: **não instala serviço, timer, cron, feed 24×7, API de ordens nem acesso remoto**.

Os arquivos não são importados pelo GitHub nem publicados no painel. O relatório stdout contém apenas contagens e classificações do D410, sem símbolos, IDs, preços, saldo ou credenciais. Um código de retorno 2 indica cobertura incompleta da amostra; jamais assume stop nativo ou rentabilidade. Erros são sanitizados; se houver erro após a reserva PAPER, consultar o diário antes de qualquer repetição, porque não é afirmado rollback.

## Proteções e gates

- Validação fail-closed do manifest (duplicação de chave, float, NaN, campo extra, direitos do arquivo, symlink/hardlink, id/plan/venue, ordem dos preços LONG/SHORT, faixa de Decimal, políticas de stop/target/runner) antes de socket ou reserva. Lock owner exclusivo evita duas sessões D425 gravando no mesmo PAPER journal.
- O curso de uma janela N50 usa a epoch J1 atual sob leitura, revalidada ao fim, e não escreve no SQLite histórico. Posição PAPER fora da coorte tem assinatura incluída, sem novo ranking.
- Sem conexão privada Bybit, ordem, execução de FILL, stop nativo, margem verificada, PnL líquido ou decisão de entrada. A fonte é mercado **público não autenticado**.
- CPU/RAM e estabilidade **não homologadas** em uso conjunto com J1/D423. Código e testes não autorizam instalação, operação supervisionada permanente ou mutação de dados operacionais da VPS. Qualquer piloto que grave posições PAPER na VPS exige plano/gate próprio e isolamento do diretório e das janelas J1.

## Aceite automatizado

`tests/test_j4_private_paper_ws_operator_d425.py` injeta sessão WebSocket offline em D425/D410 e usa o journal AUTO4 real criado por fixture. Verifica reserva parcial sem FILL, stop antes de qualquer outro ticker N50, idempotência entre sessões/restart, bloqueio sem cinco opt-ins, lock concorrente, permissão 0700/0600, integridade do manifesto e runner opcional. Gates CI Linux/Python, Windows (POSIX-only skip) e navegador; integração apenas se verdes no SHA exato. Custo adicional R$0.

**Próxima etapa material:** piloto em ambiente PAPER segregado para comparar eventos públicos reais com decisões AUTO4, observar lacunas e persistência através de reconexão, depois feed 24×7 e supervisão de posições. Não misturar isso com autorização de negociação real.
