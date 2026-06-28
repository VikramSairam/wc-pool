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

import json, ssl, re, datetime, html, os, sys, shutil
import urllib.request
from collections import defaultdict

# ============================================================================
# 1. YOUR DRAFT  — replace with the real picks. Keys = people, values = 4 teams.
#    Team names must match ESPN's spelling. Run the script once; it prints any
#    name it can't find so you can fix it (see ALIASES below for quick remaps).
# ============================================================================
DRAFT = {
    "Daniel (G.O.A.T.)":          ["France", "Egypt", "Sweden", "Haiti"],
    "Wantonio":                   ["Spain", "Senegal", "Scotland", "Panama"],
    "Tik Tok Joe":                ["England", "Turkey", "Austria", "Iraq"],
    "Mario Armando Leal Verdugo": ["Argentina", "Uruguay", "Canada", "DR Congo"],
    "BP, Twin, Oil Spill":        ["Germany", "Switzerland", "Ivory Coast", "Uzbekistan"],
    "Young Man":                  ["Brazil", "United States", "Algeria", "Jordan"],
    "Vikinho":                    ["Portugal", "Ecuador", "Ghana", "Cape Verde"],
    "Paul Benzino":               ["Netherlands", "Bosnia & Herzegovina", "Curacao", "South Africa"],
    "Mad Max":                    ["Morocco", "Mexico", "Czechia", "New Zealand"],
    "Jack S":                     ["Colombia", "Japan", "Qatar", "Saudi Arabia"],
    "J Kim":                      ["Croatia", "South Korea", "Paraguay", "Tunisia"],
    "Matty Ice":                  ["Belgium", "Norway", "Australia", "Iran"],
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

# ============================================================================
# 3. LOOK & FEEL (all optional — leave as-is and it still looks good)
# ============================================================================
# Headshots: put image files in an `avatars/` folder in your repo. Each photo's
# filename (without the extension) should match the basename below. The extension
# can be .jpg/.jpeg/.png/.webp — the script finds whichever you used. Anyone
# without a photo keeps their colored initials circle.
AVATARS = {
    "Daniel (G.O.A.T.)":          "daniel",
    "Wantonio":                   "wantonio",
    "Tik Tok Joe":                "joe",
    "Mario Armando Leal Verdugo": "mario",
    "BP, Twin, Oil Spill":        "bp",
    "Young Man":                  "youngman",
    "Vikinho":                    "vikinho",
    "Paul Benzino":               "paul",
    "Mad Max":                    "madmax",
    "Jack S":                     "jacks",
    "J Kim":                      "jkim",
    "Matty Ice":                  "mattyice",
}

# Custom top banner: put an image in your repo (e.g. "banner.jpg") and name it
# here. Use a WIDE / horizontal image. Leave "" for the built-in gradient banner.
BANNER_IMAGE = "banner.jpg"

# Full-bleed background art behind everything (e.g. your bracket image with an
# empty middle — the leaderboard sits over the empty center, the art shows in the
# left/right margins). Center is darkened for readability, edges stay bright.
# Leave "" for the plain dark gradient.
BACKGROUND_IMAGE = "bracket.png"

# ----------------------------------------------------------------------------
# ESPN plumbing
# ----------------------------------------------------------------------------
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
STANDINGS  = "https://site.api.espn.com/apis/v2/sports/soccer/fifa.world/standings"
START = datetime.date(2026, 6, 11)
END   = datetime.date(2026, 7, 19)

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=25, context=_ctx))

KO_ORDER  = {"r32": 1, "r16": 2, "qf": 3, "sf": 4, "final": 5}
REACH_KEY = {1: "reach_r32", 2: "reach_r16", 3: "reach_qf", 4: "reach_sf", 5: "reach_final"}
ROUND_LABEL = {1: "Round of 32", 2: "Round of 16", 3: "Quarterfinal", 4: "Semifinal", 5: "Final"}

def classify(slug, note):
    """ESPN puts the stage in event.season.slug ('group-stage', 'round-of-32',
    'quarterfinals', ...) and the group letter in competition.altGameNote
    ('FIFA World Cup, Group I'). notes[] is usually empty for the World Cup."""
    s = (slug or "").lower()
    n = (note or "").lower()
    if "group" in s or "group" in n:
        m = re.search(r"group\s+([a-l])\b", n)
        return ("group", m.group(1).upper() if m else None)
    if "32" in s or "round of 32" in n:        return ("r32", None)
    if "16" in s or "round of 16" in n:        return ("r16", None)
    if "quarter" in s or "quarter" in n:       return ("qf", None)
    if "semi" in s or "semi" in n:             return ("sf", None)
    if "3rd" in s or "third" in s or "3rd" in n or "third" in n: return ("third", None)
    if "final" in s or "final" in n:           return ("final", None)
    return ("unknown", None)

def fetch_matches():
    url = f"{SCOREBOARD}?dates={START:%Y%m%d}-{END:%Y%m%d}&limit=950"
    data = get(url)
    out, unknown = [], set()
    for ev in data.get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        stype = (comp.get("status") or {}).get("type", {})
        completed = bool(stype.get("completed"))
        slug = (ev.get("season") or {}).get("slug", "")
        note = comp.get("altGameNote", "")
        if not note and comp.get("notes"):
            note = comp["notes"][0].get("headline", "")
        rnd, grp = classify(slug, note)
        if rnd == "unknown":
            unknown.add(f"{slug} | {note}")
        cs = comp.get("competitors") or []
        if len(cs) < 2:
            continue
        def cdata(c):
            team = c.get("team") or {}
            name = team.get("displayName") or team.get("name") or "?"
            name = ALIASES.get(name, name)
            flag = team.get("logo", "")
            try: score = int(c.get("score"))
            except (TypeError, ValueError): score = 0
            return name, score, bool(c.get("winner")), flag
        n0, s0, w0, f0 = cdata(cs[0])
        n1, s1, w1, f1 = cdata(cs[1])
        out.append({"round": rnd, "group": grp,
                    "team_a": n0, "score_a": s0, "flag_a": f0,
                    "team_b": n1, "score_b": s1, "flag_b": f1,
                    "winner": "a" if w0 else "b" if w1 else None,
                    "completed": completed, "label": note or slug})
    if unknown:
        print("  ! Unrecognized stages (slug | note) — add to classify():", file=sys.stderr)
        for u in sorted(unknown): print("      -", u, file=sys.stderr)
    return out

def fetch_standings():
    """Group winner/runner-up/third straight from ESPN's standings feed. This is
    the reliable source — it keeps the group ranking after games finish, which the
    scoreboard's per-match group label does not. Returns ({team: 1|2|3}, {team: flag})."""
    finish, flags = {}, {}
    try:
        data = get(STANDINGS)
    except Exception as e:
        print(f"  ! standings fetch failed ({e}) — using scoreboard tables instead", file=sys.stderr)
        return finish, flags
    for child in data.get("children", []):
        label = f"{child.get('name','')} {child.get('abbreviation','')}".lower()
        if "group" not in label:
            continue
        entries = (child.get("standings") or {}).get("entries", [])
        ranked = []
        for e in entries:
            team = e.get("team") or {}
            raw = team.get("displayName") or team.get("name") or "?"
            name = ALIASES.get(raw, raw)
            logos = team.get("logos") or []
            if logos and logos[0].get("href"):
                flags[name] = logos[0]["href"]
            note = e.get("note") or {}
            stat = {s.get("name"): s.get("value") for s in (e.get("stats") or [])}
            rk = note.get("rank") if isinstance(note, dict) else None
            if rk is None:
                rk = stat.get("rank")
            ranked.append((name, rk, stat))
        if ranked and all(r[1] is not None for r in ranked):
            ranked.sort(key=lambda r: r[1])
        else:
            ranked.sort(key=lambda r: (-(r[2].get("points") or 0),
                                       -(r[2].get("pointDifferential") or 0),
                                       -(r[2].get("pointsFor") or 0)))
        for i, (name, _, _) in enumerate(ranked[:3], start=1):
            finish[name] = i
    return finish, flags

# ----------------------------------------------------------------------------
# Scoring engine  (pure function — no network, fully testable)
# ----------------------------------------------------------------------------
def blank():
    return {"gf": 0, "ga": 0, "w": 0, "d": 0, "l": 0, "flag": "",
            "group": None, "deepest_ko": 0, "champion": False, "runner_up": False}

def compute(matches, scoring):
    teams = defaultdict(blank)
    gtab = defaultdict(lambda: {"pts": 0, "gd": 0, "gf": 0})  # group-only table

    for m in matches:
        # capture flags even from not-yet-complete or third-place games so every team has one
        if m.get("flag_a"): teams[m["team_a"]]["flag"] = m["flag_a"]
        if m.get("flag_b"): teams[m["team_b"]]["flag"] = m["flag_b"]
        if m["round"] == "third":
            continue
        # A knockout APPEARANCE counts the moment the fixture exists (team is in the
        # bracket), whether or not that match has been played yet.
        rank = KO_ORDER.get(m["round"])
        if rank:
            teams[m["team_a"]]["deepest_ko"] = max(teams[m["team_a"]]["deepest_ko"], rank)
            teams[m["team_b"]]["deepest_ko"] = max(teams[m["team_b"]]["deepest_ko"], rank)
        if not m["completed"]:
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

def flag_img(url, cls="flag"):
    if url:
        return f'<img class="{cls}" src="{html.escape(url)}" alt="" loading="lazy">'
    return f'<span class="{cls} noflag"></span>'

def avatar_html(person, avatar_files=None):
    src = (avatar_files or {}).get(person)
    if src:
        return f'<img class="ava" src="{html.escape(src)}" alt="">'
    words = [re.sub(r"[^A-Za-z0-9]", "", w) for w in person.split()]
    words = [w for w in words if w]
    if len(words) >= 2:
        initials = (words[0][0] + words[1][0]).upper()
    elif words:
        initials = words[0][:2].upper()
    else:
        initials = "?"
    hue = sum(ord(c) for c in person) % 360
    return (f'<span class="ava ava-i" style="background:linear-gradient(135deg,'
            f'hsl({hue} 62% 46%),hsl({(hue+45) % 360} 60% 36%))">{html.escape(initials)}</span>')

def resolve_avatars(avatars_dir):
    """Match each manager to a real image file in avatars_dir, trying the basename
    in AVATARS first, then a slug of the manager's name, across common extensions."""
    out = {}
    if not os.path.isdir(avatars_dir):
        return out
    have = {f.lower(): f for f in os.listdir(avatars_dir)}
    exts = (".jpg", ".jpeg", ".png", ".webp", ".gif")
    for person in DRAFT:
        candidates = []
        if AVATARS.get(person):
            candidates.append(AVATARS[person].lower())
        candidates.append(re.sub(r"[^a-z0-9]", "", person.lower()))  # name slug fallback
        for base in candidates:
            hit = next((have[base + e] for e in exts if base + e in have), None)
            if hit:
                out[person] = "avatars/" + hit
                break
    return out

def render(standings, teams, finish, scoring, meta, awards_for=None, avatar_files=None):
    awards_for = awards_for or {}
    avatar_files = avatar_files or {}
    esc = html.escape
    rows = ""
    for rank, (person, pts, tdetail, agg) in enumerate(standings, 1):
        medal = {1: "rank-1", 2: "rank-2", 3: "rank-3"}.get(rank, "")
        kit = "".join(flag_img(s["flag"], "kf") for _, _, _, s in tdetail)
        teamrows = ""
        for tname, tpts, comp, s in tdetail:
            teamrows += f"""<tr>
              <td class="tm"><span class="tmwrap">{flag_img(s['flag'],'flag')}<span>{esc(tname)}</span></span></td>
              <td class="rec">{s['w']}-{s['d']}-{s['l']}</td>
              <td class="gd">{s['gf']}:{s['ga']}</td>
              <td class="st">{esc(team_status(tname, teams, finish, awards_for))}</td>
              <td class="pt">{tpts}</td>
            </tr>"""
        marker = "👑" if rank == 1 else str(rank)
        rows += f"""
        <details class="card {medal}">
          <summary>
            <span class="pos">{marker}</span>
            {avatar_html(person, avatar_files)}
            <span class="who"><span class="nm">{esc(person)}</span><span class="kit">{kit}</span></span>
            <span class="tot"><b>{pts}</b><i>PTS</i></span>
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

    banner_src = (BANNER_IMAGE if BANNER_IMAGE.startswith("http")
                  else os.path.basename(BANNER_IMAGE) if BANNER_IMAGE else "")
    banner_style = (f' style="background-image:linear-gradient(rgba(14,11,26,.45),rgba(14,11,26,.82)),'
                    f'url({html.escape(banner_src)});background-size:cover;background-position:center"'
                    if banner_src else "")

    bg_src = (BACKGROUND_IMAGE if BACKGROUND_IMAGE.startswith("http")
              else os.path.basename(BACKGROUND_IMAGE) if BACKGROUND_IMAGE else "")
    pagebg_attr = f' style="background-image:url({html.escape(bg_src)})"' if bg_src else ""

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>World Cup Draft Pool</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--bg0:#0e0b1a;--bg1:#171130;--card:#1b1640;--card2:#181235;--line:#2c2556;
 --ink:#f4f1ff;--mut:#a79fc8;--gold:#ffd166;--green:#34e1b0;--pop:#ff5d8f;
 --display:'Barlow Condensed',system-ui,sans-serif;--mono:'JetBrains Mono',ui-monospace,monospace}}
*{{box-sizing:border-box}}
body{{margin:0;color:var(--ink);font-family:var(--display);font-size:18px;line-height:1.4;
 -webkit-font-smoothing:antialiased;
 background:radial-gradient(1200px 600px at 50% -10%,#241a4d 0%,var(--bg1) 40%,var(--bg0) 100%) fixed}}
.wrap{{max-width:780px;margin:0 auto;padding:0 16px 64px;position:relative;z-index:1}}

/* ---- full-bleed background art (bracket) ---- */
.pagebg{{position:fixed;inset:0;z-index:0;background-position:center;background-repeat:no-repeat;
 background-size:cover}}
.pagebg::after{{content:"";position:absolute;inset:0;
 background:radial-gradient(ellipse 62% 92% at 50% 46%,
   rgba(14,11,26,.82) 0%,rgba(14,11,26,.80) 38%,rgba(14,11,26,.30) 100%)}}

/* ---- banner ---- */
.banner{{position:relative;z-index:1;margin:0 -16px 22px;padding:40px 24px 50px;overflow:hidden;
 background:linear-gradient(115deg,#3a1d6e 0%,#5b2a86 38%,#1f7a6b 100%)}}
.banner::before{{content:"";position:absolute;inset:0;opacity:.16;
 background:repeating-linear-gradient(115deg,#fff 0 2px,transparent 2px 22px)}}
.banner::after{{content:"";position:absolute;left:-20%;top:-60%;width:60%;height:220%;
 background:linear-gradient(90deg,transparent,rgba(255,255,255,.18),transparent);transform:rotate(8deg);
 animation:sheen 6s ease-in-out infinite}}
@keyframes sheen{{0%,60%{{left:-30%}}100%{{left:130%}}}}
.banner .in{{position:relative;z-index:1}}
.eyebrow{{font-family:var(--mono);font-size:12px;font-weight:700;letter-spacing:.26em;text-transform:uppercase;
 color:rgba(255,255,255,.82);margin:0 0 8px}}
h1{{font-family:var(--display);font-weight:800;letter-spacing:.005em;line-height:.9;text-transform:uppercase;
 font-size:clamp(52px,13.5vw,96px);margin:0;text-shadow:0 2px 18px rgba(0,0,0,.35)}}
h1 .yr{{color:var(--gold)}}
.strip{{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:16px;
 font-family:var(--mono);font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:rgba(255,255,255,.92)}}
.strip .dot{{width:7px;height:7px;border-radius:50%;background:var(--green);
 box-shadow:0 0 0 4px rgba(52,225,176,.18);display:inline-block;margin-right:6px;vertical-align:middle}}

/* ---- cards ---- */
.card{{background:linear-gradient(180deg,var(--card),var(--card2));border:1px solid var(--line);
 border-radius:14px;margin-bottom:10px;overflow:hidden;transition:transform .12s ease,border-color .12s ease}}
.card:hover{{transform:translateY(-1px);border-color:#3a3270}}
summary{{list-style:none;cursor:pointer;display:grid;grid-template-columns:34px 60px 1fr auto;
 gap:14px;align-items:center;padding:14px 16px}}
summary::-webkit-details-marker{{display:none}}
.pos{{font-family:var(--display);font-weight:800;font-size:26px;color:var(--mut);text-align:center}}
.ava{{width:58px;height:58px;border-radius:50%;object-fit:cover;display:grid;place-items:center;
 border:2px solid #34306a}}
.ava-i{{font-family:var(--display);font-weight:800;font-size:24px;color:#fff;letter-spacing:.02em}}
.who{{min-width:0}}
.nm{{display:block;font-weight:700;font-size:23px;line-height:1.05;text-transform:uppercase;letter-spacing:.01em;
 overflow-wrap:anywhere}}
.kit{{display:flex;gap:4px;margin-top:6px}}
.kf{{width:24px;height:17px;border-radius:3px;object-fit:cover;background:#2c2556;
 box-shadow:0 1px 2px rgba(0,0,0,.4)}}
.kf.noflag{{display:inline-block}}
.tot{{text-align:right;line-height:1}}
.tot b{{font-family:var(--display);font-weight:800;font-size:34px;display:block}}
.tot i{{font-family:var(--mono);font-style:normal;font-size:10px;letter-spacing:.18em;color:var(--mut)}}

.rank-1{{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold),0 8px 30px -12px rgba(255,209,102,.5)}}
.rank-1 .pos{{font-size:28px}}
.rank-1 .tot b{{color:var(--gold)}}
.rank-2{{border-color:#9fb0c9}} .rank-2 .tot b{{color:#cfd8e6}}
.rank-3{{border-color:#c08457}} .rank-3 .tot b{{color:#e0a173}}

/* ---- expanded team table ---- */
table.teams{{width:100%;border-collapse:collapse;border-top:1px solid var(--line)}}
table.teams th{{text-align:left;font-family:var(--mono);color:var(--mut);font-weight:500;font-size:11px;
 text-transform:uppercase;letter-spacing:.08em;padding:9px 16px}}
table.teams td{{padding:10px 16px;border-top:1px solid var(--line);font-size:17px}}
.tmwrap{{display:flex;align-items:center;gap:10px;font-weight:600;text-transform:uppercase;letter-spacing:.01em}}
.flag{{width:24px;height:17px;border-radius:3px;object-fit:cover;background:#2c2556;flex:none}}
.flag.noflag{{display:inline-block}}
td.rec,td.gd,td.pt{{font-family:var(--mono);font-variant-numeric:tabular-nums}}
td.rec,td.gd{{color:var(--mut);font-size:13px}}
td.st{{font-family:var(--mono);color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.03em}}
td.pt{{text-align:right;font-weight:700;font-size:15px}}
th:nth-child(2),th:nth-child(3),th:nth-child(5),
td.rec,td.gd,td.pt{{text-align:right}}
th:first-child,td.tm{{text-align:left}}

.scorebox{{margin-top:22px;background:linear-gradient(180deg,var(--card),var(--card2));
 border:1px solid var(--line);border-radius:14px;overflow:hidden}}
.scorebox>summary{{list-style:none;cursor:pointer;display:flex;align-items:center;justify-content:space-between;
 padding:15px 18px;font-family:var(--display);font-weight:800;font-size:20px;
 text-transform:uppercase;letter-spacing:.04em;color:var(--gold)}}
.scorebox>summary::-webkit-details-marker{{display:none}}
.scorebox .chev{{font-size:14px;color:var(--mut);transition:transform .15s ease}}
.scorebox[open] .chev{{transform:rotate(180deg)}}
.keybody{{font-family:var(--mono);color:var(--mut);font-size:14px;font-weight:700;line-height:1.75;
 text-transform:uppercase;letter-spacing:.03em;padding:2px 18px 18px;border-top:1px solid var(--line)}}
@media (max-width:480px){{
  summary{{grid-template-columns:30px 52px 1fr auto;gap:12px}}
  .ava{{width:52px;height:52px}}
  .nm{{font-size:21px}}
}}
@media (prefers-reduced-motion:reduce){{.banner::after{{animation:none;display:none}}.card{{transition:none}}}}
</style></head><body>
<div class="pagebg"{pagebg_attr}></div>
<div class="banner"{banner_style}>
  <div class="in">
    <h1><span class="yr">2026</span> FIFA WORLD CUP<br>DRAFT POOL</h1>
    <div class="strip"><span><span class="dot"></span>Updated {esc(meta['updated'])}</span>
      <span>·</span><span>{meta['done']} matches counted</span>
      <span>·</span><span>tap a manager to see their squad</span></div>
  </div>
</div>
<div class="wrap">
{rows}
<details class="scorebox">
  <summary>Scoring<span class="chev">▾</span></summary>
  <div class="keybody">{key}</div>
</details>
</div></body></html>"""

# ----------------------------------------------------------------------------
def build(matches, std_finish=None, std_flags=None, avatar_files=None):
    std_finish = std_finish or {}
    std_flags = std_flags or {}
    avatar_files = avatar_files or {}
    teams, sb_finish = compute(matches, SCORING)
    # Prefer ESPN's standings ranking; fall back to the table computed from matches.
    finish = std_finish if std_finish else sb_finish
    # Fill in any flags the standings feed has that the scoreboard didn't surface.
    for name, url in std_flags.items():
        if url and not teams[name]["flag"]:
            teams[name]["flag"] = url

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
    return render(standings, teams, finish, SCORING, meta, awards_for, avatar_files)

def main():
    print("Pulling World Cup matches from ESPN…")
    matches = fetch_matches()
    print(f"  {len(matches)} matches found, "
          f"{sum(1 for m in matches if m['completed'])} completed.")
    std_finish, std_flags = fetch_standings()
    print(f"  Standings: {len(std_finish)} group placements read.")
    base = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(base, "pool-site")
    os.makedirs(out_dir, exist_ok=True)

    # copy headshots (if any) into the published folder FIRST, then match them
    src_av = os.path.join(base, "avatars")
    if os.path.isdir(src_av):
        shutil.copytree(src_av, os.path.join(out_dir, "avatars"), dirs_exist_ok=True)
    avatar_files = resolve_avatars(os.path.join(out_dir, "avatars"))
    if avatar_files:
        print(f"  Matched {len(avatar_files)} headshot(s): {', '.join(avatar_files)}")

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(build(matches, std_finish, std_flags, avatar_files))

    # copy custom images (top banner + full-bleed background), if set
    for img in (BANNER_IMAGE, BACKGROUND_IMAGE):
        if img and not img.startswith("http"):
            src_b = os.path.join(base, img)
            if os.path.isfile(src_b):
                shutil.copy(src_b, os.path.join(out_dir, os.path.basename(img)))
                print(f"  Copied {os.path.basename(img)} into the site.")
    print(f"  Wrote {out_dir}/index.html")

if __name__ == "__main__":
    main()
