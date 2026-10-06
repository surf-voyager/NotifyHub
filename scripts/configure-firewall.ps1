$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$report = Join-Path $projectRoot "reports/local-firewall.json"
New-Item -ItemType Directory -Path (Split-Path $report -Parent) -Force | Out-Null
try {
    $python = Join-Path $projectRoot ".venv/Scripts/python.exe"
    $config = Join-Path $projectRoot "config/local.toml"
    $configCode = "from notifyhub.config import load; import sys,json; c=load(sys.argv[1]); print(json.dumps({'port':c['udp']['port'],'rules':c.get('firewall',{}).get('rules',[])}))"
    $settings = (& $python -c $configCode $config) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Invalid NotifyHub configuration" }
    foreach ($rule in $settings.rules) {
        if (-not $rule.name.StartsWith("NotifyHub-") -or -not $rule.remote_addresses -or -not $rule.interface_alias) { throw "Firewall rules require NotifyHub name, interface and explicit remote addresses" }
        & (Join-Path $PSScriptRoot "firewall.ps1") -Name $rule.name -RemoteAddress $rule.remote_addresses -InterfaceAlias $rule.interface_alias -Port $settings.port | Out-Null
    }
    @{success=$true; names=@($settings.rules | ForEach-Object {$_.name}); time=(Get-Date).ToString("o")} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
} catch {
    @{success=$false; error=$_.Exception.Message; time=(Get-Date).ToString("o")} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
    throw
}
