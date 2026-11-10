#!/usr/bin/env python3
"""Refresh verified external merged PRs and the GitHub contribution calendar.

Runs in the 0PeterAdel/0PeterAdel profile repository via GitHub Actions.
Only the marked README sections are touched. No third-party dependencies.
"""
from collections import defaultdict
from datetime import date
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import json
import os
import re

USERNAME = "0PeterAdel"
# Personal repositories and the author's own Shift-Core organization are not
# external open-source contributions.
EXCLUDED_OWNERS = {USERNAME.casefold(), "shift-core"}
PROFILE_REPO = f"{USERNAME}/{USERNAME}"
README = Path("README.md")
SVG_PATH = Path("assets/contributions.svg")
START = "<!-- OPEN SOURCE CONTRIBUTIONS START -->"
END = "<!-- OPEN SOURCE CONTRIBUTIONS END -->"
GRAPH_START = "<!-- PROFILE ACTIVITY START -->"
GRAPH_END = "<!-- PROFILE ACTIVITY END -->"
TOKEN = os.environ.get("GH_TOKEN")
LABELS = {"CrossGL/crosstl": "CrossTL", "alltheplaces/alltheplaces": "AllThePlaces"}
COLORS = {
    "NONE": "#161b22", "FIRST_QUARTILE": "#0e4429",
    "SECOND_QUARTILE": "#006d32", "THIRD_QUARTILE": "#26a641",
    "FOURTH_QUARTILE": "#39d353",
}


def github_json(url, payload=None):
    if not TOKEN:
        raise RuntimeError("GH_TOKEN is required")
    request = Request(
        url, data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "0PeterAdel-profile-updater",
        },
    )
    with urlopen(request, timeout=40) as response:
        result = json.load(response)
    if isinstance(result, dict) and result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {result['errors']}")
    return result


def verified_merged_prs():
    search = f"is:pr is:merged author:{USERNAME} -user:{USERNAME} -org:Shift-Core"
    results = []
    for page in range(1, 11):
        params = urlencode({"q": search, "sort": "updated", "order": "desc", "per_page": 100, "page": page})
        page_data = github_json(f"https://api.github.com/search/issues?{params}")
        items = page_data["items"]
        if page == 1 and not items:
            raise RuntimeError("Search returned zero merged PRs; preserving existing README")
        for issue in items:
            match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", issue["html_url"])
            if not match:
                continue
            owner, repo, number = match.groups()
            if owner.casefold() in EXCLUDED_OWNERS:
                continue
            # Verify each result as merged by this author, not merely closed.
            pr = github_json(f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}")
            if not pr.get("merged_at") or pr.get("user", {}).get("login", "").casefold() != USERNAME.casefold():
                continue
            results.append({
                "repo": f"{owner}/{repo}",
                "number": int(number),
                "title": pr["title"],
                "url": pr["html_url"],
                "merged": pr["merged_at"],
            })
        if len(items) < 100:
            break
    if not results:
        raise RuntimeError("No verified external merged PRs; refusing to erase contributions")
    return results


def render_contributions(prs):
    grouped = defaultdict(list)
    for pr in prs:
        grouped[pr["repo"]].append(pr)
    repos = sorted(grouped, key=lambda r: (-max(p["merged"] for p in grouped[r]), r.casefold()))
    cards = []
    for repo in repos[:10]:
        recent = sorted(grouped[repo], key=lambda p: p["merged"], reverse=True)
        display = LABELS.get(repo, repo.split("/")[-1].replace("-", " "))
        count = len(recent)
        badges = []
        for pr in recent[:4]:
            badges.append(
                f'<a href="{escape(pr["url"], quote=True)}">'
                f'<img alt="PR #{pr["number"]} merged" '
                f'src="https://img.shields.io/badge/PR%20%23{pr["number"]}-MERGED-2ea44f?style=flat-square&amp;logo=github&amp;logoColor=white" /></a>'
            )
        if count > 4:
            badges.append(f'<small>+{count - 4} more merged PRs</small>')
        repo_link = f"https://github.com/{quote(repo, safe='/')}"
        card = (
            '    <td align="center" valign="top" width="50%">\n'
            f'      <a href="{repo_link}"><img alt="{escape(display, quote=True)}" '
            f'src="https://img.shields.io/badge/{quote(display.replace("-", "--"), safe="")}-OPEN%20SOURCE-0e75b6?style=for-the-badge&amp;logo=github&amp;logoColor=white" /></a>\n'
            f'      <p><b>{count} merged PR{"s" if count != 1 else ""}</b><br />'
            f'<sub>{escape(recent[0]["title"][:115])}</sub></p>\n'
            f'      {" &nbsp; ".join(badges)}\n'
            '    </td>'
        )
        cards.append(card)
    rows = []
    for idx in range(0, len(cards), 2):
        pair = cards[idx:idx + 2]
        if len(pair) == 1:
            pair.append('    <td width="50%"></td>')
        rows.append("  <tr>\n" + "\n".join(pair) + "\n  </tr>")
    return (
        f"{START}\n"
        '<h3 align="center">🌍 Open Source Contributions</h3>\n'
        '<p align="center">Verified merged pull requests in open-source communities · Automatically updated daily</p>\n'
        '<table align="center">\n' + "\n".join(rows) + '\n</table>\n'
        f"{END}"
    )


def render_graph():
    query = """query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount contributionLevel } }
          }
        }
      }
    }"""
    data = github_json("https://api.github.com/graphql", {"query": query, "variables": {"login": USERNAME}})
    calendar = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = calendar["weeks"]
    if not weeks or not any(w["contributionDays"] for w in weeks):
        raise RuntimeError("Empty GitHub contribution calendar")
    side, gap, left, top = 11, 3, 35, 59
    width, height = max(750, left + len(weeks) * (side + gap) + 20), 194
    squares = []
    months = []
    seen = set()
    for col, week in enumerate(weeks):
        for day in week["contributionDays"]:
            d = date.fromisoformat(day["date"])
            x, y = left + col * (side + gap), top + ((d.weekday() + 1) % 7) * (side + gap)
            level = day["contributionLevel"]
            fill = COLORS.get(level, COLORS["NONE"])
            tip = escape(f'{day["date"]}: {day["contributionCount"]} contributions', quote=True)
            squares.append(f'<rect x="{x}" y="{y}" width="{side}" height="{side}" rx="2" fill="{fill}"><title>{tip}</title></rect>')
            key = (d.year, d.month)
            if d.day <= 7 and key not in seen:
                months.append(f'<text x="{x}" y="47" fill="#8b949e" font-size="10">{d.strftime("%b")}</text>')
                seen.add(key)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="GitHub contribution activity for the past year">'
        f'<title>{USERNAME} — GitHub contributions</title>'
        f'<rect width="{width}" height="{height}" rx="12" fill="#0d1117" />'
        f'<text x="23" y="25" fill="#e6edf3" font-size="15" font-weight="600" font-family="Arial,sans-serif">GITHUB CONTRIBUTIONS</text>'
        f'<text x="{width - 23}" y="25" text-anchor="end" fill="#39d353" font-size="13" font-family="Arial,sans-serif">'
        f'{calendar["totalContributions"]} in the last year</text>'
        '<g font-family="Arial,sans-serif">' + "".join(months)
        + '<text x="6" y="81" fill="#8b949e" font-size="10">Mon</text>'
        + '<text x="6" y="109" fill="#8b949e" font-size="10">Wed</text>'
        + '<text x="6" y="137" fill="#8b949e" font-size="10">Fri</text>'
        + "</g>" + "".join(squares)
        + f'<text x="{width - 20}" y="173" text-anchor="end" fill="#8b949e" font-size="11" font-family="Arial,sans-serif">Updated {date.today().isoformat()} · GitHub GraphQL</text>'
        + "</svg>\n"
    )
    return svg


def replace_block(readme, start, end, replacement):
    if readme.count(start) != 1 or readme.count(end) != 1:
        raise RuntimeError(f"Missing or duplicate README markers: {start}, {end}")
    before, remainder = readme.split(start, 1)
    _, after = remainder.split(end, 1)
    return before + replacement + after


def main():
    readme = README.read_text(encoding="utf-8")
    prs = verified_merged_prs()
    readme = replace_block(readme, START, END, render_contributions(prs))
    try:
        svg = render_graph()
    except Exception as exc:
        print(f"::warning::Could not refresh contribution graph: {exc}")
        svg = None
    if svg is not None:
        SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
        SVG_PATH.write_text(svg, encoding="utf-8")
        graph_html = (
            f'{GRAPH_START}\n<div align="center">\n'
            f'  <a href="https://github.com/{USERNAME}"><img width="100%" '
            f'src="https://raw.githubusercontent.com/{PROFILE_REPO}/main/assets/contributions.svg" '
            f'alt="GitHub contribution activity — automatically refreshed" /></a>\n'
            f'</div>\n{GRAPH_END}'
        )
        readme = replace_block(readme, GRAPH_START, GRAPH_END, graph_html)
    README.write_text(readme, encoding="utf-8")
    print(f"Updated {len(prs)} merged PRs across {len({p['repo'] for p in prs})} external repositories")


if __name__ == "__main__":
    main()
