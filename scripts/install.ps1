# STARK CLIP AI - instalador Windows (uso pessoal, 100% gratis).
# Na pasta do repositorio:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1 [-Tailscale]
# Instala o que faltar via winget: Git, uv (traz o Python), Node LTS, FFmpeg, pnpm. Depois instala e compila o app.
param([switch]$Tailscale)
$ErrorActionPreference = "Stop"

function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
              [Environment]::GetEnvironmentVariable("Path", "User")
}
function Need($cmd, $id) {
  if (Have $cmd) { Write-Host "ok   $cmd" -ForegroundColor Green; return }
  if (-not (Have "winget")) { throw "winget nao encontrado: atualize o 'Instalador de Aplicativo' na Microsoft Store." }
  Write-Host "instalando $id ..." -ForegroundColor Cyan
  winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements
  Refresh-Path
  if (-not (Have $cmd)) { throw "$cmd ainda nao aparece no PATH. Feche e abra o PowerShell e rode de novo." }
}

Need git "Git.Git"
Need uv "astral-sh.uv"          # o uv baixa o Python certo sozinho
Need node "OpenJS.NodeJS.LTS"
Need ffmpeg "Gyan.FFmpeg"
if (-not (Have pnpm)) {
  try { corepack enable pnpm } catch { }
  Refresh-Path
  if (-not (Have pnpm)) { npm install -g pnpm@10; Refresh-Path }
}
if ($Tailscale) { Need tailscale "tailscale.tailscale" }

Set-Location (Split-Path -Parent $PSScriptRoot)
pnpm install
pnpm run setup
pnpm run build

Write-Host ""
Write-Host "Pronto! Para usar: duplo clique em scripts\start.cmd (ou 'pnpm start')." -ForegroundColor Green
Write-Host "Depois abra http://127.0.0.1:3000/install e clique em 'Instalar app'." -ForegroundColor Green
