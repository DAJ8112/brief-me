#!/usr/bin/python3
# <xbar.title>brief-me</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.author>brief-me</xbar.author>
# <xbar.desc>Morning inbox brief: yesterday's email, action items first.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
#
# Reads the daily-overwritten cache written by generate_brief.py and renders the
# menu bar. The cache is the single transient file the menu-bar surface needs;
# it is overwritten each morning and keeps no history.
#
# `--mark-read` flips the read flag (wired to the "Mark as read" menu item).

import datetime
import json
import os
import sys

CACHE = os.path.expanduser("~/Library/Caches/brief-me/today.json")
SELF = os.path.realpath(__file__)
PY = "/usr/bin/python3"

ACTION_COLOR = "#e0820a"  # amber — legible in light & dark
REST_COLOR = "#3b82f6"    # blue
MUTED = "#9aa0a6"         # gray


def load():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except Exception:
        return None


def mark_read():
    data = load()
    if data:
        data["read"] = True
        tmp = CACHE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, CACHE)


def clean(s):
    # '|' is SwiftBar's param delimiter; newlines break menu lines.
    return str(s).replace("|", "∣").replace("\n", " ").replace("\r", " ").strip()


def line(text, **params):
    parts = clean(text)
    if params:
        parts += " | " + " ".join(f"{k}={v}" for k, v in params.items() if v not in (None, ""))
    print(parts)


def render():
    data = load()
    today = datetime.date.today().isoformat()

    if not data:
        print("\U0001F4ED")  # 📭
        print("---")
        line("No brief yet", color=MUTED)
        line("Runs automatically around 7 AM", color=MUTED, size=11)
        print("---")
        line("↻ Refresh", refresh="true")
        return

    gen_date = str(data.get("generated_at", ""))[:10]
    fresh = gen_date == today
    read = bool(data.get("read", False))
    counts = data.get("counts", {})
    actions = data.get("action_items", [])
    rest = data.get("rest", [])
    n_action = counts.get("action", len(actions))

    # --- menu bar title ---
    if fresh and not read:
        print(f"\U0001F4EC {n_action}" if n_action else "\U0001F4EC")  # 📬
    else:
        print("\U0001F4ED")  # 📭

    print("---")
    line(f"Morning Brief — {data.get('date', '')}", size=14)
    if not fresh and gen_date:
        line(f"(from {gen_date}; today's run hasn't happened yet)", color=MUTED, size=11)
    print("---")

    # --- action needed ---
    line(f"⚡ Action needed ({len(actions)})", color=ACTION_COLOR)
    if actions:
        for it in actions:
            url = it.get("gmail_url", "")
            line(it.get("title", "(untitled)"), href=url or None)
            sender = it.get("sender", "")
            if sender:
                line(f"-- {sender}", color=MUTED, size=11, href=url or None)
    else:
        line("Nothing needs you \U0001F389", color=MUTED)

    # --- the rest ---
    print("---")
    line(f"\U0001F4E5 Rest ({len(rest)})", color=REST_COLOR)
    for r in rest:
        url = r.get("gmail_url", "")
        line(r.get("summary", ""), href=url or None, color=None if url else MUTED)

    # --- actions ---
    print("---")
    line(
        "✓ Mark as read",
        bash=f'"{PY}"',
        param1=f'"{SELF}"',
        param2="--mark-read",
        terminal="false",
        refresh="true",
    )
    line("↻ Refresh", refresh="true")
    line("\U0001F4E7 Open Gmail", href="https://mail.google.com/mail/u/0/#inbox")


def main():
    if "--mark-read" in sys.argv:
        mark_read()
        return
    render()


if __name__ == "__main__":
    main()
