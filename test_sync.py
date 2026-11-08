import sync, datetime as dt
LAB = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-"]
def ath(i, dnp=False): return {"athlete": {"id": str(i), "displayName": f"P{i}"}, "didNotPlay": dnp, "stats": [] if dnp else ["34", str(20 + i), "8-15", "2-5", "4-4", "7", "5", "3", "1", "0", "1", "6", "2", "+4"]}
def team(abbr, pids, pts, fga=88, fta=22, orb=10, tov=13):
    return {"team": {"abbreviation": abbr}, "statistics": [{"labels": LAB, "athletes": [ath(i) for i in pids] + [ath(99, True)], "totals": ["240", str(pts), f"40-{fga}", "10-30", f"15-{fta}", "45", "25", str(tov), "7", "4", str(orb), "35", "20", ""]}]}
def box(h, a, iso, completed=True, per=4, hab="GS", aab="NY"):
    return {"header": {"competitions": [{"date": iso, "status": {"period": per, "type": {"completed": completed}}, "competitors": [{"homeAway": "home", "team": {"abbreviation": hab}}, {"homeAway": "away", "team": {"abbreviation": aab}}]}]},
            "boxscore": {"players": [team(hab, [1, 2], 110), team(aab, [3, 4], 100)]}}
r = sync.parse_box(box(0, 0, "2026-11-06T02:30Z"))
assert r["d"] == "2026-11-05" and r["h"] == "GSW" and r["a"] == "NYK", r  # ET date + tricode mapping
p = r["p"][0]; assert p[4] == 21 and p[5] == 7 and p[6] == 5 and p[7] == 2 and p[8] == 1 and p[9] == 0 and p[10] == 3 and p[11] == 15 and p[12] == 4, p  # DNP skipped, parsed columns
assert r["t"]["GSW"] == [88, 22, 10, 110, 13], r["t"]
assert sync.parse_box(box(0, 0, "2026-11-06T02:30Z", completed=False)) is None
try: sync.parse_box({"header": {"competitions": [{"date": "2026-11-06T02:30Z", "status": {"type": {"completed": True}}, "competitors": [{"homeAway": "home", "team": {"abbreviation": "A"}}, {"homeAway": "away", "team": {"abbreviation": "B"}}]}]}, "boxscore": {"players": []}}); assert False
except ValueError: pass  # unexpected format fails loudly instead of storing nothing silently
games = {str(i): sync.parse_box(box(0, 0, f"2026-11-0{i}T23:00Z", hab="GS" if i % 2 else "NY", aab="NY" if i % 2 else "GS")) for i in range(1, 6)}
teams, lp, ld = sync.team_context(games); print(teams); assert teams["GSW"]["pace"] > 80
pl = sync.build_players(games, dt.datetime(2026, 11, 8, tzinfo=dt.timezone.utc)); p1 = next(x for x in pl if x["id"] == 1)
assert len(p1["logs"]) == 5 and len(p1["logs"][0]) == 12 and p1["logs"][0][0] > p1["logs"][-1][0] and 0 < p1["usg"] < 1
def ev(i, done, typ=2): return {"id": i, "date": "2026-11-05T00:30Z", "season": {"type": typ}, "status": {"type": {"completed": done}}}
sync.fetch = lambda url, tries=2: {"events": [ev("1", True), ev("2", True, 1), ev("3", False)]} if "20261105" in url else {"events": [ev("9", True)]}
k, done, errs = sync.list_days([dt.date(2026, 11, 5), dt.date(2026, 11, 4)], dt.date(2026, 11, 8))
assert set(k) == {"1", "9"} and done == ["2026-11-04"] and not errs, (k, done)  # preseason skipped; day with a live game not marked done
assert list(sync.daterange(dt.date(2026, 10, 30), dt.date(2026, 11, 1))) == [dt.date(2026, 10, 30), dt.date(2026, 10, 31), dt.date(2026, 11, 1)]
print("sync tests passed")
