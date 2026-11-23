# D470 — Console J5: última sessão pública PAPER versus estado atual

## Entrega de produto

O Console local (127.0.0.1:8765) poderá exibir um painel **Última sessão N50 / PAPER**, separado do painel **Operador PAPER residente** e das posições reais do diário PAPER. Uma sessão D450 terminada há minutos ou dias NÃO é cobertura de mercado atual. Cada informação vem exclusivamente do resumo sanitizado D459/D469 do operador D453, não de credenciais da corretora, chamadas de rede ou logs arbitrários.

O novo leitor \`j5_last_public_paper_lease_d470.py\` reabre o arquivo owner-only \`paper-last-public-lease-d459.json\`, modo 0600 sob diretório POSIX 0700, rejeita troca de inode, link simbólico, chaves duplicadas, schema não permitido, números inválidos, combinações incoerentes e dados com mais de sete dias. Aceita o schema original D466 e a extensão tipada D469 sem confundi-los: valores não armazenados na execução antiga aparecem como **indisponíveis**, não como zero. Somente contadores e categorias permitidas chegam à página, sem símbolos, preços, hashes de pesquisa, caminhos locais ou mensagens do provedor.

O endpoint \`GET /api/last-public-paper-lease\` fica **DESATIVADO por padrão**, requer opção e diretório explicitamente indicados e usuário proprietário não-root; nenhuma rota pública, POST ou CORS é criada. O navegador recebe apenas se estiver servido pelo loopback local, valida estritamente os dados e limpa a leitura em qualquer falha. Informação antiga fica marcada como histórica mesmo se o processo atual estiver ativo.

## Conteúdo visível

- Última sessão retornou concluída ou degradada, data e frescor;
- Quantidade REST histórica, quantidade de fechamentos WS e callbacks PAPER **relatados** (não uma auditoria independente de diário);
- Situação kline, situação ticker e categoria técnica permitida da última falha;
- Coorte pesquisada, hipóteses relativas ao BTC e aberturas pendentes **quando D469 as registra**;
- Avisos explícitos: sem feed atual comprovado, sem stop na corretora, sem ordens reais, sem PnL ou validação OOS.

Mesmo que o resumo mostre 50/50 e ticker concluído, a última lease não comprova 24h WS, feed no momento, posições protegidas ou aprovação da estratégia. A prova D466 com 50/50 possui conferência SQLite independente registrada no \`OPERATIONAL_STATE.md\`; esta UI **não** reivindica repetir tal conferência.

## Aceite e implantação

Teste POSIX não-root do leitor, arquivo D466 legado, D469 completo, stale, flags de segurança, symlink, modos, duplicatas, HTML/Node e gates do servidor. Conferir CI Linux, Windows e mobile no SHA final. Nenhuma instalação: a VPS ainda tem servidor 8765 antigo e o serviço novo depende de gate de release, não deve disputar a porta. Sem ordens reais, J1 ou custo adicional. Após disponibilização, avançar para prova prospectiva PAPER com dois WSS saudáveis, feed causal e RiskGate, antes de declarar operação autônoma.
