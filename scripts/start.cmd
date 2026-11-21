@echo off
rem STARK CLIP AI - inicia motor + worker + painel e abre o navegador (Windows, duplo clique).
cd /d "%~dp0.."
start "" cmd /c "timeout /t 12 >nul & start http://127.0.0.1:3000"
pnpm start
