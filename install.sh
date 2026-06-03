#!/bin/bash
# brief-me installer / deployer.
#
# Source lives in this repo (edit here); the RUNTIME is deployed to
# ~/Library/Application Support/brief-me because macOS TCC blocks launchd
# background jobs (and would block SwiftBar) from reading ~/Documents.
# Re-run this after editing any source file to redeploy.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$HOME/Library/Application Support/brief-me"
PLUGIN_DIR="$RUNTIME_DIR/swiftbar"
LABEL="com.briefme.daily"
TEMPLATE="$PROJECT_DIR/$LABEL.plist.template"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

echo "==> brief-me install"
echo "    source:  $PROJECT_DIR"
echo "    runtime: $RUNTIME_DIR"

# 1. Deploy runtime out of the TCC-protected ~/Documents -----------------
mkdir -p "$PLUGIN_DIR"
cp "$PROJECT_DIR/generate_brief.py" "$RUNTIME_DIR/"
cp "$PROJECT_DIR/swiftbar/"*.py "$PLUGIN_DIR/"
chmod +x "$RUNTIME_DIR/generate_brief.py" "$PLUGIN_DIR/"*.py
echo "    deployed runtime files."

# 2. SwiftBar -------------------------------------------------------------
if [ -d "/Applications/SwiftBar.app" ] || brew list --cask swiftbar >/dev/null 2>&1; then
    echo "    SwiftBar already installed."
else
    echo "    Installing SwiftBar via Homebrew..."
    brew install --cask swiftbar
fi
defaults write com.ameba.SwiftBar PluginDirectory "$PLUGIN_DIR"
defaults write com.ameba.SwiftBar makePluginExecutable -bool YES
echo "    SwiftBar plugin folder -> $PLUGIN_DIR"

# Auto-start SwiftBar at login so the menu bar is present every morning
# (the brief still generates without it; this just keeps the display up).
if osascript -e 'tell application "System Events" to if not (exists login item "SwiftBar") then make login item at end with properties {path:"/Applications/SwiftBar.app", hidden:false}' >/dev/null 2>&1; then
    echo "    SwiftBar set to launch at login."
else
    echo "    (couldn't set login item automatically — enable in SwiftBar → Preferences → Launch at Login)"
fi

# 3. Generate the wrapper + plist, then (re)load the LaunchAgent ---------
mkdir -p "$HOME/Library/LaunchAgents"
CLAUDE_BIN="$(command -v claude || true)"
if [ -z "$CLAUDE_BIN" ]; then
    echo "ERROR: 'claude' not found on PATH. Open a shell where 'claude --version' works, then re-run."
    exit 1
fi
NODE_BIN="$(dirname "$CLAUDE_BIN")"

# Wrapper sets PATH in-shell — launchd does not reliably apply the plist's
# EnvironmentVariables PATH, so generate_brief.py couldn't resolve `claude`.
# --if-needed makes catch-up runs no-ops once the day's brief exists.
cat > "$RUNTIME_DIR/run.sh" <<EOF
#!/bin/bash
export PATH="$NODE_BIN:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
exec /usr/bin/python3 "$RUNTIME_DIR/generate_brief.py" --if-needed
EOF
chmod +x "$RUNTIME_DIR/run.sh"
echo "    wrote wrapper run.sh (PATH includes $NODE_BIN)."

sed -e "s|__HOME__|$HOME|g" \
    -e "s|__RUNTIME_DIR__|$RUNTIME_DIR|g" \
    -e "s|__NODE_BIN__|$NODE_BIN|g" \
    "$TEMPLATE" > "$PLIST_DST"

launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST_DST"
echo "    LaunchAgent loaded ($LABEL)."

# 4. First run now + launch SwiftBar -------------------------------------
echo "==> Generating today's brief once now..."
/usr/bin/python3 "$RUNTIME_DIR/generate_brief.py" || echo "    (first run failed — see /tmp/briefme.log)"
echo "==> Launching SwiftBar..."
open -a SwiftBar || true

cat <<EOF

Done. Look for 📬 / 📭 in your menu bar.

  • Force a run:  launchctl kickstart -k gui/$UID_NUM/$LABEL
  • Logs:         /tmp/briefme.log
  • Pause:        launchctl bootout gui/$UID_NUM/$LABEL   (and quit SwiftBar)
  • After edits:  re-run ./install.sh to redeploy

If SwiftBar shows a folder picker on first launch, choose:
  $PLUGIN_DIR
EOF
