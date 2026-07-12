# Start Epic Tech AI daemon with Telegram inbound (always-on for @EpicTechAI_bot)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start-epic-bot.ps1
#
# Prefer scripts\refresh_telegram_bot.ps1 after a git pull to rewire channel + brand.
# This script only starts the daemon (loads .env + vault-friendly env).

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:Path = "$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\uv\bin;$env:Path"
$env:IRONJARVIS_HOME = Join-Path $Root ".ironjarvis"
$env:IRONJARVIS_INBOUND = "on"
$env:IRONJARVIS_INBOUND_INTERVAL = "3"
$env:IRONJARVIS_INBOUND_SETTLE = "2"

# Load gitignored .env (never commit)
$envFile = Join-Path $Root ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $i = $line.IndexOf("=")
    if ($i -lt 1) { return }
    $k = $line.Substring(0, $i).Trim()
    $v = $line.Substring($i + 1).Trim().Trim("'").Trim('"')
    if ($k) { Set-Item -Path "Env:$k" -Value $v }
  }
}

# Free port 8787 if stale
foreach ($c in (netstat -ano | Select-String "LISTENING" | Select-String ":8787")) {
  $parts = ($c.ToString() -split "\s+") | Where-Object { $_ }
  $procId = $parts[-1]
  if ($procId -match "^\d+$") {
    Write-Host "Stopping stale process $procId on :8787"
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
  }
}
Start-Sleep -Seconds 1

Write-Host "Epic Tech AI daemon + Telegram inbound"
Write-Host "  home: $env:IRONJARVIS_HOME"
Write-Host "  http://127.0.0.1:8787"
Write-Host "  Media: text generate / photo+caption video"
Write-Host "  Keep this window open (or run minimized)."

& uv run ironjarvis serve --host 127.0.0.1 --port 8787
