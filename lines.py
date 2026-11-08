"""Optional prop lines from SportsGameOdds (free 'Amateur' plan includes player props). Key: SGO_API_KEY.
One request returns every player market for the slate, so it uses very few of the free monthly 'objects'."""
import json, os, sys, unicodedata, urllib.request, urllib.parse, datetime as dt
STATS = {"points": "PTS", "rebounds": "REB", "assists": "AST", "threePointersMade": "FG3", "blocks": "BLK", "steals": "STL",
         "turnovers": "TOV", "points+rebounds+assists": "PRA", "points+rebounds": "PR", "points+assists": "PA", "rebounds+assists": "RA"}
PREF = ["fanduel", "draftkings", "betmgm", "caesars"]
# Only the four stat types whose oddID format is confirmed in the provider docs; set SGO_ODDIDS to request more.
DEFAULT_ODDIDS = ",".join(f"{s}-PLAYER_ID-game-ou-over" for s in ["points", "rebounds", "assists", "threePointersMade"])

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c) and c not in ".'’ _").lower()

def to_int(x):
    try: return int(str(x).replace("+", ""))
    except Exception: return None

def parse_event(ev, unknown=None):
    out = {}
    game = ev.get("eventID", "")
    for odd in (ev.get("odds") or {}).values():
        if odd.get("sideID") != "over" or odd.get("periodID") != "game": continue
        pid = odd.get("statEntityID") or ""
        if pid in ("", "all", "home", "away"): continue
        stat = STATS.get(odd.get("statID"))
        if not stat:
            if unknown is not None: unknown.add(odd.get("statID"))
            continue
        line = price = book = None
        byb = odd.get("byBookmaker") or {}
        for b in PREF + [k for k in byb if k not in PREF]:
            e = byb.get(b) or {}
            if e.get("available", True) and e.get("overUnder") not in (None, ""):
                line, price, book = float(e["overUnder"]), to_int(e.get("odds")), b; break
        if line is None:
            c = odd.get("bookOverUnder") or odd.get("fairOverUnder")
            if c in (None, ""): continue
            line, price, book = float(c), to_int(odd.get("bookOdds")), "consensus"
        name = norm("".join(pid.split("_")[:-2]))  # NAME_PARTS_1_NBA -> normalized name
        out[f"{name}|{stat}"] = {"line": line, "book": book, "over": price, "game": game}
    return out

def main():
    key = os.environ.get("SGO_API_KEY")
    if not key: print("SGO_API_KEY not set; skipping (lines stay manual)"); return
    q = {"apiKey": key, "leagueID": "NBA", "oddsAvailable": "true", "limit": "20", "oddIDs": os.environ.get("SGO_ODDIDS", DEFAULT_ODDIDS)}
    raw = json.load(urllib.request.urlopen(f"https://api.sportsgameodds.com/v2/events?{urllib.parse.urlencode(q)}", timeout=60))
    now, lines, unknown = dt.datetime.now(dt.timezone.utc), {}, set()
    for ev in raw.get("data", []):
        st = ((ev.get("status") or {}).get("startsAt")) or ""
        try:
            if dt.datetime.fromisoformat(st.replace("Z", "+00:00")) < now: continue  # skip games already started
        except ValueError: pass
        lines.update(parse_event(ev, unknown))
    if unknown: print("unmapped stat ids:", sorted(unknown))
    if lines:  # never overwrite good data with an empty result
        json.dump({"updated": now.isoformat(timespec="seconds"), "source": "SportsGameOdds", "lines": lines}, open("data/lines.json", "w"), separators=(",", ":"))
    print(f"ok: {len(lines)} lines")

if __name__ == "__main__": main()
