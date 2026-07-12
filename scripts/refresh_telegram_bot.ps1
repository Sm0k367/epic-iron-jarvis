# Refresh Epic Tech AI Telegram bot to the intended media-capable state.
# Safe to re-run: reloads secrets, rewires channel, rebrands profile, restarts daemon.
#
# Usage (from repo root on Windows):
#   powershell -ExecutionPolicy Bypass -File scripts\refresh_telegram_bot.ps1
#
# Prerequisites:
#   - .env has TELEGRAM_BOT_TOKEN (and ideally TELEGRAM_CHAT_ID / PIXIO_API_KEY)
#   - You have /start'ed the bot once (or pass -UserId)
#   - uv + git on PATH

[CmdletBinding()]
param(
  [string]$UserId = "",
  [switch]$SkipBrand,
  [switch]$SkipPull,
  [switch]$NoServe
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:Path = "$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\uv\bin;$env:Path"
$env:IRONJARVIS_HOME = Join-Path $Root ".ironjarvis"
$env:IRONJARVIS_INBOUND = "on"
$env:IRONJARVIS_INBOUND_INTERVAL = "3"
$env:IRONJARVIS_INBOUND_SETTLE = "2"

function Write-Step([string]$msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

# Load gitignored .env (never commit; never print values)
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
  Write-Step "Loaded .env (values not shown)"
} else {
  Write-Host "WARN: no .env — copy .env.example and set TELEGRAM_BOT_TOKEN + PIXIO_API_KEY" -ForegroundColor Yellow
}

if (-not $SkipPull) {
  Write-Step "git pull (latest media + photo-to-video fixes)"
  git pull --ff-only 2>&1 | ForEach-Object { Write-Host $_ }
}

Write-Step "uv sync"
& uv sync 2>&1 | Select-Object -Last 8

Write-Step "Load env keys into encrypted vault (pixio, telegram, xai…)"
& uv run python scripts/load_env_to_vault.py 2>&1 | ForEach-Object { Write-Host $_ }

# Wire Telegram channel (inbound + allowlist). Prefer explicit UserId, else env, else getUpdates.
Write-Step "Configure Telegram channel (inbound on)"
if ($UserId) {
  & uv run python scripts/configure_telegram.py --user-id $UserId
} elseif ($env:TELEGRAM_CHAT_ID) {
  & uv run python scripts/configure_telegram.py --user-id $env:TELEGRAM_CHAT_ID
} else {
  & uv run python scripts/configure_telegram.py --from-updates
}
$cfgCode = $LASTEXITCODE
if ($cfgCode -eq 2) {
  Write-Host @"

Telegram token is stored, but no user id yet.
1) Open your bot in Telegram and send /start
2) Re-run:  powershell -ExecutionPolicy Bypass -File scripts\refresh_telegram_bot.ps1
   or:      uv run python scripts/configure_telegram.py --from-updates

"@ -ForegroundColor Yellow
  exit 2
}
if ($cfgCode -ne 0) {
  Write-Host "configure_telegram failed (exit $cfgCode)" -ForegroundColor Red
  exit $cfgCode
}

if (-not $SkipBrand) {
  Write-Step "Brand Telegram profile (name, about, commands, photo)"
  & uv run python scripts/brand_telegram_profile.py 2>&1 | ForEach-Object { Write-Host $_ }
}

Write-Step "Doctor"
& uv run ironjarvis doctor 2>&1 | ForEach-Object { Write-Host $_ }

# Free ports so a stale daemon does not block refresh
foreach ($port in 8787, 8790) {
  foreach ($c in (netstat -ano | Select-String "LISTENING" | Select-String ":$port\s")) {
    $parts = ($c.ToString() -split "\s+") | Where-Object { $_ }
    $procId = $parts[-1]
    if ($procId -match "^\d+$") {
      Write-Host "Stopping stale PID $procId on :$port"
      Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
  }
}
Start-Sleep -Seconds 1

if ($NoServe) {
  Write-Host "Skip serve (-NoServe). Start later with scripts\start-epic-bot.ps1" -ForegroundColor Green
  exit 0
}

Write-Step "Start daemon with Telegram inbound (keep window open)"
Write-Host "  home: $env:IRONJARVIS_HOME"
Write-Host "  http://127.0.0.1:8787/health"
Write-Host "  Photo + caption 'make a video of this' → image-to-video"
Write-Host "  Text: generate an image of … → still / media"

& uv run ironjarvis serve --host 127.0.0.1 --port 8787
