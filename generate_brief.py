#!/usr/bin/python3
"""brief-me: generate a morning inbox brief from YESTERDAY's Gmail.

Runs Claude Code headless (`claude -p`) on your existing subscription, using your
already-connected Gmail connector (no API key, no Gmail OAuth). Writes a single,
daily-overwritten cache file that the SwiftBar menu-bar plugin renders, fires a
macOS notification, and refreshes the menu bar.

Invoked by the LaunchAgent (~7 AM / on next wake) and runnable by hand for testing:
    /usr/bin/python3 generate_brief.py
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import time

# --- configuration ---------------------------------------------------------
HOME = os.path.expanduser("~")
# Resolved from PATH — the LaunchAgent's plist sets PATH to include the node/claude
# bin dir. Override with BRIEFME_CLAUDE_BIN if your setup differs.
CLAUDE = os.environ.get("BRIEFME_CLAUDE_BIN") or shutil.which("claude") or "claude"
# Sonnet: good action-item judgment, ~5x cheaper/faster than Opus.
# Set to "claude-haiku-4-5" to go cheaper, or "" to use the CLI default.
MODEL = "claude-sonnet-4-6"
ALLOWED_TOOLS = "mcp__claude_ai_Gmail__search_threads,mcp__claude_ai_Gmail__get_thread"
TIMEOUT_SECONDS = 300

CACHE_DIR = os.path.join(HOME, "Library", "Caches", "brief-me")
CACHE = os.path.join(CACHE_DIR, "today.json")
# Sidecar marker written when a run fails, removed on the next success. Lets the
# menu bar distinguish "today's run failed" from "today's run hasn't happened yet"
# without clobbering the last good brief in today.json.
ERROR_FILE = os.path.join(CACHE_DIR, "last_error.json")
PLUGIN_NAME = "briefme"  # SwiftBar plugin base name (briefme.5m.py)

# Date tokens are substituted by str.replace (NOT .format) so the JSON braces
# in the schema below survive untouched.
PROMPT_TEMPLATE = r"""You are generating a "morning inbox brief" from my Gmail. Today is __TODAY_ISO__; summarize YESTERDAY's inbox (__YDAY_ISO__).

Steps:
1. Use the Gmail search_threads tool with query: in:inbox after:__YDAY_SLASH__ before:__TODAY_SLASH__
   Page through results (pageSize 50) until you have covered all of yesterday's inbox threads.
2. For any thread that plausibly needs MY action -- a reply, a decision, a deadline, an interview/assessment, an account/security action, or anything time-sensitive -- use get_thread on its thread id to read enough to describe what's needed. Skip get_thread for obvious low-value mail (promotions, job-board digests, newsletters, automated "application received/rejected" notices).
3. Produce the brief.

Your ENTIRE response must be a single JSON object. Do not write anything before the opening { or after the closing }. No prose, no greetings, no markdown code fences. Schema:
{
  "date": "__YDAY_ISO__",
  "action_items": [
    {"title": "<short, specific: include the deadline / what's needed>",
     "sender": "<email or name>",
     "gmail_url": "https://mail.google.com/mail/u/0/#all/<messageId>"}
  ],
  "rest": [
    {"summary": "<one concise line; group similar items, e.g. '3 job-board digests (ZipRecruiter, Adzuna, Alignerr)'>",
     "gmail_url": "<optional: #all/<messageId> deep link if this line is ONE message; omit for grouped lines>"}
  ],
  "counts": {"action": 0, "rest": 0, "total": 0}
}

Rules:
- Put genuinely actionable/time-sensitive items in action_items, most urgent first. Be specific (names, deadlines, amounts).
- Collapse promotions, newsletters, and routine job-board/application notices into a few concise lines under "rest".
- gmail_url: use a messageId from the thread's messages (the #all/<messageId> deep link opens that message in Gmail).
- For a "rest" line that summarizes a single message, you may include a gmail_url (same #all/<messageId> format) so it's clickable; omit gmail_url for grouped lines (e.g. "3 job-board digests").
- counts.action = number of action_items, counts.rest = number of rest lines, counts.total = action + rest.
- If yesterday's inbox was empty, return empty arrays and zero counts.
"""


def date_tokens():
    today = datetime.date.today()
    yest = today - datetime.timedelta(days=1)
    return {
        "__TODAY_ISO__": today.isoformat(),
        "__YDAY_ISO__": yest.isoformat(),
        "__TODAY_SLASH__": today.strftime("%Y/%m/%d"),
        "__YDAY_SLASH__": yest.strftime("%Y/%m/%d"),
    }, yest


def build_prompt(tokens):
    prompt = PROMPT_TEMPLATE
    for k, v in tokens.items():
        prompt = prompt.replace(k, v)
    return prompt


def _invoke_claude_once(prompt):
    cmd = [CLAUDE, "-p", "--output-format", "json", "--allowedTools", ALLOWED_TOOLS]
    if MODEL:
        cmd += ["--model", MODEL]
    proc = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=TIMEOUT_SECONDS
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[:500]}")
    envelope = json.loads(proc.stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"claude reported error: {str(envelope.get('result'))[:500]}")
    return envelope.get("result", "")


def run_claude(prompt):
    # Retry transient failures (e.g. Wi-Fi not reconnected yet right after wake).
    backoffs = [10, 30]  # 3 attempts total
    for attempt in range(len(backoffs) + 1):
        try:
            return _invoke_claude_once(prompt)
        except Exception as exc:
            if attempt == len(backoffs):
                raise
            wait = backoffs[attempt]
            sys.stderr.write(
                f"[brief-me] attempt {attempt + 1} failed ({exc}); retrying in {wait}s\n"
            )
            time.sleep(wait)


def extract_json(text):
    """The model sometimes adds a sentence before the JSON; pull out the object."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in result: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def osascript(script):
    subprocess.run(["/usr/bin/osascript", "-e", script], check=False)


def notify(title, message):
    def esc(s):
        return str(s).replace("\\", "\\\\").replace('"', '\\"')

    osascript(f'display notification "{esc(message)}" with title "{esc(title)}"')


def refresh_swiftbar():
    subprocess.run(
        ["/usr/bin/open", "-g", f"swiftbar://refreshplugin?name={PLUGIN_NAME}"],
        check=False,
    )


def write_cache(brief):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(brief, f, indent=2)
    os.replace(tmp, CACHE)  # atomic; never leaves a half-written cache


def write_error(message):
    """Record that today's run failed, for the menu bar to surface."""
    os.makedirs(CACHE_DIR, exist_ok=True)  # may fire before any cache exists
    marker = {"at": datetime.datetime.now().astimezone().isoformat(), "message": str(message)[:500]}
    tmp = ERROR_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(marker, f, indent=2)
    os.replace(tmp, ERROR_FILE)


def clear_error():
    """Drop a stale failure marker after a successful run."""
    try:
        os.remove(ERROR_FILE)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _generated_today():
    try:
        with open(CACHE) as f:
            stamp = str(json.load(f).get("generated_at", ""))[:10]
        return stamp == datetime.date.today().isoformat()
    except Exception:
        return False


def main():
    # `--if-needed` (used by the LaunchAgent): generate at most once per day, and
    # only in/after the morning. A manual run (no flag) always generates.
    if "--if-needed" in sys.argv:
        if _generated_today():
            print("[brief-me] today's brief already generated; skipping")
            return
        if datetime.datetime.now().hour < 7:
            print("[brief-me] before 07:00 local; skipping until morning")
            return

    tokens, yest = date_tokens()
    result = run_claude(build_prompt(tokens))
    brief = extract_json(result)

    brief.setdefault("date", yest.isoformat())
    brief.setdefault("action_items", [])
    brief.setdefault("rest", [])
    counts = brief.get("counts") or {}
    n_action = counts.get("action", len(brief["action_items"]))
    n_rest = counts.get("rest", len(brief["rest"]))
    brief["counts"] = {"action": n_action, "rest": n_rest, "total": n_action + n_rest}
    brief["generated_at"] = datetime.datetime.now().astimezone().isoformat()
    brief["read"] = False

    write_cache(brief)
    clear_error()  # a successful run clears any stale failure marker

    others = f"{n_rest} other{'s' if n_rest != 1 else ''}"
    if n_action > 0:
        msg = f"{n_action} action item{'s' if n_action != 1 else ''} • {others}"
    else:
        msg = f"Nothing needs you • {others}"
    notify("\U0001F4EC Morning Brief", msg)
    refresh_swiftbar()
    print(f"[brief-me] wrote {n_action} action / {n_rest} rest -> {CACHE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # surface failures to the menu bar + log
        sys.stderr.write(f"[brief-me] ERROR: {exc}\n")
        try:
            write_error(exc)  # let the menu bar show a distinct "failed" state
        except Exception:
            pass
        try:
            notify("brief-me failed", str(exc)[:180])
        except Exception:
            pass
        sys.exit(1)
