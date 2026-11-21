@echo off
rem STARK CLIP AI - atualiza do GitHub, liga motor + worker + painel e abre o navegador (Windows, duplo clique).
cd /d "%~dp0.."
set GIT_TERMINAL_PROMPT=0
for /f %%i in ('git rev-parse HEAD') do set OLD=%%i
git pull --ff-only -q
for /f %%i in ('git rev-parse HEAD') do set NEW=%%i
if not "%OLD%"=="%NEW%" (
  echo Versao nova baixada. Atualizando...
  call pnpm install
  call pnpm run setup
  call pnpm run build
)
start "" cmd /c "timeout /t 12 >nul & start http://127.0.0.1:3000"
pnpm start
