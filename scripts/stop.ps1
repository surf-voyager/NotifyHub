$projectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $projectRoot ".venv/Scripts/python.exe") -m notifyhub --config (Join-Path $projectRoot "config/local.toml") --stop
if ($LASTEXITCODE -ne 0) { throw "NotifyHub stop failed" }
