#!/usr/bin/env bash
# Clipzou em segundo plano: liga sozinho com o PC, reinicia se cair e se atualiza sozinho do GitHub.
# Uso: bash scripts/service.sh install [--now] | uninstall | status
cd "$(dirname "$0")/.." || exit 1
ROOT="$PWD"
UNIT="$HOME/.config/systemd/user/clipzou.service"
PLIST="$HOME/Library/LaunchAgents/ai.clipzou.plist"
AUTOSTART="$HOME/.config/autostart/clipzou.desktop"
URL="http://127.0.0.1:3000"
export PNPM_HOME="${PNPM_HOME:-$HOME/.local/share/pnpm}"
export PATH="$HOME/.local/bin:$PNPM_HOME:$HOME/Library/pnpm:$PATH"
has_systemd() { command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; }
healthy() { curl -fs "$URL/api/engine/health" >/dev/null 2>&1; }
dir_of() { local p; p=$(command -v "$1" 2>/dev/null) && dirname "$p"; }
# PATH do serviço: onde estão node, pnpm, uv e ffmpeg agora (inclui nvm/pnpm env).
SVC_PATH="$(for t in node pnpm uv ffmpeg git curl; do dir_of "$t"; done | awk '!s[$0]++' | paste -sd: -)"
SVC_PATH="${SVC_PATH:+$SVC_PATH:}$HOME/.local/bin:$PNPM_HOME:/usr/local/bin:/usr/bin:/bin"

wait_ready() {
  for _ in $(seq 1 90); do healthy && return 0; sleep 2; done
  echo "aviso: o Clipzou ainda não respondeu; veja: bash scripts/service.sh status" >&2
}

case "${1:-install}" in
  install)
    if [ "$(uname)" = "Darwin" ]; then
      mkdir -p "$(dirname "$PLIST")" "$HOME/Library/Logs"
      cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ai.clipzou</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$ROOT/scripts/start.sh</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict>
    <key>STARK_SERVICE</key><string>1</string><key>PATH</key><string>$SVC_PATH</string>
  </dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/><key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/clipzou.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/clipzou.log</string>
</dict></plist>
EOF
      if [ "${2:-}" = "--now" ]; then
        launchctl unload "$PLIST" 2>/dev/null; launchctl load -w "$PLIST" && wait_ready
      fi
    elif has_systemd; then
      mkdir -p "$(dirname "$UNIT")"
      cat > "$UNIT" <<EOF
[Unit]
Description=Clipzou - radar ao vivo e cortes prontos
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=STARK_SERVICE=1
Environment=PATH=$SVC_PATH
ExecStart=/bin/bash $ROOT/scripts/start.sh
Restart=always
RestartSec=10
TimeoutStopSec=40

[Install]
WantedBy=default.target
EOF
      systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY DBUS_SESSION_BUS_ADDRESS 2>/dev/null
      systemctl --user daemon-reload
      systemctl --user enable clipzou.service >/dev/null 2>&1
      rm -f "$AUTOSTART"
      if [ "${2:-}" = "--now" ]; then
        systemctl --user restart clipzou.service && wait_ready
      fi
    else  # sem systemd: liga no login da sessão gráfica (sem reinício automático)
      mkdir -p "$(dirname "$AUTOSTART")"
      cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Clipzou (segundo plano)
Exec=env STARK_SERVICE=1 bash "$ROOT/scripts/start.sh"
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
EOF
      if [ "${2:-}" = "--now" ] && ! healthy; then
        (STARK_SERVICE=1 nohup bash "$ROOT/scripts/start.sh" >"$ROOT/services/engine/clipzou.log" 2>&1 &)
        wait_ready
      fi
    fi
    echo "✔ Clipzou em segundo plano: liga com o PC e se atualiza sozinho."
    ;;
  uninstall)
    if [ "$(uname)" = "Darwin" ]; then launchctl unload -w "$PLIST" 2>/dev/null; rm -f "$PLIST"
    elif has_systemd; then systemctl --user disable --now clipzou.service 2>/dev/null; rm -f "$UNIT"; systemctl --user daemon-reload
    fi
    rm -f "$AUTOSTART"
    echo "Serviço removido (o Clipzou só liga quando você abrir)."
    ;;
  status)
    if [ "$(uname)" = "Darwin" ]; then launchctl list | grep ai.clipzou; tail -n 30 "$HOME/Library/Logs/clipzou.log"
    elif has_systemd; then systemctl --user status clipzou.service --no-pager; journalctl --user -u clipzou -n 40 --no-pager
    fi
    healthy && echo "✔ respondendo em $URL" || echo "✗ não responde em $URL"
    ;;
  *) echo "uso: bash scripts/service.sh install [--now] | uninstall | status" >&2; exit 2 ;;
esac
