# D549 — validação financeira cronológica com hipóteses congeladas

## Decisão do PO e continuidade (28/11/2026)

Concluir histórico anual por lotes da Bybit, mesmo que demore; não
desenvolver mais coletores alternativos para a aquisição inicial. A base
histórica de pesquisa é baixada uma vez, preservada e reutilizada nos
backtests; novas barras e eventuais lacunas são extensão incremental,
não download integral repetido. Diferenciar a coleta residente de mercado
para sinais e PAPER. Não iniciar 730d nesta etapa.

D548 integrado em 6cf461745831385822a5f677cb39156d72b86964, sem instalação.
D547 continua instalado em c227a797fa3a44e3762b84c996229fe8a8bcb3ab.
Campanha trade-5m-365 retomada 28/11 14:40:21 UTC sob autorização do PO;
baseline 1.990.120/5.245.798 (37,94%). Parou em 14:45:20 UTC, retCode10006
na tentativa 25, sem retry/cabeçalho de quota. Coverage offline 14:48:37–14:49:17
UTC confirmou 2.013.040/5.245.798 (38,37%), +22.920 preservadas, faltam
3.232.758. Issue #4 comentários 7240847168/7240948178. Acompanhamento
desativado após falha terminal; não reiniciar automaticamente nem contornar.
D549 é trabalho independente, não altera executor/unidades/broker ou
requer terminal do PO nesta sessão.

## Limitação resolvida no código candidato

D542 já previa congelar hipóteses antes de abrir reserva. D537/D538
proibiam funding e stress em qualquer partição não-development.
D549 abre apenas o protocolo reservado explícito no mesmo D529,
não desativa a proteção genérica nem cria segundo motor de backtest.

Após D547 gerar annual5m-d547.json válido, D549 deriva contrato canônico
do relatório de desenvolvimento e de inputs reais: SHA256 do relatório,
plano, perfil owner, configuração de indicadores e saídas, política
efetiva (incluindo margem/50x), árvore de fontes Python do motor e scripts,
versão do interpretador, janelas e grid. Valida o relatório inteiro
com D542 e exige as mesmas 8 entradas e 6 saídas do estudo D547, stop
150bps, stress hipotético 50/100/150bps. Não ranqueia ou escolhe vencedor.
Parâmetros fixos SOMENTE para este estudo registrado, não para o produto.

As duas janelas de 18 dias reservadas originalmente são preservadas:
validação [cutoff-36d, cutoff-18d) e holdout [cutoff-18d, cutoff).
Cada uma: 8 entradas x 6 saídas x horizontes 48h/168h = 96 cenários.
Expurga 168h do fim da janela para ambas as resoluções de horizonte,
exige trajetória máxima completa para ambas e não cruza a fronteira.
Indicadores podem usar prefixo causal de velas anteriores, sem ajuste
sobre resultado reservado. A grade de instantes não é idêntica à
do desenvolvimento anual D547 (que expurga 2160h).
Horizontes 30/60/90 dias não cabem nessa reserva; exigem futura amostra
independente suficiente, não reclassificar dados já explorados.

## Execução posterior (privada, sem rede)

O CLI scripts.run_j3_frozen_validation_d549 tem três ações: freeze,
validation, holdout. Usa o mesmo diretório privado de relatório D547
e mesma base D528, policy e matriz D547. Exige owner não-root, flags
explícitas e lock existente. Freeze lê apenas relatório dev e
configuração/plano, grava contrato uma vez, não lê velas da reserva.
Registrar digest retornado externamente (issue #4, sem dados privados)
ANTES de qualquer replay. Recomputar contrato e confrontar digest
externo e arquivo local a cada ação. Não usar contrato fabricado ou
mudar perfil ou motor entre partições. Mudanças de qualquer fonte Python
fixada ou versão do interpretador invalidam o contrato; é vínculo de
reprodutibilidade, não atestado assinado do runtime. Os arquivos de configuração permanecem
parametrizáveis, mas o protocolo não permite alterá-los durante o teste.

Exemplo da interface (não executar agora):

    python -m scripts.run_j3_frozen_validation_d549 --action freeze \
      --directory "$HISTORY" --report-directory "$REPORTS" \
      --policy-file "$POLICY" --confirm-reserved-protocol

Após digest registrado, mesmas opções e --action validation (depois
holdout), acrescentar --expected-contract-sha256 com digest exato.
Não acionar sem conclusão D547 e gate operacional posterior.
Cada replay cria claim atômico sem substituir arquivo, antes da
leitura de dados; falha preserva claim e exige decisão, não retry
silencioso. Holdout exige relatório de validação íntegro no mesmo
contrato, nunca condição de PnL positivo. Publica arquivo privado
separado por partição, sem sobrescrever relatório anterior.
A proteção é de protocolo no diretório designado, não uma garantia
contra owner copiando arquivos ou executando outros programas.

D542 valida vínculo de relatório, digest, partição, grade completa,
funding, atribuição de stress e realizado/aberto. D544 compact
identifica partição e digest e omite ranking top-mean nas reservas.
Nenhuma aprovação OOS: dados históricos da coorte sobrevivente,
independência de acesso não atestada, funding observado não prova
settlement, stress hipotético não prova liquidação, trajetórias
independentes não são carteira. Sem alteração de perfil, 50x, sizing,
stops, J1/PAPER, serviço, rede, ordens, produção ou custo.

## Aceite candidato

Testes: determinismo do contrato, mutações de parâmetros antes de
qualquer leitura, execução D529/D537/D538 real sobre fixtures sintéticas
com limite temporal, validação de todos os 96 cenários, rejeição de
mistura de partições, freeze/validation/holdout uma vez e publicação
sem overwrite. CI/revisão do head exato pendentes. Nenhuma execução
com dados reservados reais nesta entrega. Não iniciar replay anual
5m antes de trade/mark/funding e preflight D547; não repetir anual 1h.
Agrupar eventual instalação D549 após conclusão da campanha e gate,
não solicitar acesso root agora.
