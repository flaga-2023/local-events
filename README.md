# Sibiu Events Dashboard

A static dashboard that merges local event listings from RSS feeds and public
Facebook Pages, deduplicating events that appear on more than one source.

## How it works

1. `scripts/fetch_events.py` reads `scripts/sources.json`, pulls each RSS
   feed, optionally pulls public Facebook Page events via the official Graph
   API, fuzzy-matches titles + dates to merge duplicates, and writes
   `data/events.json`.
2. `.github/workflows/update-events.yml` runs that script once a day (and on
   demand) and commits the refreshed `data/events.json`.
3. `index.html` is a static page that reads `data/events.json` and renders
   it — no backend needed to *view* the dashboard, only to *update* it.

## Setup (10-15 minutes)

1. **Create a GitHub repo** and push this folder to it.
2. **Enable GitHub Pages**: repo Settings → Pages → Deploy from branch →
   `main` → `/ (root)`. Your dashboard will be live at
   `https://<username>.github.io/<repo>/`.
3. **Enable Actions**: they're on by default for public repos. Go to the
   Actions tab once to confirm the workflow shows up.
4. **Fix the RSS URLs**: I put placeholder feed URLs in
   `scripts/sources.json` — several Romanian event sites don't expose RSS
   at an obvious path. For each source, check for a `/feed` or `/rss` link,
   or view page source for `<link rel="alternate" type="application/rss+xml">`.
   If a site has no RSS at all, run an instance of
   [RSS-Bridge](https://github.com/RSS-Bridge/rss-bridge) (free, self-hosted
   or hosted by others) to generate one, and drop that URL in instead.
5. **(Optional) Facebook Pages**: create a Facebook Developer App, generate
   a Page Access Token with `pages_read_engagement`, add it to your repo as
   a secret named `FB_PAGE_ACCESS_TOKEN` (Settings → Secrets and variables →
   Actions), and fill in real `page_id` values in `sources.json`. This only
   reads a Page's own published Events — it cannot read Groups or your
   personal feed, since the Graph API doesn't expose those.
6. **Run it once manually**: Actions tab → "Update local events" →
   Run workflow. Check that `data/events.json` gets updated.

## Tuning the dedupe

In `scripts/sources.json`:
- `title_similarity_threshold` (0-100): how similar two titles must be to
  count as the same event. Lower = merges more aggressively.
- `date_window_days`: how many days apart two dated events can be and still
  be considered the same listing (handles sites that post the wrong day).

## Local testing

```bash
pip install feedparser rapidfuzz requests
python scripts/fetch_events.py
python -m http.server 8000   # then open localhost:8000
```
