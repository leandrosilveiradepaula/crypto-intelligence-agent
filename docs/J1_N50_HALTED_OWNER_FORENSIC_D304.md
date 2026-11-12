# J1/D304 — verificação forense de journal N50 HALT sem novas chamadas ao provedor

## Incidente real — 12/11/2026, 08:01 UTC

O N50 produziu 3 checkpoints reais até 07:00 UTC. No fechamento 08:00, o escritor M1 tentou 7 GETs, persistiu 6 candles de 50 contratos e registrou HALT `provider_denied_owner_review`. O serviço encerrou com exit 65 e acionou o fallback para o N2, cujos timer/serviço antigos permaneceram disponíveis. A tentativa seguinte não pode apagar HALT nem completar um checkpoint 08h artificialmente. O subtipo do erro remoto não ficou disponível nos logs históricos; D303 passou a transportar whitelist de `failure_category` para incidentes futuros. Não atribuir erro ao limite de quota ou região sem evidência.

## Contrato D304

`crypto_intelligence_agent.j1_n50_halted_forensic.audit_halted_n50_epoch` relê como proprietário não-root o manifesto selado de 50 contratos e SQLite privado exclusivamente `mode=ro`+`PRAGMA query_only=ON`, e valida: escopo/digest/membros, esquema, `integrity_check`, todos os recibos `published_hour` com hora e digest, todos os 50 cursores e histórico contíguo de candles com hashes e OHLCV, as 3 publicações e as 6 posições avançadas sem publicação. Resultados count-only sanitizados, sem preços/símbolos/retMsg ou credenciais. `resume_authorized=false` incondicional, `network_requests=0`, `database_mutation_statements=0`, `orders_sent=false`. Falhas de validação resultam `blocked`. Falta de HALT não é relatório forense positivo.

CLI `python -m scripts.audit_j1_n50_halted_owner_once --allow-private-readonly-audit` usa exclusivamente raiz N50 privada pinada e ponteiro ativo D294, não permite escolha de SQL, journal ou rede pelo usuário. Não modifica systemd nem recoloca N50 em produção.

## Política de recuperação

**Não repetir automaticamente requisições** no journal com HALT. Preservar snapshot/claims/recibos reais e N2 restaurado. Recuperação futura exige diagnosticar o tipo de falha observado em fonte pública sem burlar restrição, validar acesso/limites e criar *nova* epoch e journal sob gate operacional; nenhuma retropublicação de 08:00. A simples aprovação da suíte D304 não prova 24h N50 nem autoriza cutover.

## Testes e evidências

`tests/test_j1_n50_halted_forensic.py` gera SQLite real 50 contratos, 1.306 candles (1.300 de 3 publicações completas + 6 avançados), 3 recibos com clocks válidos e HALT idêntico à forma do incidente. Verifica que somente os 3 checkpoints são publicados e as 6 linhas parciais continuam contabilizadas separadamente. Cobre digest/recibo adulterados, ausência de HALT, symlink, relógio, owner e opt-in. Regressão J1 N50/D292 e CI Linux/docs Windows/offline Chrome/PAPER antes do merge sem deploy. Depois, owner-only leitura VPS para confirmar o estado real, sem alterar os dados.
