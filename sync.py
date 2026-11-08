"""Collects real NBA data with NO API key, from ESPN's public JSON feeds (NBA.com blocks cloud servers like GitHub's).
Schedule, final box scores, today's scoreboard and injuries all come from site.api.espn.com. Pure standard library.
Keeps a box-score store (data/store.json) so each run only downloads NEW games."""
import json, os, sys, time, urllib.request, urllib.error, datetime as dt
from concurrent.futures import ThreadPoolExecutor
try: from zoneinfo import ZoneInfo; ET = ZoneInfo("America/New_York")
except Exception: ET = dt.timezone(dt.timedelta(hours=-5))

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
MAX_PER_RUN = int(os.environ.get("MAX_BOX_PER_RUN", "250"))
BACKFILL_PREV = os.environ.get("BACKFILL_PREV", "1") == "1"
TRI = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP", "UTAH": "UTA", "WSH": "WAS"}  # ESPN -> NBA tricodes
tri = lambda a: TRI.get(a, a)

def fetch(url, tries=3, timeout=25):
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            if e.code == 403: raise RuntimeError(f"blocked (HTTP 403) by {url}")
            err = e
        except Exception as e:
            err = e
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"request failed for {url}: {err}")

def et_date(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET).strftime("%Y-%m-%d")

def num(s):
    try: return int(float(s))
    except Exception: return 0

def split(s, i):  # "8-15" -> 8 (i=0) or 15 (i=1)
    try: return int(str(s).split("-")[i])
    except Exception: return 0

def parse_box(j):
    """ESPN game summary -> compact record, or None if the game is not final. Raises on an unexpected format."""
    h = j["header"]["competitions"][0]
    if not h["status"]["type"].get("completed"): return None
    comp = {c["homeAway"]: c for c in h["competitors"]}
    rec = {"d": et_date(h["date"]), "h": tri(comp["home"]["team"]["abbreviation"]), "a": tri(comp["away"]["team"]["abbreviation"]),
           "per": int(h["status"].get("period") or 4), "t": {}, "p": []}
    for team in j["boxscore"]["players"]:
        t = tri(team["team"]["abbreviation"]); seen = {}
        for blk in team["statistics"]:
            L = {n: i for i, n in enumerate(blk.get("labels") or blk.get("names") or [])}
            need = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB"]
            if any(k not in L for k in need): continue
            g = lambda row, k: row[L[k]] if L[k] < len(row) else "0"
            for a in blk.get("athletes") or []:
                row = a.get("stats") or []
                if a.get("didNotPlay") or not row or num(g(row, "MIN")) <= 0: continue
                seen[int(a["athlete"]["id"])] = [int(a["athlete"]["id"]), a["athlete"]["displayName"], t, num(g(row, "MIN")), num(g(row, "PTS")), num(g(row, "REB")),
                    num(g(row, "AST")), split(g(row, "3PT"), 0), num(g(row, "STL")), num(g(row, "BLK")), num(g(row, "TO")), split(g(row, "FG"), 1), split(g(row, "FT"), 1)]
            tot = blk.get("totals") or []
            if tot and len(tot) > max(L.values()) - 0:  # [FGA, FTA, OREB, PTS, TOV]; unavailable (None) if absent, never guessed
                rec["t"][t] = [split(g(tot, "FG"), 1), split(g(tot, "FT"), 1), num(g(tot, "OREB")), num(g(tot, "PTS")), num(g(tot, "TO"))]
        rec["p"] += list(seen.values()); rec["t"].setdefault(t, None)
    if not rec["p"]: raise ValueError("no player rows parsed (unexpected ESPN format)")
    return rec

POSG = {"PG": "Guards", "SG": "Guards", "G": "Guards", "SF": "Forwards", "PF": "Forwards", "F": "Forwards", "C": "Centers"}
KEYS = ["PTS", "REB", "AST", "FG3", "STL", "BLK", "TOV", "PR", "PA", "RA", "PRA"]

def stat_vec(r):  # r[4:11] = pts reb ast fg3 stl blk tov
    p, rb, a, t3, st, bl, tv = r[4:11]
    return [p, rb, a, t3, st, bl, tv, p + rb, p + a, rb + a, p + rb + a]

def parse_roster(j):
    """ESPN team roster -> {player id: position abbreviation}. Players without a listed position are skipped, never guessed."""
    out = {}
    for a in (j or {}).get("athletes") or []:
        for x in (a.get("items") if isinstance(a, dict) and "items" in a else [a]):
            pos = (x.get("position") or {}).get("abbreviation")
            if x.get("id") and pos: out[int(x["id"])] = pos
    return out

def get_positions(store):
    if store.get("pos") and time.time() - store.get("posTs", 0) < 7 * 86400: return  # rosters change slowly
    teams = fetch(f"{BASE}/teams")["sports"][0]["leagues"][0]["teams"]
    pos = {}
    for t in teams: pos.update(parse_roster(fetch(f"{BASE}/teams/{t['team']['id']}/roster", tries=2)))
    if pos: store["pos"] = {str(k): v for k, v in pos.items()}; store["posTs"] = time.time()

def dvp(games, pos, last=15, min_games=3):
    """Defense vs position: stats a team ALLOWS per game to players at a position (and to guards/forwards/centers as groups),
    over its last N games, with rank among teams (1 = allows the most). Only players with a known position are counted."""
    keys = set(pos.values()) | {POSG[v] for v in pos.values() if v in POSG}
    cells, tot, known = {}, 0, 0
    for g in games.values():
        sums = {(sd, k): [0] * 11 for sd in ("a", "h") for k in keys}
        for r_ in g["p"]:
            tot += r_[3]; p = pos.get(r_[0])
            if not p: continue
            known += r_[3]; sd = "h" if r_[2] == g["h"] else "a"; v = stat_vec(r_)
            for k in (p, POSG.get(p)):
                if k: sums[(sd, k)] = [x + y for x, y in zip(sums[(sd, k)], v)]
        for (sd, k), v in sums.items():
            cells.setdefault((g["a"] if sd == "h" else g["h"], k), []).append((g["d"], v))  # players on side sd face the other team's defense
    out = {}
    for (team, k), L in cells.items():
        L = sorted(L, key=lambda x: x[0], reverse=True)[:last]
        if len(L) >= min_games: out.setdefault(team, {})[k] = {"n": len(L), "v": {KEYS[i]: round(sum(x[1][i] for x in L) / len(L), 1) for i in range(11)}, "r": {}}
    for k in keys:
        teams = [t for t in out if k in out[t]]
        for i, name in enumerate(KEYS):
            for rank, t in enumerate(sorted(teams, key=lambda t: out[t][k]["v"][name], reverse=True), 1):
                out[t][k]["r"][name] = rank; out[t][k]["of"] = len(teams)
    out["_cov"] = round(known / tot, 2) if tot else None
    return out

def poss(t): return t[0] + 0.44 * t[1] - t[2] + t[4]  # FGA + .44 FTA - OREB + TOV

def team_context(games, last=15):
    """Pace / defensive / net rating per team from stored box scores (each team's last N games)."""
    per = {}
    for gid, g in sorted(games.items(), key=lambda kv: kv[1]["d"], reverse=True):
        ta, th = g["t"].get(g["a"]), g["t"].get(g["h"])
        if not ta or not th: continue
        gm = 48 + 5 * max(0, g["per"] - 4)
        for me, tm, to in ((g["a"], ta, th), (g["h"], th, ta)):
            L = per.setdefault(me, [])
            if len(L) < last: L.append((48 * (poss(tm) + poss(to)) / 2 / gm, 100 * tm[3] / poss(tm), 100 * to[3] / poss(to)))
    teams = {}
    for t, L in per.items():
        if len(L) >= 3:
            pace, off, de = (sum(x[i] for x in L) / len(L) for i in range(3))
            teams[t] = {"pace": round(pace, 2), "def": round(de, 2), "net": round(off - de, 2), "n": len(L)}
    if not teams: return {}, None, None
    return teams, sum(t["pace"] for t in teams.values()) / len(teams), sum(t["def"] for t in teams.values()) / len(teams)

def build_players(games, now, types=None, pos=None):
    P = {}
    for gid, g in sorted(games.items(), key=lambda kv: kv[1]["d"], reverse=True):
        for r in g["p"]:
            p = P.setdefault(r[0], {"id": r[0], "name": r[1], "team": r[2], "pos": (pos or {}).get(r[0]), "logs": [], "_u": []})
            opp = g["a"] if r[2] == g["h"] else g["h"]
            p["logs"].append([g["d"], opp, 1 if r[2] == g["h"] else 0, r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], gid, (types or {}).get(gid)])  # last field: season type 2=regular 3=playoffs 5=play-in (None=unknown)
            tt = g["t"].get(r[2])
            if tt and len(p["_u"]) < 15: p["_u"].append((r[11] + 0.44 * r[12] + r[10], r[3], tt[0] + 0.44 * tt[1] + tt[4], 48 + 5 * max(0, g["per"] - 4)))
    out, cutoff = [], (now - dt.timedelta(days=150)).strftime("%Y-%m-%d")
    for p in P.values():
        logs = p["logs"][:80]
        if logs[0][0] < cutoff or sum(l[3] for l in logs[:10]) / len(logs[:10]) < 12: continue
        u = p.pop("_u"); den = sum(m * tm for _, m, tm, _ in u)
        p["usg"] = round(sum(x * gm for x, _, _, gm in u) / den, 3) if u and den else None
        p["logs"] = logs; out.append(p)
    return out

def daterange(a, b):
    while a <= b:
        yield a; a += dt.timedelta(days=1)

def list_days(days, today):
    """One scoreboard request per day (ESPN rejects multi-day ranges). Returns {event id: iso date} of final games, fully-final days, errors."""
    def one(d):
        try: return d, fetch(f"{BASE}/scoreboard?dates={d:%Y%m%d}", tries=2)
        except RuntimeError as e: return d, e
    known, types, done, errs = {}, {}, [], []
    with ThreadPoolExecutor(6) as ex:
        for d, j in ex.map(one, days):
            if isinstance(j, Exception): errs.append(str(j)); continue
            evs = (j or {}).get("events", [])
            for e in evs:
                if e["status"]["type"].get("completed") and (e.get("season") or {}).get("type", 2) != 1: known[e["id"]] = e["date"]; types[e["id"]] = (e.get("season") or {}).get("type", 2)  # skip preseason
            if d < today and all(e["status"]["type"].get("completed") for e in evs): done.append(d.isoformat())
    return known, types, done, errs

def slate(today):
    games = []
    for off in (-1, 0, 1):
        d = today + dt.timedelta(days=off)
        try: b = fetch(f"{BASE}/scoreboard?dates={d:%Y%m%d}")
        except RuntimeError as e: print(f"  scoreboard {d} failed:", e, file=sys.stderr); continue
        for ev in (b or {}).get("events", []):
            c = {x["homeAway"]: x for x in ev["competitions"][0]["competitors"]}; stt = ev["status"]["type"]
            games.append({"id": ev["id"], "date": d.isoformat(), "day": off, "status": {"pre": 1, "in": 2, "post": 3}.get(stt.get("state"), 1), "statusText": stt.get("shortDetail", ""), "startUTC": ev["date"],
                          "home": {"tri": tri(c["home"]["team"]["abbreviation"]), "score": num(c["home"].get("score"))}, "away": {"tri": tri(c["away"]["team"]["abbreviation"]), "score": num(c["away"].get("score"))}})
    return games

DAYS_PER_RUN = int(os.environ.get("DAYS_PER_RUN", "90"))

def main():
    now = dt.datetime.now(dt.timezone.utc); stamp = now.isoformat(timespec="seconds"); today = now.astimezone(ET).date()
    os.makedirs("data", exist_ok=True)
    try: store = json.load(open("data/store.json"))
    except Exception: store = {}
    if "ty" not in store: store["days"] = []; store.pop("prevDone", None)  # one-time: re-scan days to learn each game's season type
    store.setdefault("ty", {}); store.setdefault("games", {}); store.setdefault("missing", []); store.setdefault("known", {}); store.setdefault("days", [])
    sy = today.year if today.month >= 10 else today.year - 1
    def scan(days):
        known, types, done, errs = list_days(days, today)
        store["known"].update(known); store["ty"].update(types); store["days"] = sorted(set(store["days"]) | set(done))
        for e in errs[:2]: print("  day failed:", e, file=sys.stderr)
        if days and len(errs) == len(days): raise RuntimeError("every schedule request failed; keeping previous data")
    seen = set(store["days"])
    cur = [d for d in daterange(dt.date(sy, 10, 1), today) if d.isoformat() not in seen][::-1]  # newest first; today is re-checked every run
    scan(cur[:DAYS_PER_RUN])
    if len(cur) <= DAYS_PER_RUN and BACKFILL_PREV and not store.get("prevDone"):  # last season, for head-to-head depth
        prev = [d for d in daterange(dt.date(sy - 1, 10, 1), dt.date(sy, 6, 30)) if d.isoformat() not in seen][::-1]
        if prev: scan(prev[:DAYS_PER_RUN])
        else: store["prevDone"] = True
    skip = set(store["games"]) | set(store["missing"])
    todo = sorted([i for i in store["known"] if i not in skip], key=lambda i: store["known"][i], reverse=True)[:MAX_PER_RUN]
    def get(gid):
        try: return gid, fetch(f"{BASE}/summary?event={gid}", tries=2)
        except RuntimeError as e: return gid, e
    new, errors = 0, []
    with ThreadPoolExecutor(6) as ex:
        for gid, j in ex.map(get, todo):
            try:
                if isinstance(j, Exception): raise j
                rec = parse_box(j) if j else None
                if rec: store["games"][gid] = rec; new += 1
                elif j is None and store["known"][gid][:10] < f"{sy}-10-01": store["missing"].append(gid)  # old games only; current ones are retried
            except Exception as e:
                errors.append(f"{gid}: {e}")
    print(f"box scores: {new} new, {len(errors)} failed, {len(store['games'])} stored")
    for e in errors[:3]: print("  e.g.", e, file=sys.stderr)
    if todo and len(errors) == len(todo): raise RuntimeError("every box score failed; keeping previous data")
    if not store["games"]: raise RuntimeError("no games stored yet (season may not have started)")
    cur = {k: v for k, v in store["games"].items() if v["d"] >= f"{sy}-10-01"}
    teams, lgPace, lgDef = team_context(cur)
    try: get_positions(store)
    except Exception as e: print("positions unavailable (keeping previous):", e, file=sys.stderr)
    pos = {int(k): v for k, v in store.get("pos", {}).items()}
    players = build_players(store["games"], now, store["ty"], pos)
    ctx = {"updated": stamp, "scoreDate": str(today), "teams": teams, "lgPace": lgPace, "lgDef": lgDef, "dvp": dvp(cur, pos) if pos else {},
           "injuries": {"ok": False, "items": [], "updated": None, "source": "ESPN public injury feed (unofficial)"}}
    try:  # yesterday's results, today's and tomorrow's games (ET dates) with live status
        games = slate(today)
        if games: json.dump({"updated": stamp, "scoreDate": str(today), "games": games}, open("data/games.json", "w"), separators=(",", ":"))
    except Exception as e:
        print("scoreboard unavailable (keeping previous games.json):", e, file=sys.stderr)
    try:
        raw = fetch(f"{BASE}/injuries")
        items = [{"name": i["athlete"]["displayName"], "status": i.get("status", ""), "detail": (i.get("shortComment") or "")[:140]} for t in raw["injuries"] for i in t["injuries"]]
        if items: ctx["injuries"].update(ok=True, items=items, updated=stamp)
    except Exception as e:
        print("injuries unavailable:", e, file=sys.stderr)
    json.dump(store, open("data/store.json", "w"), separators=(",", ":"))
    json.dump({"updated": stamp, "season": f"{sy}-{str(sy+1)[-2:]}", "players": players}, open("data/players.json", "w"), separators=(",", ":"))
    json.dump(ctx, open("data/context.json", "w"), separators=(",", ":"))
    print(f"ok: {len(players)} players, {len(teams)} teams with pace/defense")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print("SYNC FAILED:", e, file=sys.stderr); sys.exit(1)
