$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$config = Join-Path $projectRoot "config/local.toml"
$bootstrap = Join-Path $projectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $bootstrap)) { throw "Run scripts/setup.ps1 first" }
# Read the configured interpreter instead of assuming a PATH entry.
$pythonw = & $bootstrap -c "from notifyhub.config import load; import sys; print(load(sys.argv[1])['runtime']['pythonw'])" $config
if ($LASTEXITCODE -ne 0) { throw "Invalid NotifyHub configuration" }
$quotedConfig = '"' + $config + '"'
Start-Process -FilePath $pythonw -ArgumentList @("-m", "notifyhub", "--config", $quotedConfig) -WindowStyle Hidden
