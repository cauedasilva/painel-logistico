# refresh_pbi.ps1
# Atualiza (refresh) o modelo do .pbix que esta aberto no Power BI Desktop,
# sem cliques: conecta no motor Analysis Services local que o Desktop abre.
# Saida: "OK" em caso de sucesso, "ERRO: ..." em caso de falha (exit 1).

param([int]$TimeoutSeg = 180)
$ErrorActionPreference = 'Stop'

try {
    # Modulo com o Invoke-ASCmd (instala uma unica vez, por usuario)
    if (-not (Get-Module -ListAvailable -Name SqlServer)) {
        Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force | Out-Null
        Install-Module SqlServer -Scope CurrentUser -Force -AllowClobber
    }
    Import-Module SqlServer -DisableNameChecking

    $limite = (Get-Date).AddSeconds($TimeoutSeg)
    $server = $null
    $db = $null

    # Espera o Power BI subir o modelo e descobre porta + nome do banco
    while (-not $db) {
        if ((Get-Date) -gt $limite) { throw "Tempo esgotado esperando o modelo do Power BI carregar." }
        Start-Sleep -Seconds 3

        $bases = @(
            "$env:LOCALAPPDATA\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces",
            "$env:USERPROFILE\Microsoft\Power BI Desktop Store App\AnalysisServicesWorkspaces"
        ) | Where-Object { Test-Path $_ }
        if (-not $bases) { continue }

        $portFile = $bases |
            ForEach-Object { Get-ChildItem $_ -Filter 'msmdsrv.port.txt' -Recurse -ErrorAction SilentlyContinue } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if (-not $portFile) { continue }

        $port = (Get-Content $portFile.FullName -Encoding Unicode -Raw).Trim()
        $server = "localhost:$port"

        try {
            $xml = Invoke-ASCmd -Server $server -Query 'SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS'
            if ($xml -match '<CATALOG_NAME>([^<]+)</CATALOG_NAME>') { $db = $Matches[1] }
        } catch {
            # motor ainda iniciando; tenta de novo
        }
    }

    # Refresh completo do modelo (relê todas as fontes, ex.: resumo_kpis.json)
    $tmsl = '{"refresh":{"type":"full","objects":[{"database":"' + $db + '"}]}}'
    $res = Invoke-ASCmd -Server $server -Query $tmsl
    if ($res -match '<Error\b') { throw "Falha no refresh: $res" }

    Write-Output "OK"
    exit 0
}
catch {
    Write-Output "ERRO: $($_.Exception.Message)"
    exit 1
}
