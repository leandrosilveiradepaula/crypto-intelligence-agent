# J5/D419 — correção do pacote offline para celular

## Defeito concreto

Na auditoria do artefato gerado pela CI sobre a versão principal D417,
o ZIP `crypto-paper-app-preview-44214273141` continha **somente cinco
arquivos**: `index.html`, `style.css`, `engine.js`,
`app.js` e `LEIA-ME.txt`.

O `index.html` usa ainda quatro scripts locais ausentes do ZIP:

- `public-market.js` (amostras de mercado);
- `persisted-paper.js` (posições PAPER);
- `research-scorebook.js` (pesquisa);
- `paper-ws-health.js` (saúde Bybit N50 e PAPER D417).

Assim, os testes da página contra o **checkout completo** do GitHub
podiam passar enquanto o ZIP entregue ao usuário ficava incompleto.
A existência de um arquivo ZIP não comprova que todos os recursos
necessários estejam nele.

## Correção do produto

O empacotamento no workflow
`.github/workflows/paper-mobile-browser-qa.yml` passa a incluir **os
nove arquivos** e, antes do upload, roda
`tests/test_j5_mobile_preview_bundle_d419.py`. O teste lê os
`src="./..."` e `href="./..."` do HTML, compara os arquivos exigidos
contra a lista exata do upload-artifact, verifica que estão presentes e
não vazios, e rejeita o antigo subconjunto de cinco arquivos. O arquivo
`LEIA-ME.txt` também enumera a lista completa.

A UI mantém somente execução **offline PAPER**, sem conta de
corretora, credenciais, preços ao vivo, ordens ou conexão automática à
VPS. Relatórios públicos N50/PAPER devem ser importados localmente.

## Aceite e evidências

- Teste de regressão reproduz o erro antigo de quatro dependências
  ausentes e comprova que a lista corrigida coincide com as dependências
  atuais do HTML.
- CI Linux/Windows e auditoria de navegador sobre SHA final exigidos
  antes do merge.
- Depois do merge, obter o novo ZIP produzido pelo workflow e **inspecionar
  realmente seu conteúdo**; somente entregar ao usuário um arquivo que
  contenha todos os nove recursos.
- Esta correção não modifica J1, motor de ordens ou serviços da VPS.
  Custo adicional R$ 0,00.
