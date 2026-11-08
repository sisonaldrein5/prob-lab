# Prop Lab
Free setup (no server, no API key):
1. Create a GitHub repo and upload these files (keep the `.github` folder).
2. Settings → Pages → deploy from `main` branch (root). Settings → Actions → allow read/write.
3. Actions tab → run "sync-nba-data" once. It then runs every ~20 min and commits fresh `data/*.json`.
Local test: `python sync.py && python -m http.server` then open http://localhost:8000
Tests: `node test.js`
If sync fails on GitHub (NBA.com sometimes blocks cloud IPs), run `python sync.py` from your own computer on a schedule and push `data/`.

## Injuries, pace, defense, usage
`sync.py` also writes `data/context.json`: team pace/defensive rating and usage from NBA.com, injuries from ESPN's public (unofficial) feed. If any of these fail, the site says "unavailable" instead of guessing.
## Prop lines (optional, free)
Uses SportsGameOdds' free plan (player props included). Create a free key at sportsgameodds.com, add it as repo secret `SGO_API_KEY`, then run "fetch-prop-lines" once. It runs twice a day and covers points, rebounds, assists and threes (one request for the whole slate). Check your usage on their dashboard after the first few days; if the monthly limit is tight, delete one cron time in `.github/workflows/lines.yml`. Without a key, lines stay manual.

Data source: ESPN public JSON feeds (no key, no installs). NBA.com blocks GitHub's servers, so it is not used. First run downloads up to 250 games; later runs only fetch new ones and back-fill last season for head-to-head until complete.
