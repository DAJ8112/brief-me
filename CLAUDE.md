# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`brief-me` is a macOS automation that, every morning, summarizes **yesterday's Gmail inbox**
(action items first, the rest grouped) and surfaces it in a SwiftBar menu-bar dropdown. It has
no build system, package manager, or test suite — it's a few Python scripts, a LaunchAgent plist
template, and a bash installer.

## Critical architectural fact: source vs. runtime

**You edit in this repo, but the automation runs from a deployed copy in
`~/Library/Application Support/brief-me/`.** macOS TCC privacy protection blocks launchd
background jobs (and SwiftBar) from reading `~/Documents`, so the runtime must live outside it.

**After editing `generate_brief.py` or `swiftbar/briefme.5m.py`, you must run `./install.sh` to
redeploy** — editing the repo file alone changes nothing about what runs. This is the #1 thing
to get wrong.

## The pipeline (requires reading multiple files to see)

```
launchd (com.briefme.daily; 7:05 AM + StartInterval 1800s; a missed interval fires on wake)
  → run.sh  (generated wrapper: exports PATH, then runs generate_brief.py --if-needed)
      → generate_brief.py
          • --if-needed: skip if already generated today, or before 07:00 (≤1 real run/day)
          • claude -p --output-format json --allowedTools mcp__claude_ai_Gmail__search_threads,...
            (runs on the user's Claude subscription + the connected Gmail MCP connector — NO API key)
          • run_claude() retries transient failures (post-wake Wi-Fi lag) ~3x with backoff
          • parses JSON out of the result (model may prepend prose; extract first {…last })
          • writes ~/Library/Caches/brief-me/today.json   (single file, overwritten daily, no history)
          • osascript notification + `open swiftbar://refreshplugin?name=briefme`
  → swiftbar/briefme.5m.py  reads today.json and renders the menu bar
```

**Critical launchd gotcha:** launchd does NOT reliably apply the plist's `EnvironmentVariables`
PATH, so a job that resolves `claude` via `shutil.which` (PATH-dependent) fails with
`No such file or directory: 'claude'`. That's why the LaunchAgent runs through **`run.sh`**,
which `export`s PATH in-shell first. `install.sh` generates `run.sh` with the install-time
`claude` bin dir. If `claude` moves (Node upgrade), re-run `./install.sh`.

`today.json` is the **contract** between the writer (`generate_brief.py`) and the reader
(`swiftbar/briefme.5m.py`): keys `date`, `action_items[]` (`title`/`sender`/`gmail_url`),
`rest[]` (`summary`), `counts`, `generated_at`, `read`. Change the shape in one place → change it
in both.

Key design choices baked into the code:
- **Subscription, not API.** Summarization is `claude -p` (headless Claude Code) using
  `--allowedTools` scoped to Gmail read tools — least privilege, no `--dangerously-skip-permissions`.
- **`open swiftbar://…` relaunches SwiftBar if it's quit**, so the menu bar self-heals each
  morning even if the user quit it.
- **Untrusted email content is sanitized for the menu**: `clean()` in the plugin replaces `|`
  (SwiftBar's param delimiter) and newlines, so a maliciously-titled email can't inject a menu
  action.

## Common commands

```bash
./install.sh                                          # deploy/redeploy + (re)load agent + run once
/usr/bin/python3 generate_brief.py                    # run the generator by hand (writes the cache)
/usr/bin/python3 swiftbar/briefme.5m.py               # print the menu-bar render (debug the plugin)
/usr/bin/python3 swiftbar/briefme.5m.py --mark-read   # flip the read flag in the cache
launchctl kickstart -k gui/$(id -u)/com.briefme.daily # force the scheduled job to run now
cat /tmp/briefme.log                                  # generator stdout/stderr (launchd buffers until exit)
launchctl bootout gui/$(id -u)/com.briefme.daily      # pause the schedule
claude mcp list                                       # must show `claude.ai Gmail … ✓ Connected`
```

There are no automated tests. Verify end-to-end by running `generate_brief.py`, checking
`~/Library/Caches/brief-me/today.json`, and rendering the plugin. Sanity-check edits with
`bash -n install.sh` and `python3 -m py_compile generate_brief.py swiftbar/briefme.5m.py`.

## Where to change behavior

- **What's "action needed" / tone / output** → `PROMPT_TEMPLATE` in `generate_brief.py`
  (date tokens are substituted with `str.replace`, not `.format`, so the JSON-schema braces survive).
- **Model / cost** → `MODEL` constant in `generate_brief.py` (default `claude-sonnet-4-6`).
- **Schedule** → `Hour`/`Minute` in `com.briefme.daily.plist.template`, then `./install.sh`.

## Portability / publishing constraints

This repo is meant to be public and machine-agnostic — keep it that way:
- **No hardcoded `/Users/<name>` paths or personal names.** The `claude` binary is resolved via
  `shutil.which("claude")`; the plist is a **template** (`com.briefme.daily.plist.template`) whose
  `__HOME__` / `__RUNTIME_DIR__` / `__NODE_BIN__` placeholders are filled in by `install.sh` at
  install time (the generated plist is written to `~/Library/LaunchAgents/`, never committed).
- The label is the neutral `com.briefme.daily`.
