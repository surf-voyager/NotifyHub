param([string]$PythonExecutable = "python", [string]$Topic = "", [string]$DataDir = "", [switch]$NoRegister)
$ErrorActionPreference = "Stop"
$setupArgs = @((Join-Path $PSScriptRoot "setup.py"))
if ($Topic) { $setupArgs += @("--topic", $Topic) }
if ($DataDir) { $setupArgs += @("--data-dir", $DataDir) }
if ($NoRegister) { $setupArgs += "--no-register" }
& $PythonExecutable @setupArgs
if ($LASTEXITCODE -ne 0) { throw "NotifyHub setup failed: $LASTEXITCODE" }
