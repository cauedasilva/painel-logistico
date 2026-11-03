@echo off
REM Rotina diaria: obtem o relatorio do dia e atualiza a base do Power BI.
REM Codigo de saida: 0 = OK, 2 = OK com alerta de KPI, outro = erro.
cd /d "%~dp0"
if not exist "dados\fato_pedidos.csv" (
    python gerar_dados.py --historico || exit /b 1
) else (
    python gerar_dados.py --dia || exit /b 1
)
python processar.py
exit /b %ERRORLEVEL%
