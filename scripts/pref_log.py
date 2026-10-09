#!/usr/bin/env python3
"""pref_log.py — generic, domain-agnostic preference-signal logger for pi skills and jobs
(it began life under Hermes).

Any skill or script that shows the user a set of options, or learns the user chose/liked/
disliked one, appends an event here instead of inventing its own tracking. One shared store
means one summarizer (pref_summarize.py) and one place a skill can read "what does the
operator tend to pick" from, instead of every domain re-solving this itself.

Store: ~/.local/share/pi-jobs/preferences/events.jsonl, append-only, one JSON object per line:
  {ts, domain, action, title, url, keywords, tags, note}

action is one of: shown, chosen, liked, disliked. "shown" is the denominator (what was
offered); the others are signal. Not every domain needs every action — podcast-topics logs
shown + chosen; a domain with no natural "shown" set (e.g. a thumbs-down reaction on a
message) can log disliked alone, it just won't get keyword-weighted (pref_summarize.py
inherits keywords from a matching "shown" event by URL; with none, the raw event still shows
up in the "recent signal" list but scores nothing).

Usage:
  pref_log.py add --domain D --action {shown,chosen,liked,disliked} --title T
              [--url U] [--keywords k1,k2,...] [--tags t1,t2,...] [--note N]
  pref_log.py add-batch --domain D --action A
              (reads a JSON array of {title,url,keywords,tags,note} objects from stdin —
              for bulk "shown" logging, e.g. everything a discovery script just printed)
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

STORE_DIR = Path.home() / ".local" / "share" / "pi-jobs" / "preferences"  # was ~/.hermes/preferences until Hermes was removed, 2026-09-24
EVENTS_FILE = STORE_DIR / "events.jsonl"
ACTIONS = ["shown", "chosen", "liked", "disliked"]


def append_event(domain, action, title, url=None, keywords=None, tags=None, note=None):
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "domain": domain,
        "action": action,
        "title": title,
        "url": url,
        "keywords": keywords or [],
        "tags": tags or [],
        "note": note or "",
    }
    with EVENTS_FILE.open("a") as f:
        f.write(json.dumps(event) + "\n")
    return event


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="log a single preference event")
    add.add_argument("--domain", required=True)
    add.add_argument("--action", required=True, choices=ACTIONS)
    add.add_argument("--title", required=True)
    add.add_argument("--url")
    add.add_argument("--keywords", default="", help="comma-separated")
    add.add_argument("--tags", default="", help="comma-separated")
    add.add_argument("--note", default="")

    batch = sub.add_parser("add-batch", help="log many events of one domain/action from a JSON array on stdin")
    batch.add_argument("--domain", required=True)
    batch.add_argument("--action", required=True, choices=ACTIONS)

    args = p.parse_args()

    if args.cmd == "add":
        kw = [k.strip() for k in args.keywords.split(",") if k.strip()]
        tg = [t.strip() for t in args.tags.split(",") if t.strip()]
        ev = append_event(args.domain, args.action, args.title, args.url, kw, tg, args.note)
        print(f"logged: {ev['domain']}/{ev['action']}: {ev['title']}")
    else:
        try:
            items = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            sys.exit(f"add-batch: invalid JSON on stdin: {e}")
        if not isinstance(items, list):
            sys.exit("add-batch expects a JSON array on stdin")
        n = 0
        for it in items:
            append_event(args.domain, args.action, it.get("title", ""), it.get("url"),
                         it.get("keywords"), it.get("tags"), it.get("note"))
            n += 1
        print(f"logged {n} {args.domain}/{args.action} event(s)")


if __name__ == "__main__":
    main()
