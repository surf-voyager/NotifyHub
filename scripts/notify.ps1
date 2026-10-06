param([Parameter(Mandatory)][ValidateSet("ntfy", "speech", "windows")][string]$Method, [Parameter(Mandatory)][string]$Text, [string]$Title = "", [string]$Server = "127.0.0.1", [switch]$Wait)
$projectRoot = Split-Path $PSScriptRoot -Parent
$clientArgs = @("-m", "notifyhub.client", "--config", (Join-Path $projectRoot "config/local.toml"), "--host", $Server, "--method", $Method, "--text", $Text)
if ($Title) { $clientArgs += @("--title", $Title) }
if ($Wait) { $clientArgs += "--wait" }
& (Join-Path $projectRoot ".venv/Scripts/python.exe") @clientArgs
exit $LASTEXITCODE
