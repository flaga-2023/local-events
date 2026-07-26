#!/usr/bin/env python3
"""
Fetches events from local RSS feeds and public Facebook Pages (via the
official Graph API), deduplicates events that appear on multiple sources,
and writes the merged result to data/events.json for the static dashboard.

Env vars:
    FB_PAGE_ACCESS_TOKEN  - optional. A Facebook Graph API token with
                             pages_read_engagement, used to read public
                             Page posts. Never scrapes or logs in as a user.

Usage:
    python fetch_events.py
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = Path(__file__).resolve().parent / "sources.json"
OUTPUT_FILE = ROOT / "data" / "events.json"

FB_GRAPH_URL = "https://graph.facebook.com/v19.0"


def load_sources():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)  # strip HTML tags
    return re.sub(r"\s+", " ", text).strip()


def parse_rss_feed(feed_cfg):
    """Pull entries from a single RSS/Atom feed. Skips silently on failure
    so one broken source doesn't take down the whole run."""
    events = []
    try:
        parsed = feedparser.parse(feed_cfg["url"])
        if parsed.bozo and not parsed.entries:
            print(f"[warn] could not parse feed '{feed_cfg['name']}': {parsed.bozo_exception}")
            return events

        for entry in parsed.entries:
            title = clean_text(entry.get("title", ""))
            if not title:
                continue

            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                event_date = datetime(*published[:6], tzinfo=timezone.utc)
            else:
                event_date = None

            events.append({
                "title": title,
                "summary": clean_text(entry.get("summary", ""))[:280],
                "link": entry.get("link", ""),
                "date": event_date.isoformat() if event_date else None,
                "sources": [feed_cfg["name"]],
                "source_links": {feed_cfg["name"]: entry.get("link", "")},
            })
    except Exception as e:
        print(f"[warn] error fetching '{feed_cfg['name']}': {e}")
    return events


def parse_facebook_page(page_cfg, token):
    """Pulls upcoming/recent posts from a PUBLIC Facebook Page via the
    official Graph API. Requires a Page access token - this never logs in
    as a personal user and never touches Groups (not exposed by the API)."""
    events = []
    if not token or page_cfg.get("page_id", "").startswith("REPLACE_"):
        return events

    try:
        resp = requests.get(
            f"{FB_GRAPH_URL}/{page_cfg['page_id']}/events",
            params={"access_token": token, "fields": "name,description,start_time,event_place,id"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        for item in data:
            events.append({
                "title": clean_text(item.get("name", "")),
                "summary": clean_text(item.get("description", ""))[:280],
                "link": f"https://facebook.com/events/{item.get('id')}",
                "date": item.get("start_time"),
                "sources": [page_cfg["name"]],
                "source_links": {page_cfg["name"]: f"https://facebook.com/events/{item.get('id')}"},
            })
    except Exception as e:
        print(f"[warn] error fetching Facebook page '{page_cfg['name']}': {e}")
    return events


def same_event(a, b, title_threshold, date_window_days):
    """Two events are considered duplicates if their titles are similar
    enough AND their dates fall within the allowed window (or either date
    is unknown, in which case we fall back to title similarity alone)."""
    title_score = fuzz.token_sort_ratio(a["title"].lower(), b["title"].lower())
    if title_score < title_threshold:
        return False

    if a["date"] and b["date"]:
        try:
            da = datetime.fromisoformat(a["date"].replace("Z", "+00:00"))
            db = datetime.fromisoformat(b["date"].replace("Z", "+00:00"))
            if abs((da - db).days) > date_window_days:
                return False
        except ValueError:
            pass  # unparsable dates - fall back to title-only match

    return True


def dedupe_events(events, title_threshold, date_window_days):
    merged = []
    for event in events:
        match = next(
            (m for m in merged if same_event(m, event, title_threshold, date_window_days)),
            None,
        )
        if match:
            for src in event["sources"]:
                if src not in match["sources"]:
                    match["sources"].append(src)
            match["source_links"].update(event["source_links"])
            # keep the earliest known date and the longer summary
            if event["date"] and (not match["date"] or event["date"] < match["date"]):
                match["date"] = event["date"]
            if len(event["summary"]) > len(match["summary"]):
                match["summary"] = event["summary"]
        else:
            merged.append(event)
    return merged


def main():
    sources = load_sources()
    token = os.environ.get("FB_PAGE_ACCESS_TOKEN")

    all_events = []
    for feed_cfg in sources["rss_feeds"]:
        all_events.extend(parse_rss_feed(feed_cfg))
    for page_cfg in sources["facebook_pages"]:
        all_events.extend(parse_facebook_page(page_cfg, token))

    dedupe_cfg = sources.get("dedupe", {})
    merged = dedupe_events(
        all_events,
        title_threshold=dedupe_cfg.get("title_similarity_threshold", 82),
        date_window_days=dedupe_cfg.get("date_window_days", 1),
    )

    # sort: dated events first (soonest first), undated events last
    merged.sort(key=lambda e: (e["date"] is None, e["date"] or ""))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(merged),
            "events": merged,
        }, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(merged)} deduped events ({len(all_events)} raw) to {OUTPUT_FILE}")


if __name__ == "__main__":
    sys.exit(main())
