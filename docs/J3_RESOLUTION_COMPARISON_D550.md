# D550 — Comparar as resoluções do mesmo estudo anual

## Entrega
O resultado anual D541 de 1h já existe; D547 deve produzir
`annual5m-d547.json` após completar as velas, mark e funding.
Não repetir o primeiro replay nem executar um novo apenas para resumir.

O módulo `j3_resolution_comparison_d550` reutiliza D542 para validar
as duas fontes. Exige o mesmo plano, perfil, matriz e experimentos,
período de desenvolvimento anual, janelas reservadas, configuração
de entradas e saídas, 50x, stop 150 bps, stress 50/100/150 bps,
oito estratégias, seis saídas e cinco horizontes (240 cenários).
Compara hashes e contagens do contexto de 1h de todos os 50 ativos,
dados observados de funding e cobertura. O mark tem resolução
distinta por construção; não exige hashes iguais de mark ou trade-5m.
Aceita diagnósticos adicionais de stress/exposição em relatórios novos
sem exigir sua presença no legado. Não modifica os relatórios.

A saída apresenta por cenário: quantidade de sinais e trajetórias
cobertas, intervalos líquidos condicionais ao funding, média por
trajetória, saldo realizado/aberto antes de funding, stress em ambas
as ordenações e estabilidade por coorte mensal. O resumo apresenta
transições de sinal (positivo, negativo, misto ou indisponível) por
horizonte. Comparação descritiva, sem ranquear ou selecionar vencedor.
Mesmo com contagens iguais, não atesta identidade de trajetórias.
Não calcula efeito pareado, não afirma que a diferença é causada
somente pela resolução; diferenças de amostra e motor são possíveis.
Não é carteira, liquidação comprovada ou validação financeira/OOS.

## Interface local
Após D547 concluído e gate administrativo de disponibilização do
código, como owner não-root em checkout revisado:

    python -m scripts.compare_j3_annual_resolution_d550 \
        --hourly-report "$ANNUAL_1H" --fine-report "$ANNUAL_5M" \
        --confirm-private-readonly-research --compact

Sem --compact, retorna também os 240 registros de cenário. Caminhos
absolutos privados, arquivos owner-only, tamanho limitado, leitura sem
alteração. Não disponibilizar os relatórios privados publicamente.
Não executar agora; nenhum serviço, broker ou VPS foi alterado.

## Decisão de continuidade da base (28/11/2026)
O PO autorizou aquisição única por partes, preservação e reutilização,
sem novos coletores alternativos. D547 instalado
c227a797fa3a44e3762b84c996229fe8a8bcb3ab. Último 10006 em
28/11 14:45:20 UTC; 2.013.040/5.245.798 velas trade-5m (38,37%).
Política registrada na issue #4 comment 7240997239: parar ao limite,
reconciliar progresso, aguardar pelo menos 24h e retomar somente se
elegível, sem contornar restrição. Não alterar o executor durante pausa.

Risco identificado: MAX_PLAN_AGE_MS=30*DAY em D528, usado pelo D543
para início e pelo D536 para consulta e leitura de páginas, e pelo
parser de candles para idade do contrato. Uma coleta gradual pode
exceder o prazo. Antes de expirar, preparar entrega agrupada de
continuidade de plano histórico explicitamente autorizada, separando
prazo de aquisição retrospectiva e frescor de metadados atuais.
Preservar plano, coorte, cutoff, digest, shards e páginas existentes,
não rebaixar gates de dados atuais nem alegar metadados contemporâneos,
não alterar o relógio ou renovar artificialmente timestamps. Exigir
prazo finito explícito, provenance, compatibilidade de leitura e
regressão de páginas antigas, limite de requisições e parada em
restrições. Mudança administrativa só após revisão/gate; não
implementar exceção silenciosa no coletor. Se expirar antes disso,
manter dados e comunicar bloqueio; nunca reinicializar.

## Aceite
Testes sintéticos: grade 240, mudança de sinal, amostra menor, funding
incompleto, contagens iguais sem pareamento e rejeição de divergências
de configuração, manifestos, partição, cobertura e JSON. CI Linux,
Windows e mobile; revisão exata antes de merge sem publicação.
Relatório real 5m, comparação real e aprovação financeira pendentes.
D549 permanece separado. Sem alteração de J1/PAPER, sizing, stops,
perfil, ordens, 730d, rede adicional, produção ou custo.
