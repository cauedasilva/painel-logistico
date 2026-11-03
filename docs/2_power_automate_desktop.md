# Robô RPA no Power Automate Desktop

O robô faz o que um analista faria toda manhã:

1. Obtém o relatório de pedidos do dia e atualiza a base (`rotina_diaria.bat`)
2. Lê o resumo de KPIs gerado (`dados/resumo_kpis.json`)
3. Abre o Power BI, atualiza o modelo com `scripts/refresh_pbi.ps1` (sem cliques), salva e tira um print do painel
4. Se o OTD estiver abaixo da meta, envia um alerta por e-mail com o print anexo

O Power Automate Desktop é gratuito no Windows 11. Se não estiver instalado, procure "Power Automate" na Microsoft Store.

> Os nomes das ações abaixo são os da interface em português. Se algum estiver um pouco diferente na sua versão, use a busca do painel **Ações**.

## Preparação

- Monte o `.pbix` seguindo `1_power_bi.md` e salve como `painel-logistico\PainelLogistico.pbix`
- Crie a pasta `painel-logistico\relatorios\`
- Rode `scripts\refresh_pbi.ps1` uma vez no PowerShell para instalar o módulo `SqlServer`

## Criando o fluxo

**Novo fluxo** → nome `Painel Logistico - Rotina diaria`.

### 1. Variáveis

**Definir variável**: `PastaProjeto` = `C:\Users\caued\Dev\Projetos\painel-logistico`

### 2. Atualizar a base

**Executar comando do DOS**
- Comando: `rotina_diaria.bat`
- Diretório de trabalho: `%PastaProjeto%`
- Saídas: `CommandOutput`, `CommandExitCode`

**Se** `%CommandExitCode%` *maior que* `2`
- **Exibir mensagem**: `Falha ao atualizar a base: %CommandOutput%`
- **Parar fluxo**

**Fim**

### 3. Ler os KPIs

- **Ler texto do arquivo**: `%PastaProjeto%\dados\resumo_kpis.json` → `ConteudoJson` (codificação **UTF-8**)
- **Converter JSON em objeto personalizado**: `%ConteudoJson%` → `Kpis`

A partir daqui você usa valores como `%Kpis['otd']%`, `%Kpis['alerta']%` e `%Kpis['mensagem']%`.

### 4. Atualizar o Power BI (sem clicar na tela)

1. **Executar aplicativo**: `%PastaProjeto%\PainelLogistico.pbix`
2. **Aguardar janela**: título `PainelLogistico`
3. **Definir estado da janela**: Maximizado
4. **Executar script do PowerShell** → saída `PowershellOutput`:
   ```
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PastaProjeto%\scripts\refresh_pbi.ps1"
   ```
   O script espera o modelo carregar, dispara o refresh e só devolve `OK` quando termina.
5. **Se** `%PowershellOutput%` *não começa com* `OK` → **Parar fluxo** com a mensagem `%PowershellOutput%`
6. **Janela de foco**: `PainelLogistico`
7. **Aguardar** 5 segundos (os visuais redesenham)
8. **Tirar captura de tela**: janela em primeiro plano, salvar em `%PastaProjeto%\relatorios\Painel_%DataHoje%.png`
9. **Enviar teclas** para a janela `PainelLogistico`: `{Control}({S})`
10. **Aguardar** 5 segundos (o `.pbix` termina de gravar)
11. **Fechar janela**: `PainelLogistico`
12. **Aguardar processo** `PBIDesktop` parar (tempo limite 60 s)

> Por que não usar o gravador? Cliques gravados (principalmente por imagem) quebram quando muda a resolução, a escala ou o tema do Windows. O refresh pelo motor do Power BI não depende da tela e espera o fim real da atualização.

### 5. Alerta

**Se** `%Kpis['alerta']%` *é igual a* `True`

Opção A – Outlook instalado:
- **Iniciar Outlook** → **Enviar mensagem de email por meio do Outlook**
- Para: seu e-mail · Assunto: `[Painel Logistico] %Kpis['mensagem']%`
- Corpo: OTD, OTIF, lead time, pedidos em aberto atrasados e pior transportadora (`%Kpis['pior_transportadora']['transportadora_id']%`)
- Anexo: `%PastaProjeto%\relatorios\Painel_%DataHoje%.png`

Opção B – Gmail:
- **Enviar email** (SMTP): servidor `smtp.gmail.com`, porta 587, SSL ativado, usuário seu Gmail e uma **senha de app** (Conta Google → Segurança → Senhas de app). Nunca use sua senha normal.

**Senão**
- **Gravar texto no arquivo**: `%PastaProjeto%\logs\robo.log`, com `%CurrentDateTime% OK - %Kpis['mensagem']%` (anexar)

**Fim**

### 6. Tratamento de erros

Na ação **Executar aplicativo** e no **Aguardar janela**, abra **Em caso de erro** e configure **Tentar novamente** 2 vezes. O refresh já devolve `ERRO: ...` quando falha, e o `Parar fluxo` do passo 4 mostra o motivo.

## Rodando todo dia

A versão gratuita não tem agendamento embutido. Duas saídas:

- **Rodar manualmente** para a demo (é o suficiente para o vídeo)
- **Agendador de Tarefas do Windows**: nas propriedades do fluxo no console há um link de execução (`ms-powerautomate:/console/flow/run?...`). Crie uma tarefa diária que abra esse link. Na primeira vez o Windows pede confirmação.


## Gravando a demo

O ideal é uma gravação só, com o PAD e o Power BI lado a lado:

1. Tire a ação **Definir estado da janela: Maximizado** e deixe o Power BI na metade direita da tela (Win + →) e o PAD na esquerda
2. Grave a tela inteira com a **Ferramenta de Captura** (Win + Shift + R) ou o OBS. O Win + Alt + R grava só uma janela
3. Clique em **Executar** e só pare a gravação depois que o e-mail chegar
4. Converta para GIF com o ScreenToGif ou com ffmpeg e salve em `docs/demo.gif`

