# Run from an elevated PowerShell. Limit sources to trusted peers.
param([Parameter(Mandatory)][string[]]$RemoteAddress, [string]$InterfaceAlias = "", [int]$Port = 39393, [switch]$Remove)
$ErrorActionPreference = "Stop"
$name = "NotifyHub-UDP"
if ($Remove) { Remove-NetFirewallRule -Name $name -ErrorAction SilentlyContinue; return }
$rule = @{Name=$name; DisplayName="NotifyHub UDP"; Direction="Inbound"; Action="Allow"; Protocol="UDP"; LocalPort=$Port; RemoteAddress=$RemoteAddress; Profile="Any"}
if ($InterfaceAlias) { $rule.InterfaceAlias = $InterfaceAlias }
if (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue) { Remove-NetFirewallRule -Name $name }
New-NetFirewallRule @rule
