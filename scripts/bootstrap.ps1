param([switch]$Offline)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
if ($Offline) {
    & ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --no-index --find-links wheelhouse -r requirements-dev.txt
} else {
    & ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-dev.txt
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
