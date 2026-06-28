#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
World Cup 2026 Draft Pool — daily standings site generator.

What it does:
  1. Pulls every completed World Cup match from ESPN's public API.
  2. Scores each of the 48 teams with your agreed point system.
  3. Sums each person's 4 teams into a leaderboard.
  4. Writes pool-site/index.html (drop on Netlify, or auto-deploy — see notes).

You only edit two blocks below: DRAFT and SCORING.
"""

import json, ssl, re, datetime, html, os, sys
import urllib.request
from collections import defaultdict

# ============================================================================
# 1. YOUR DRAFT  — replace with the real picks. Keys = people, values = 4 teams.
#    Team names must match ESPN's spelling. Run the script once; it prints any
#    name it can't find so you can fix it (see ALIASES below for quick remaps).
# ============================================================================
DRAFT = {
    "Daniel":    ["France", "Egypt", "Sweden", "Haiti"],
    "Antonio":   ["Spain", "Senegal", "Scotland", "Panama"],
    "Joe":       ["England", "Turkey", "Austria", "Iraq"],
    "Mario":     ["Argentina", "Uruguay", "Canada", "DR Congo"],
    "Bennett":   ["Germany", "Switzerland", "Ivory Coast", "Uzbekistan"],
    "Ryan":      ["Brazil", "United States", "Algeria", "Jordan"],
    "Vik":       ["Portugal", "Ecuador", "Ghana", "Cape Verde"],
    "Paul":      ["Netherlands", "Bosnia & Herzegovina", "Curacao", "South Africa"],
    "Mad Max":   ["Morocco", "Mexico", "Czechia", "New Zealand"],
    "Jack S":    ["Colombia", "Japan", "Qatar", "Saudi Arabia"],
    "J Kim":     ["Croatia", "South Korea", "Paraguay", "Tunisia"],
    "Matty Ice": ["Belgium", "Norway", "Australia", "Iran"],
}

# ============================================================================
# 2. SCORING — drop in the numbers you tweaked with the group.
# ============================================================================
SCORING = {
    "win": 3, "draw": 1, "loss": 0,
    "goal_for": 0, "goal_against": 0,          # goals are shown for context but NOT scored
    "group_winner": 4, "group_runner_up": 2, "group_third": 1,
    "reach_r32": 2, "reach_r16": 4, "reach_qf": 6, "reach_sf": 8, "reach_final": 10,
    "runner_up": 0, "champion": 20,            # runner-up just keeps the Final-appearance points
    "award": 10,                               # each individual award below is worth this
}

# ============================================================================
# 2b. INDIVIDUAL AWARDS — fill in the COUNTRY of each winner once FIFA announces
#     them (end of tournament). Whoever drafted that country gets +10 each.
#     Leave blank until then; blank = 0 points.
# ============================================================================
AWARDS = {
    "Golden Boot":         "",   # tournament top scorer
    "Golden Ball":         "",   # best player
    "Golden Glove":        "",   # best goalkeeper
    "Young Player Award":  "",   # best young player
}

# Name remaps if ESPN spells a team differently from your draft.
# KEY = how ESPN writes it,  VALUE = how it appears in your DRAFT above.
# The first run prints any team it can't match — add a line here for each.
ALIASES = {
    "Türkiye": "Turkey",
    "Congo DR": "DR Congo",
    "Côte d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "Curaçao": "Curacao",
    "Korea Republic": "South Korea",
    "Czech Republic": "Czechia",
    "USA": "United States",
    "IR Iran": "Iran",
}

# ----------------------------------------------------------------------------
# ESPN plumbing
# ----------------------------------------------------------------------------
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates="
START = datetime.date(2026, 6, 11)
END   = datetime.date(2026, 7, 19)
ONE   = datetime.timedelta(days=1)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=25, context=_ctx))

KO_ORDER  = {"r32": 1, "r16": 2, "qf": 3, "sf": 4, "final": 5}
REACH_KEY = {1: "reach_r32", 2: "reach_r16", 3: "reach_qf", 4: "reach_sf", 5: "reach_final"}
ROUND_LABEL = {1: "Round of 32", 2: "Round of 16", 3: "Quarterfinal", 4: "Semifinal", 5: "Final"}

def normalize_round(label):
    s = (label or "").lower()
    if "group" in s:
        m = re.search(r"group\s+([a-l])", s)
        return ("group", m.group(1).upper() if m else None)
    if "round of 32" in s or "round-of-32" in s or " 32" in s: return ("r32", None)
    if "round of 16" in s or "round-of-16" in s or " 16" in s: return ("r16", None)
    if "quarter" in s: return ("qf", None)
    if "semi" in s: return ("sf", None)
    if "third" in s or "3rd" in s: return ("third", None)
    if "final" in s: return ("final", None)
    return ("unknown", None)

def fetch_matches():
    out, seen, unknown = [], set(), set()
    d = START
    while d <= END:
        try:
            data = get(SCOREBOARD + d.strftime("%Y%m%d"))
        except Exception as e:
            print(f"  ! fetch failed {d}: {e}", file=sys.stderr)
            d += ONE; continue
        for ev in data.get("events", []):
            eid = ev.get("id")
            if eid in seen: continue
            seen.add(eid)
            comp = (ev.get("competitions") or [{}])[0]
            stype = (comp.get("status") or {}).get("type", {})
            completed = bool(stype.get("completed"))
            notes = comp.get("notes") or []
            label = (notes[0].get("headline") if notes else "") or ev.get("name", "")
            rnd, grp = normalize_round(label)
            if rnd == "unknown" and label:
                unknown.add(label)
            cs = comp.get("competitors") or []
            if len(cs) < 2: continue
            def cdata(c):
                team = c.get("team") or {}
                name = team.get("displayName") or team.get("name") or "?"
                name = ALIASES.get(name, name)
                try: score = int(c.get("score"))
                except (TypeError, ValueError): score = 0
                return name, score, bool(c.get("winner"))
            n0, s0, w0 = cdata(cs[0])
            n1, s1, w1 = cdata(cs[1])
            out.append({"round": rnd, "group": grp,
                        "team_a": n0, "score_a": s0,
                        "team_b": n1, "score_b": s1,
                        "winner": "a" if w0 else "b" if w1 else None,
                        "completed": completed, "label": label})
        d += ONE
    if unknown:
        print("  ! Unrecognized round labels (add to normalize_round):", file=sys.stderr)
        for u in sorted(unknown): print("      -", u, file=sys.stderr)
    return out

# ----------------------------------------------------------------------------
# Scoring engine  (pure function — no network, fully testable)
# ----------------------------------------------------------------------------
def blank():
    return {"gf": 0, "ga": 0, "w": 0, "d": 0, "l": 0,
            "group": None, "deepest_ko": 0, "champion": False, "runner_up": False}

def compute(matches, scoring):
    teams = defaultdict(blank)
    gtab = defaultdict(lambda: {"pts": 0, "gd": 0, "gf": 0})  # group-only table

    for m in matches:
        if not m["completed"] or m["round"] == "third":
            continue
        a, b, sa, sb = m["team_a"], m["team_b"], m["score_a"], m["score_b"]
        ta, tb = teams[a], teams[b]
        ta["gf"] += sa; ta["ga"] += sb
        tb["gf"] += sb; tb["ga"] += sa

        if m["round"] == "group":
            ta["group"] = tb["group"] = m["group"]
            if sa > sb:   ta["w"] += 1; tb["l"] += 1; gtab[a]["pts"] += 3
            elif sb > sa: tb["w"] += 1; ta["l"] += 1; gtab[b]["pts"] += 3
            else:         ta["d"] += 1; tb["d"] += 1; gtab[a]["pts"] += 1; gtab[b]["pts"] += 1
            gtab[a]["gd"] += sa - sb; gtab[a]["gf"] += sa
            gtab[b]["gd"] += sb - sa; gtab[b]["gf"] += sb
        else:
            rank = KO_ORDER.get(m["round"])
            if rank:
                ta["deepest_ko"] = max(ta["deepest_ko"], rank)
                tb["deepest_ko"] = max(tb["deepest_ko"], rank)
            win = m["winner"] or ("a" if sa > sb else "b" if sb > sa else None)
            if win == "a":   ta["w"] += 1; tb["l"] += 1
            elif win == "b": tb["w"] += 1; ta["l"] += 1
            if m["round"] == "final" and win:
                champ, runr = (a, b) if win == "a" else (b, a)
                teams[champ]["champion"] = True
                teams[runr]["runner_up"] = True

    # group winner / runner-up from the group-only table
    finish = {}
    by_group = defaultdict(list)
    for name, s in teams.items():
        if s["group"]:
            by_group[s["group"]].append(name)
    for letter, names in by_group.items():
        ranked = sorted(names, key=lambda n: (-gtab[n]["pts"], -gtab[n]["gd"], -gtab[n]["gf"], n))
        if len(ranked) >= 1: finish[ranked[0]] = 1
        if len(ranked) >= 2: finish[ranked[1]] = 2
        if len(ranked) >= 3: finish[ranked[2]] = 3
    return teams, finish

def team_score(name, teams, finish, scoring, awards_for=None):
    awards_for = awards_for or {}
    s = teams.get(name)
    n_awards = len(awards_for.get(name, []))
    award_pts = n_awards * scoring["award"]
    if not s:
        return award_pts, {"results": 0, "goals": 0, "group_finish": 0,
                           "advancement": 0, "final": 0, "awards": award_pts}, blank()
    comp = {
        "results": s["w"]*scoring["win"] + s["d"]*scoring["draw"] + s["l"]*scoring["loss"],
        "goals":   s["gf"]*scoring["goal_for"] + s["ga"]*scoring["goal_against"],
    }
    pos = finish.get(name)
    comp["group_finish"] = {1: scoring["group_winner"], 2: scoring["group_runner_up"],
                            3: scoring["group_third"]}.get(pos, 0)
    comp["advancement"] = sum(scoring[REACH_KEY[r]] for r in range(1, s["deepest_ko"] + 1))
    comp["final"] = scoring["champion"] if s["champion"] else scoring["runner_up"] if s["runner_up"] else 0
    comp["awards"] = award_pts
    return sum(comp.values()), comp, s

# ----------------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------------
def team_status(name, teams, finish, awards_for=None):
    awards_for = awards_for or {}
    s = teams.get(name)
    badges = ["🏅 " + a for a in awards_for.get(name, [])]
    if not s or (s["w"] + s["d"] + s["l"]) == 0:
        return " · ".join(badges) if badges else "—"
    bits = []
    if s["champion"]:    bits.append("🏆 Champion")
    elif s["runner_up"]: bits.append("🥈 Runner-up")
    elif s["deepest_ko"]: bits.append("Reached " + ROUND_LABEL[s["deepest_ko"]])
    pos = finish.get(name)
    if pos == 1:   bits.append("Group winner")
    elif pos == 2: bits.append("Group 2nd")
    elif pos == 3: bits.append("Group 3rd")
    bits += badges
    return " · ".join(bits) if bits else "Group stage"

def render(standings, teams, finish, scoring, meta, awards_for=None):
    awards_for = awards_for or {}
    esc = html.escape
    rows = ""
    for rank, (person, pts, tdetail, agg) in enumerate(standings, 1):
        medal = {1: "rank-1", 2: "rank-2", 3: "rank-3"}.get(rank, "")
        teamrows = ""
        for tname, tpts, comp, s in tdetail:
            teamrows += f"""<tr>
              <td class="tm">{esc(tname)}</td>
              <td class="rec">{s['w']}-{s['d']}-{s['l']}</td>
              <td class="gd">{s['gf']}:{s['ga']}</td>
              <td class="st">{esc(team_status(tname, teams, finish, awards_for))}</td>
              <td class="pt">{tpts}</td>
            </tr>"""
        rows += f"""
        <details class="card {medal}">
          <summary>
            <span class="pos">{rank}</span>
            <span class="name">{esc(person)}</span>
            <span class="agg">{agg['w']}-{agg['d']}-{agg['l']} · {agg['gf']}:{agg['ga']}</span>
            <span class="total">{pts}</span>
          </summary>
          <table class="teams">
            <thead><tr><th>Team</th><th>W-D-L</th><th>GF:GA</th><th>Status</th><th>Pts</th></tr></thead>
            <tbody>{teamrows}</tbody>
          </table>
        </details>"""

    key = (f"Win +{scoring['win']} · Draw +{scoring['draw']} · Loss +{scoring['loss']} &nbsp;|&nbsp; "
           f"Group winner +{scoring['group_winner']} · Runner-up +{scoring['group_runner_up']} · "
           f"3rd +{scoring['group_third']} &nbsp;|&nbsp; "
           f"R32 +{scoring['reach_r32']} · R16 +{scoring['reach_r16']} · QF +{scoring['reach_qf']} · "
           f"SF +{scoring['reach_sf']} · Final +{scoring['reach_final']} · Champion +{scoring['champion']} "
           f"&nbsp;|&nbsp; Golden Boot / Ball / Glove / Young Player +{scoring['award']} each. "
           f"Goals shown for context only.")

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup Draft Pool</title>
<style>
:root{{--bg:#0c1117;--card:#161d27;--line:#232c39;--ink:#e7edf5;--mut:#8a97a8;--gold:#f2c14e;--green:#3fb56b}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 -webkit-font-smoothing:antialiased}}
.wrap{{max-width:760px;margin:0 auto;padding:28px 18px 60px}}
h1{{font-size:23px;margin:0 0 2px;letter-spacing:-.02em}}
.sub{{color:var(--mut);font-size:13px;margin-bottom:22px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:10px;overflow:hidden}}
summary{{list-style:none;cursor:pointer;display:grid;
 grid-template-columns:34px 1fr auto auto;gap:12px;align-items:center;padding:14px 16px}}
summary::-webkit-details-marker{{display:none}}
.pos{{font-weight:700;color:var(--mut);text-align:center}}
.name{{font-weight:650;font-size:16px}}
.agg{{color:var(--mut);font-size:12.5px;font-variant-numeric:tabular-nums}}
.total{{font-weight:800;font-size:19px;font-variant-numeric:tabular-nums;min-width:46px;text-align:right}}
.rank-1 .pos,.rank-1 .total{{color:var(--gold)}}
.rank-1{{border-color:var(--gold)}}
.rank-2 .total,.rank-3 .total{{color:var(--ink)}}
table.teams{{width:100%;border-collapse:collapse;border-top:1px solid var(--line)}}
table.teams th{{text-align:left;color:var(--mut);font-weight:600;font-size:11px;
 text-transform:uppercase;letter-spacing:.04em;padding:9px 16px}}
table.teams td{{padding:9px 16px;border-top:1px solid var(--line);font-variant-numeric:tabular-nums}}
td.tm{{font-weight:600}} td.rec,td.gd{{color:var(--mut);font-size:13px}}
td.st{{color:var(--mut);font-size:12.5px}} td.pt{{text-align:right;font-weight:700}}
.key{{margin-top:26px;color:var(--mut);font-size:11.5px;line-height:1.7;border-top:1px solid var(--line);padding-top:16px}}
</style></head><body><div class="wrap">
<h1>🌍 World Cup 2026 — Draft Pool</h1>
<div class="sub">Updated {esc(meta['updated'])} · {meta['done']} matches counted · tap a name to expand</div>
{rows}
<div class="key"><b>Scoring</b> &nbsp; {key}</div>
</div></body></html>"""

# ----------------------------------------------------------------------------
def build(matches):
    teams, finish = compute(matches, SCORING)
    # awards: country -> list of award names won (only ones that are filled in)
    awards_for = defaultdict(list)
    for award_name, country in AWARDS.items():
        if country:
            awards_for[country].append(award_name)

    # validate draft names against ESPN data
    seen = set(teams.keys())
    missing = [t for picks in DRAFT.values() for t in picks if t not in seen]
    if missing:
        print("  ! Draft teams not found in ESPN data yet (typo or no match played):", file=sys.stderr)
        for t in sorted(set(missing)): print("      -", t, file=sys.stderr)

    standings = []
    for person, picks in DRAFT.items():
        tdetail, total = [], 0
        agg = {"w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0}
        for t in picks:
            pts, comp, s = team_score(t, teams, finish, SCORING, awards_for)
            total += pts
            tdetail.append((t, pts, comp, s))
            for k in agg: agg[k] += s[k]
        tdetail.sort(key=lambda x: -x[1])
        standings.append((person, total, tdetail, agg))
    standings.sort(key=lambda x: -x[1])

    done = sum(1 for m in matches if m["completed"] and m["round"] != "third")
    meta = {"updated": datetime.datetime.now().strftime("%b %-d, %Y · %-I:%M %p"), "done": done}
    return render(standings, teams, finish, SCORING, meta, awards_for)

def main():
    print("Pulling World Cup matches from ESPN…")
    matches = fetch_matches()
    print(f"  {len(matches)} matches found, "
          f"{sum(1 for m in matches if m['completed'])} completed.")
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pool-site")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(build(matches))
    print(f"  Wrote {out_dir}/index.html")

if __name__ == "__main__":
    main()
