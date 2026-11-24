# D515 — atualização única do PAPER (D509–D514)

## Entrega ao operador
Atualizar motor e painel juntos: Centro de Decisões, desempenho por operações encerradas, comparação histórica e configuração independente EMA/SMA/Pivot Point SuperTrend. O perfil atual não será automaticamente substituído por uma estratégia nova. Os dados, históricos, posição e parâmetros financeiros continuam nos mesmos diretórios owner. J1 e o timer N50 ficam intactos.

## Pré-condições de publicação
- D513/D514 integrado ao main após CI e revisão do SHA exato.
- Script D515 aprovado e integrado. O parâmetro SHA é a revisão final de main validada, não uma branch ou SHA escolhido por conveniência. Obter o script por URL imutável fixada ao commit revisado, verificar sintaxe e executar somente no host explicitamente pinado.
- A versão de origem é D507, SHA 056845fdc46b8c2d1b08acd86be75e59dd368bac, ambas unidades PAPER ativas e os dois drop-ins D507 originais sem modificações. Leitura owner D505 consistente; zero posições abertas.
- Consentimento explícito interativo no terminal: AUTORIZO CUTOVER PAPER. Nenhuma troca de serviço antes dessa confirmação.
- Não editar perfil durante a troca. O lock de perfil D487 fica retido na fase de publicação e rollback. Os dois drop-ins D507 permanecem no lugar; os novos drop-ins D515 alteram somente WorkingDirectory. Novo painel e contratos HTTP são verificados antes de iniciar motor. Em falha, remover apenas overrides D515 e voltar aos anteriores. Não copiar, apagar, migrar ou restaurar dados privados.

## Aceite e limites
Verificar D515_RELEASE=PASS, SHA esperado, endpoints scorecard/histórico/perfil, rota de decisões (aceita ausência explícita de lease completa), rota de comparação, controles SMA/Pivot, serviços PAPER ativos e J1 ativo. O roteiro não prova continuidade WS, preenchimento de ordens, rentabilidade, funding, liquidação ou que há amostra suficiente para a comparação: executar o laboratório sobre o histórico real após a troca. Nenhuma ordem real. O custo adicional permanece zero.

Se a atualização falhar, conferir o resultado de rollback e a revisão em execução; não repetir automaticamente. Se uma estratégia incompatível com D507 for salva depois de uma publicação bem-sucedida, qualquer rollback futuro necessita de revisão explícita do perfil antes de iniciar código antigo. Nunca sobrescrever configuração do usuário.

## Estado de preparação
O VPS foi consultado em 24/11/2026: as duas unidades PAPER e o timer J1 estão ativos, com zero posições abertas, uma encerrada e sem ordens reais. A elegibilidade é temporal e será reconferida no gate, não presumida para a instalação. D514 corrige o selo offline legado (84 erros + 1 falha da primeira CI D513 tiveram a mesma causa). O script está preparado, não executado; requer a aprovação dos dois conjuntos de alterações antes de publicar.
