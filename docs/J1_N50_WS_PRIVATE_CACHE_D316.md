# J1/D316 — cache owner imutável dos metadados WS dinâmicos D314

Referências: #585, #429, #319; depende da ponte D315.

## Necessidade

O D314 entrega em memória uma admissão provisória de exatamente 50
contratos do manifesto D287. Reconsultar o catálogo V5 a cada lease WS
mudaria o digest e poderia invalidar o journal histórico e aumentar GETs.
O D316 guarda a **mesma prova causal** e permite revalidá-la sem HTTP.

## Contrato implementado

`crypto_intelligence_agent.j1_n50_ws_private_cache` fornece:

- `cache_n50_ws_dynamic_admission_once`: com opt-in, dono POSIX não-root,
  diretório pré-existente 0700 e caminho fixo, valida a cópia canônica de
  manifesto D287, páginas D314, cadeia de cursores, horários de recepção e
  selecionados 50 antes de qualquer escrita. Usa `O_EXCL|O_NOFOLLOW`,
  arquivo 0600, `fsync` e limite de 8 MiB. Não sobrescreve nem apaga
  cache antigo, inclusive quando parcial/corrompido.
- `load_n50_ws_dynamic_admission`: com opt-in read-only, valida dono,
  permissões/inode/hardlinks, bytes canônicos, JSON sem chaves duplicadas,
  hash de payload, digest de ranking corrente fornecido pelo owner, TTL
  máximo 48h e replay completo pelo **mesmo** `admit_dynamic_n50_ws_scope`
  D314. Sem refresh automático ou GET, sem inserir novo ticker. Se não
  corresponder ao manifesto D287 **ativo**, abstém-se.
- `N50WSPrivateAdmission`: o objeto tipado mantém símbolos/metadados
  somente nos campos privados ocultos no `repr`. O relatório sanitizado
  contém exclusivamente status, contagens, digests e flags de segurança.

O contrato guarda páginas completas já fornecidas pelo chamador em arquivo
privado, não no GitHub nem em logs públicos. O digest dá integridade contra
corrupção, **não** autenticidade criptográfica do provedor ou comprovação
independente de que um símbolo representa criptomoeda.

Nenhuma função abre socket, envia HTTP, altera o journal REST HALT, cria
systemd, habilita trading ou envia ordens. `load` é um pré-requisito para
futura lease owner D315: o journal WS continua separado e limitado por
flock/epoch; não combinar digest D316 antigo com outro manifesto atual.

## Testes e gates

`tests/test_j1_n50_ws_private_cache_d316.py` testa gravação/leitura de
uma captura única (50 membros), reprodução exata dos metadados, ligação D313
com 50 candles WS sintéticos após reload, ausência de novas requisições,
tentativa de sobrescrita, metadados TradFi, expiração >48h, coorte D287
diferente, bytes adulterados, diretório inseguro, symlink e sanitização
sem símbolos. Positivos owner POSIX são skipped deliberadamente em Windows.
Suite Linux/docs, Windows/offline e Chrome/PAPER SHA final + revisão antes
de merge sem release.

## Ainda falta para N50 real

O próximo bloco da #585 terá de ligar o manifesto D287 **já selado**, a
captura pública D314 de uma única janela, o cache D316, a lease WS D315 e
o journal privado do próprio epoch em um runner owner supervisionado.
O serviço deverá manter assinatura antes do fechamento, evitar novos
GETs horários, registrar 50/49 e corrigir gaps por REST somente com quota e
proveniência própria. Qualquer cutover de unidades N2/N50/fallback é release
de produção separado; N50 REST 10006 continua OFF e N2 ativo até gate.
24 horas reais, rotação >=36h e verificação crypto-only #319 continuam
pendentes. Custo adicional R$0, nenhuma ordem real.
