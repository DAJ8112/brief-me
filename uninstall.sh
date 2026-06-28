#!/bin/bash
# brief-me uninstaller — the inverse of install.sh.
#
# Removes everything install.sh sets up: the LaunchAgent, its plist, the deployed
# runtime, the cache, the log, and the SwiftBar login item. Best-effort: a piece
# that's already gone won't abort the rest.
#
# Deliberately LEFT IN PLACE: the SwiftBar app (a general menu-bar tool you may use
# for other plugins), this source repo, and your Claude subscription + Gmail connector.
set -uo pipefail  # NOT -e: keep cleaning up even if a step finds nothing to remove.

RUNTIME_DIR="$HOME/Library/Application Support/brief-me"
CACHE_DIR="$HOME/Library/Caches/brief-me"
LABEL="com.briefme.daily"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="/tmp/briefme.log"
UID_NUM="$(id -u)"

echo "==> brief-me uninstall"

# 1. Stop & unload the LaunchAgent ---------------------------------------
if launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null; then
    echo "    unloaded LaunchAgent $LABEL."
else
    echo "    LaunchAgent not loaded (nothing to unload)."
fi

# 2. Remove the generated plist ------------------------------------------
if [ -e "$PLIST_DST" ]; then
    rm -f "$PLIST_DST" && echo "    removed $PLIST_DST"
else
    echo "    no plist at $PLIST_DST"
fi

# 3. Remove the deployed runtime (incl. run.sh) --------------------------
if [ -d "$RUNTIME_DIR" ]; then
    rm -rf "$RUNTIME_DIR" && echo "    removed runtime $RUNTIME_DIR"
else
    echo "    no runtime dir at $RUNTIME_DIR"
fi

# 4. Remove the cache (today.json, last_error.json) ----------------------
if [ -d "$CACHE_DIR" ]; then
    rm -rf "$CACHE_DIR" && echo "    removed cache $CACHE_DIR"
else
    echo "    no cache dir at $CACHE_DIR"
fi

# 5. Remove the log ------------------------------------------------------
if [ -e "$LOG" ]; then
    rm -f "$LOG" && echo "    removed $LOG"
else
    echo "    no log at $LOG"
fi

# 6. Remove the SwiftBar login item install.sh added ---------------------
#    (the SwiftBar app itself stays installed.)
if osascript -e 'tell application "System Events" to if (exists login item "SwiftBar") then delete login item "SwiftBar"' >/dev/null 2>&1; then
    echo "    removed SwiftBar login item (if it was present)."
else
    echo "    (couldn't remove SwiftBar login item — remove it in System Settings → General → Login Items if needed)"
fi

cat <<EOF

Done. brief-me removed.

Left in place on purpose:
  • SwiftBar.app                 — quit it & uninstall separately if you don't use it elsewhere
  • this source repo             — delete the folder yourself if you're done with it
  • Claude subscription + Gmail connector

Note: SwiftBar's saved plugin-folder setting may still point at the now-removed
  $RUNTIME_DIR/swiftbar
If SwiftBar still shows an old icon, quit & reopen it, or update the folder in
SwiftBar → Preferences.
EOF
