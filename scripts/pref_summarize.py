#!/usr/bin/env python3
"""pref_summarize.py — turns ~/.local/share/pi-jobs/preferences/events.jsonl into two derived files:

  weights.json — {domain: {keyword: score in [-3, 3]}}, meant to be read back by a script
                 like podcast_topics.py as a scoring bonus/penalty.
  summary.md   — human/agent-readable digest ("leans toward / leans away from" per domain,
                 plus recent chosen/liked/disliked signal), meant to be read by a skill or an
                 agent turn that wants to know what the operator tends to pick.

Keyword attribution: a "chosen"/"liked"/"disliked" event usually doesn't carry its own
keywords — the agent logging it (from a live conversation, after the fact) typically only has
a title/url. It inherits keywords from the most recent "shown" event in the same domain with
the same URL. An event with no matching "shown" event and no keywords of its own still shows
up in "recent signal" for visibility, it just contributes nothing to keyword weighting.

Decay: an event's influence halves every HALF_LIFE_DAYS, so a burst of interest two months ago
doesn't permanently outweigh what the operator picks now — this is meant to track a moving
target, not settle on one forever.

Run standalone to refresh both files: python3 pref_summarize.py
Consumers (e.g. podcast_topics.py) should run this via subprocess before reading weights.json
rather than importing it, so the store stays a plain file interface, not a library dependency.
"""
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path

STORE_DIR = Path.home() / ".local" / "share" / "pi-jobs" / "preferences"  # was ~/.hermes/preferences until Hermes was removed, 2026-09-24
EVENTS_FILE = STORE_DIR / "events.jsonl"
WEIGHTS_FILE = STORE_DIR / "weights.json"
SUMMARY_FILE = STORE_DIR / "summary.md"

HALF_LIFE_DAYS = 45
MIN_SHOWN = 2          # ignore a keyword's score until it's accumulated at least this much shown-weight
CLIP = 3.0
ACTION_SIGN = {"chosen": 1.0, "liked": 1.0, "disliked": -1.0}

now = dt.datetime.now(dt.timezone.utc)


def url_key(url):
    if not url:
        return None
    return re.sub(r"[#?].*$", "", url.lower().rstrip("/"))


def load_events():
    if not EVENTS_FILE.exists():
        return []
    events = []
    for line in EVENTS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a corrupt line must not take the whole store down
    return events


def decay(ts):
    try:
        t = dt.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return 0.0
    age_days = max((now - t).total_seconds() / 86400, 0)
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def summarize(events):
    shown_keywords = defaultdict(dict)  # domain -> url_key -> keywords, from the latest "shown" event
    for e in events:
        if e.get("action") == "shown":
            k = url_key(e.get("url"))
            if k:
                shown_keywords[e["domain"]][k] = e.get("keywords") or []

    kw_stats = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))  # domain -> keyword -> [shown_w, signed_w]
    signal_log = defaultdict(list)  # domain -> [(ts, action, title, url)]

    for e in events:
        d, a, w = e.get("domain"), e.get("action"), decay(e.get("ts"))
        if not d or not a:
            continue
        kws = e.get("keywords") or []
        if a == "shown":
            for k in kws:
                kw_stats[d][k][0] += w
            continue
        if a in ACTION_SIGN:
            signal_log[d].append((e.get("ts"), a, e.get("title"), e.get("url")))
            inherited = shown_keywords.get(d, {}).get(url_key(e.get("url")), [])
            for k in set(kws) | set(inherited):
                # A chosen/liked/disliked item also counts toward its own keywords' shown-weight,
                # so a keyword that's only ever appeared via direct signal (never a "shown" batch)
                # can still clear MIN_SHOWN instead of being stuck at zero forever.
                kw_stats[d][k][0] += w
                kw_stats[d][k][1] += ACTION_SIGN[a] * w

    weights = {}
    for d, kws in kw_stats.items():
        weights[d] = {}
        for k, (shown_w, signed_w) in kws.items():
            if shown_w < MIN_SHOWN:
                continue
            score = max(-CLIP, min(CLIP, (signed_w / shown_w) * CLIP))
            if abs(score) > 0.05:
                weights[d][k] = round(score, 3)

    return weights, signal_log


def write_summary(weights, signal_log):
    lines = [f"# Learned preferences (auto-generated {now.strftime('%Y-%m-%d %H:%M UTC')})", "",
             "Derived from `events.jsonl` by `pref_summarize.py`. Do not edit by hand — it is "
             "overwritten on every run. See the `preference-mining` skill for the mechanism.", ""]
    domains = sorted(set(weights) | set(signal_log))
    if not domains:
        lines.append("No preference signal recorded yet.")
    for d in domains:
        lines.append(f"## {d}")
        ranked = sorted(weights.get(d, {}).items(), key=lambda kv: -kv[1])
        liked = [f"{k} ({v:+.2f})" for k, v in ranked if v > 0][:10]
        disliked = [f"{k} ({v:+.2f})" for k, v in ranked if v < 0][:10]
        lines.append(f"- Leans toward: {', '.join(liked) if liked else 'none yet'}")
        lines.append(f"- Leans away from: {', '.join(disliked) if disliked else 'none yet'}")
        recent = sorted(signal_log.get(d, []), key=lambda t: t[0] or "", reverse=True)[:8]
        if recent:
            lines.append("- Recent signal:")
            for ts, action, title, url in recent:
                day = (ts or "")[:10]
                suffix = f" — {url}" if url else ""
                lines.append(f"  - {day} {action}: {title}{suffix}")
        lines.append("")
    SUMMARY_FILE.write_text("\n".join(lines))


def main():
    events = load_events()
    weights, signal_log = summarize(events)
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    WEIGHTS_FILE.write_text(json.dumps(weights, indent=2, sort_keys=True))
    write_summary(weights, signal_log)
    total_signal = sum(len(v) for v in signal_log.values())
    total_scored = sum(len(v) for v in weights.values())
    print(f"{len(events)} events -> {total_scored} scored keyword(s) across {len(weights)} "
          f"domain(s); {total_signal} chosen/liked/disliked signal(s).")


if __name__ == "__main__":
    main()
