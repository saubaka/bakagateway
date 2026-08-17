$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$env:CLOUD_GATEWAY_ENV = "development"
& ".venv\Scripts\python.exe" -m flask --app wsgi:app db upgrade
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ".venv\Scripts\python.exe" -m flask --app wsgi:app run --host 127.0.0.1 --port 5100 --debug
