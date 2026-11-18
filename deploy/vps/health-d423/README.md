# D423 — candidato de agendamento N50 público e painel local na VPS

**Os arquivos nesta pasta são SOMENTE templates. Não foram instalados,
ativados ou publicados.** A integração de código não autoriza release.

## Progresso real por trás do candidato

- D418, D420 e D421 receberam cotações de 50 contratos na Bybit V5 pública
  em sessões finitas owner. O segundo ciclo D421 real observou 50/50
  instrumentos, com 49/50 frescos no encerramento e um expirado.
- D422 comprovou a integração local ponta a ponta com outra sessão real:
  12.545 ticker callbacks, 43/50 frescos no final, 7 expirados, arquivo
  owner 0600, leitura HTTP 200 restrita a 127.0.0.1, temporários removidos.
- A validação de 24 horas consecutivas da J1 ainda não foi homologada,
  e o monitor D421 ainda não constitui um serviço 24×7 comprovado.

## Objetivo destes templates

`cia-j2-n50-health.service` executa **uma** sessão D421 de 60 s por vez,
reaproveitando a epoch owner ativa J1 somente leitura, escrevendo apenas
`/home/cia-probe/agent/j5-n50-health-private/latest-n50-public-health.json`.
Status 2 é esperado para cobertura final parcial; não é sucesso de entradas.

`cia-j2-n50-health.timer` agenda novas sessões após a conclusão da anterior
e tem calendário de recuperação. É preciso comprovar a convivência de CPU
e rede com o serviço horário J1, sem reiniciar ou reconfigurar a J1.
Risco de sobreposição interprocessos é limitado pelo lock D421.

`cia-j5-health-loopback.service` serve o HTML e resumo local com
`scripts.serve_j5_local_readonly`, exclusivamente em 127.0.0.1:8765
e com checagem de Host/Origin, sem CORS e sem POST. É uma fonte de
leitura local, **não um site acessível pelo celular fora da VPS**.

## Gate obrigatório ANTES de instalar ou habilitar

1. Aprovação explícita de release de pesquisa/monitoramento somente
   leitura na VPS. Nunca inferir aprovação a partir de merge.
2. Fixar SHA aprovado da versão principal do GitHub; baixar fonte
   imutável e conferir SHA/revisão/CI Linux+Windows+Chrome; instalar o
   código numa pasta `j5-health-release` que não seja symlink e não
   possa ser alterada pelo usuário do serviço. Nunca executar código
   `main` mutável em modo root.
3. Conferir N50 owner ativo, DAC e integridade, agendamentos J1
   existentes, capacidade CPU/memória e ausência de serviço concorrente.
   Preparar diretório `j5-n50-health-private` proprietário `0700`.
   Não conceder acesso ao journal J1 como escritor.
4. Validar `systemd-analyze verify`, executar piloto oneshot e 3+ ciclos
   sob telemetria. Simular queda de rede, epoch rotacionada, stall, status
   expirado e lock concorrente; verificar 503 quando a amostra vence.
5. Confirmar que os templates não alteram unidades J1, portas públicas
   80/443, proxy Traefik existente, firewall, DNS, SSH, contas, ou ordens.
   Liberar **somente** os serviços de pesquisa permitidos pelo gate.
6. Para acesso pelo celular é necessário desenho separado de HTTPS,
   autenticação, privacidade e controle de origem. Não expor 8765
   publicamente nem usar proxy sem autenticação por conveniência.

## Reversão e critérios de aceite

Parar/desabilitar **somente** as unidades D423 se e quando forem
instaladas, preservando os arquivos privados, a coleta J1 e as evidências;
remover o acesso remoto se houver gate futuro de publicação. O dashboard
deve mostrar indisponibilidade quando não há arquivo recente, e nunca
afirmar stop real, 24×7 homologado ou sinal aprovado.

Custo adicional R$ 0,00. Nenhum serviço criado pela leitura deste arquivo.
