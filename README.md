# brief-me 📬

A hands-off **morning briefing of yesterday's inbox**, in your Mac menu bar. Action
items first (replies, decisions, deadlines), everything else summarized underneath.

It runs locally on your subscription — **no API key, no Gmail OAuth, ~$0/month.**

## How it works

```
launchd (7:05 AM + every 30 min; a missed interval fires on wake)
   └─ run.sh  (wrapper: sets PATH in-shell so `claude` resolves under launchd)
        └─ generate_brief.py --if-needed   (generates at most once per day)
             ├─ claude -p  (your subscription + your connected Gmail connector)
             │     → JSON: action_items[], rest[], counts
             ├─ writes ~/Library/Caches/brief-me/today.json   (overwritten daily; no history)
             ├─ macOS notification: "📬 Morning Brief — 2 action items • 8 others"
             └─ refreshes the SwiftBar menu bar (relaunches it if you quit it)

SwiftBar plugin (swiftbar/briefme.5m.py)  → renders the menu bar
   📬 2   ▸  ⚡ Action needed   (click an item → opens that email in Gmail)
            📥 Rest, summarized
            ✓ Mark as read   (icon → 📭)
```

The menu-bar surface needs the brief stored *somewhere* to render on each click, so
there is exactly **one cache file** (`~/Library/Caches/brief-me/today.json`) that is
**overwritten every morning** — it never builds up a history.

**Catch-up / "open the lid late":** because the Mac is usually asleep at 7:05, the job also
runs on a 30-minute interval, and launchd fires a missed interval on wake. So whenever you open
the lid, if today's brief isn't done yet (and it's past 7 AM) it generates then. `--if-needed`
guarantees only one real run (and one notification) per day; a transient post-wake network blip
is retried a few times before giving up.

## Source vs. runtime (important)

You **edit** in this repo, but the automation **runs** from a deployed copy in
`~/Library/Application Support/brief-me/`. Reason: macOS TCC privacy protection blocks
launchd background jobs (and SwiftBar) from reading `~/Documents`. `install.sh` copies the
runtime there and points launchd + SwiftBar at it. **After editing any file here, re-run
`./install.sh` to redeploy.**

## Files

| File | Role |
|------|------|
| `generate_brief.py` | Generator: calls `claude -p`, writes cache, notifies, refreshes SwiftBar. |
| `swiftbar/briefme.5m.py` | SwiftBar plugin: renders the cache into the menu bar. |
| `com.briefme.daily.plist.template` | LaunchAgent: the ~7:05 AM schedule. |
| `install.sh` | One-shot setup. |

## Install

```bash
./install.sh
```

This installs SwiftBar (via Homebrew), points it at `swiftbar/`, loads the LaunchAgent,
and runs the brief once. Look for 📬 / 📭 in the menu bar.

> Requires: the Gmail connector connected to Claude Code. Verify with
> `claude mcp list` → you should see `claude.ai Gmail … ✓ Connected`.

## Everyday use

| Want to… | Do this |
|----------|---------|
| Force a run now | `launchctl kickstart -k gui/$(id -u)/com.briefme.daily` |
| Run by hand (see output) | `/usr/bin/python3 generate_brief.py` |
| See what went wrong | `cat /tmp/briefme.log` |
| Pause it | `launchctl bootout gui/$(id -u)/com.briefme.daily` and quit SwiftBar |
| Resume it | re-run `./install.sh` |

## Customize

> After any change below, re-run `./install.sh` to redeploy the runtime.

- **Time** — edit `Hour`/`Minute` in `com.briefme.daily.plist.template`, then re-run `install.sh`.
- **Model / cost** — `MODEL` at the top of `generate_brief.py`. Default `claude-sonnet-4-6`
  (good judgment, cheap/fast). Use `claude-haiku-4-5` for even cheaper, or `claude-opus-4-8`
  for maximum nuance.
- **What counts as "action needed" / tone** — edit `PROMPT_TEMPLATE` in `generate_brief.py`.
- **Menu-bar refresh cadence** — the `5m` in `briefme.5m.py` (the generator also pushes an
  immediate refresh after each run).

## SwiftBar dependency

SwiftBar only *draws* the menu bar; it isn't the brain. The brief still generates and notifies
every morning even if SwiftBar is quit — you just won't have an icon to click until you reopen
it. `install.sh` sets SwiftBar to **launch at login**, so it's there after reboots. To stop it
entirely, quit SwiftBar and remove it from System Settings → General → Login Items.

## Troubleshooting

- **No icon** — make sure SwiftBar is running and its plugin folder is the runtime dir
  `~/Library/Application Support/brief-me/swiftbar` (SwiftBar → Preferences). Plugins must be
  executable (`install.sh` handles this). If you quit SwiftBar, reopen it (or log out/in, since
  it's a login item).
- **Icon stuck on 📭** — no fresh brief today; read `/tmp/briefme.log`. If it shows
  `No such file or directory: 'claude'`, `claude` moved (e.g. a Node upgrade) — **re-run
  `./install.sh`**, which re-discovers `claude` and regenerates the `run.sh` wrapper's PATH.
  To force a brief now: `/usr/bin/python3 ~/Library/Application\ Support/brief-me/generate_brief.py`.
- **Gmail errors** — re-check `claude mcp list`; reconnect the Gmail connector in Claude if it
  shows "Needs authentication".
