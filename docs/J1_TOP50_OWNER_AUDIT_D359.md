# J1/D359 — captura real de cobertura PIT Top50, isolada do serviço N50

## Autorização

Em 15/11/2026, o Product Owner autorizou explicitamente a implantação controlada da telemetria D357 na VPS para concluir a auditoria restante da J1. A opção operacional menos invasiva é **instalar o auditor D357 em checkout isolado 0700** e executar um único censo público Bybit V5 pelo proprietário `cia-probe`. Isso não exige substituir o checkout do serviço N50 nem alterar timer, unidade, SQLite ativo, documentos privados ou reiniciar a coleta. Não é deploy de negociação.

## Contrato de execução

- Fonte de verdade: `deploy/vps/audit_j1_top50_rank_d359_once.sh` nesta PR, baixado somente de commit SHA40 revisado, com `bash -n`, executado via job operacional aprovado na VPS `srv1319424` como root da unidade transitória; as consultas de mercado e o checkout GitHub ocorrem **como** `cia-probe` (sem bypass de diretórios privados).
- Exige host correto, NTP, Python owner instalado, dois timers WS e rotação ativos/habilitados, serviços REST N2/N50 antigos inativos; aborta com estado invariável se falhar.
- O script cria apenas `/home/cia-probe/agent/j1-d359-top50-pit-20261115T190130Z/` e subdiretórios `code` e `scope`, 0700, **sem** usar o diretório privado ativo `j1-n50-ws-epochs`. Clona o mesmo repositório no SHA exato revisado, confirma checkout limpo, roda três suítes D286/D287/D321 **sem rede** antes da prova.
- Audit único agendado para **15/11/2026 19:01:30 UTC** (16h01min30 Brasília). Essa é a janela operacional D286 (HH:01..HH:15). Se perder a janela, serviço de rotação ainda ativo ou se retornar 429/erro, encerra sem retry de rede. Não compete com rotação devida; há evidência de coorte ativada em 14/11 15:13 UTC e periodicidade mínima 36h, portanto o ciclo 15/11 19:01 não está no limiar de nova rotação.
- Uma execução de `scripts.run_j1_current_ranked_epoch_once capture-seal` sobre **toda a pool elegível D279**, 24 candles horários fechados, catálogo antes/depois, orçamento 2s/GET, até 400 candidatos, salvando somente manifesto de pesquisa **isolado e owner 0600**. Não toca banco privado nem executa ordem. A seleção anterior D323 continua íntegra e separada.
- O relatório público do job só expõe JSON sanitizado de contagens, tempo PIT, hashes e flags. **PASS** de pesquisa apenas se `pool = positivos completos + zeros completos + incompletos`, incompletos = 0 e flag de completude verdadeira, catálogo estável, `orders_sent=false`, `database_modified=false` e `marketwide_top50_verified=false`. Histórico incompleto resulta **abstenção**, sem declarar J1 aprovada.
- O código na VPS não é modificado nos checkouts existentes; a telemetria D357 é implantada como **instrumento autônomo de auditoria**. Eventual atualização futura do rotador ativo é release separado e só se necessária para monitoramento de cada epoch. O output não prova retroativamente contagens da rotação de 14/11.

## Estados já comprovados

A prova D286 em 11/11 foi recuperada via `vps_job_status`: 930 instrumentos, 370 candidatos técnicos, **370/370 com 24h fechadas**, 0 incompletos e 50 selecionados. O D287 da noite de 11/11 selou outra coorte em snapshot distinto. Em 14/11 o D321 rotacionou com 372 GET e preservou a epoch antiga; D323 owner em 15/11 atestou 24×50 e 1.200 linhas SQLite da nova coorte. Nenhuma dessas provas exibe incompletos do PIT de 14/11; não inventar.

## Critérios e limites

1. Auditor script revisado, shell syntax/contrato testados e CI Linux, Windows, Chrome no SHA exato.
2. Job VPS status `completed`, `exit_code=0` e `D359_POOL_COMPLETENESS=PASS_RESEARCH_ONLY` com digest/contagens reais e timestamp PIT.
3. Fazer aceite da seleção **de pesquisa** J1 somente se os resultados e contratos forem coerentes com D279/D286/D357 e a rotação D321/D323; nunca mudar `marketwide_top50_verified`, `crypto_identity_independently_verified`, `approved_for_signals` ou autorizar operações reais.
4. Relatório no GitHub e atualização de OPERATIONAL_STATE e STATUS com SHA da implantação, job ID e resultado. Sem custo adicional, sem upload de manifestos/símbolos nem dados confidenciais.

**Abster sem retry** em qualquer falha. Não ativar trade, testnet, ações via exchange ou otimização de parâmetros.
