$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
& ".venv\Scripts\python.exe" -m flask --app wsgi:app db upgrade
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ".venv\Scripts\python.exe" -m flask --app wsgi:app init-db
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ".venv\Scripts\python.exe" -m flask --app wsgi:app create-admin
