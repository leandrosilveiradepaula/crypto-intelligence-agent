# J1 — auditoria atual do catálogo Bybit para seleção automática

Continuação da D279, 11/11/2026. Issues #319/#517/#2.

O módulo \`j1_auto_usdt_perp\` da PR #551 já faz a classificação **offline** de contratos USDT. O novo \`scripts.scan_j1_auto_usdt_perps_once\` liga essa lógica ao cliente REST público existente (\`BoundedBybitPublicClient\`) em uma execução **owner-only, bounded, GET-only**, sem banco de dados, novas permissões, credenciais, ordens ou publicação.

A interface é de uso pessoal e desativada por padrão. Sem ambos \`--allow-public-network\` e \`--confirm-region-and-personal-research\`, retorna \`abstain\` sem GET. Por padrão só emite contagens por classe e hash. \`--include-public-symbols\` habilita mostrar somente códigos públicos; nunca valores de candles ou payloads da exchange.

Todas as páginas do catálogo \`instruments-info?category=linear&limit=1000\` seguem o cursor documentado. Cada GET é validado pelo cliente de transporte já existente: host/URL allowlist, HTTPS, limite de resposta, espaçamento e sem retry em quota/erros. A rotina limita a 20 páginas, 300s, compara relógios reais por página, rejeita repetições de cursor, duplicatas e catálogo truncado. O classificador verifica toda a cadeia antes de produzir o conjunto de **candidatos provisórios para pesquisa**.

**Separação de evidências:** resultado de uma consulta atual não comprova o catálogo de 06/11/2026, nem autentica identidade cripto só pela ausência de indicadores TradFi. Não produz ranking Top50, exige 24 candles já fechados para outro módulo e não altera o censo privado D256/D264. A API fornece candidatos à pesquisa, não allowlist operacional.

Validação: \`tests/test_j1_auto_catalog_once.py\` com transporte fake, zero chamada HTTP nos testes, suíte Linux/Windows/PAPER no head final; merge sem deploy, seguido de prova real na VPS somente se acesso operacional permitido. Nenhum comando manual de recolhimento dos 819 instrumentos deve ser solicitado para validar esta mudança.
