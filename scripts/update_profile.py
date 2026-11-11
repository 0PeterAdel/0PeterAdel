#!/usr/bin/env python3
"""Refresh verified external merged PRs and a dark GitHub stats card.

Runs in the 0PeterAdel/0PeterAdel profile repository via GitHub Actions.
Only the marked README sections are touched. No third-party dependencies.
"""
from collections import defaultdict
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
README = Path("README.md")
STATS_PATH = Path("assets/github-stats-dark.svg")
START = "<!-- OPEN SOURCE CONTRIBUTIONS START -->"
END = "<!-- OPEN SOURCE CONTRIBUTIONS END -->"
TOKEN = os.environ.get("GH_TOKEN")
LABELS = {"CrossGL/crosstl": "CrossTL", "alltheplaces/alltheplaces": "AllThePlaces"}

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



def verified_open_prs():
    """Discover the author's open PRs in external repos, without counting them as merged."""
    search = f"is:pr is:open author:{USERNAME} -user:{USERNAME} -org:Shift-Core"
    results = []
    seen = set()
    for page in range(1, 11):
        params = urlencode({"q": search, "sort": "updated", "order": "desc", "per_page": 100, "page": page})
        page_data = github_json(f"https://api.github.com/search/issues?{params}")
        if page_data.get("incomplete_results"):
            raise RuntimeError("GitHub search results are incomplete; retaining the current README")
        items = page_data["items"]
        for issue in items:
            match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", issue["html_url"])
            if not match:
                continue
            owner, repo, number = match.groups()
            key = (owner.casefold(), repo.casefold(), int(number))
            if owner.casefold() in EXCLUDED_OWNERS or key in seen:
                continue
            pr = github_json(f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}")
            if (
                pr.get("state") != "open"
                or pr.get("merged_at")
                or pr.get("user", {}).get("login", "").casefold() != USERNAME.casefold()
            ):
                continue
            seen.add(key)
            results.append({
                "repo": f"{owner}/{repo}",
                "number": int(number),
                "title": pr["title"],
                "url": pr["html_url"],
                "updated": pr["updated_at"],
            })
        if len(items) < 100:
            break
    return sorted(results, key=lambda p: p["updated"], reverse=True)


def render_open_prs(prs):
    """Keep work in review clearly separate from accepted merged contributions."""
    if not prs:
        return ""
    entries = [
        f'<li><a href="{escape(pr["url"], quote=True)}">'
        f'{escape(pr["repo"])} #{pr["number"]}</a> — {escape(pr["title"][:110])}</li>'
        for pr in prs[:12]
    ]
    lines = [
        f'<details><summary>⏳ Open external pull requests ({len(prs)})</summary>',
        '<ul>',
        *entries,
        '</ul>',
        '<p align="center"><a href="https://github.com/pulls?q=is%3Apr%20is%3Aopen%20author%3A0PeterAdel">View all open PRs</a></p>',
        '</details>',
    ]
    return "\n".join(lines) + "\n"


def render_contributions(prs, open_prs):
    grouped = defaultdict(list)
    for pr in prs:
        grouped[pr["repo"]].append(pr)
    repos = sorted(grouped, key=lambda r: (max(p["merged"] for p in grouped[r]), r.casefold()), reverse=True)
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
            pair[0] = pair[0].replace('width="50%"', 'colspan="2" width="100%"', 1)
        rows.append("  <tr>\n" + "\n".join(pair) + "\n  </tr>")
    return (
        f"{START}\n"
        '<h3 align="center">🌍 Open Source Contributions</h3>\n'
        '<p align="center">Verified merged pull requests in external communities · Refreshed regularly via GitHub Actions</p>\n'
        '<table align="center">\n' + "\n".join(rows) + '\n</table>\n'
        f"{render_open_prs(open_prs)}{END}"
    )


def render_stats_card():
    """Render a dark statistics card using authenticated GitHub GraphQL data."""
    query = """query($login: String!) {
      user(login: $login) {
        repositories(ownerAffiliations: OWNER, privacy: PUBLIC) { totalCount }
        followers { totalCount }
        pullRequests(states: MERGED) { totalCount }
        contributionsCollection {
          contributionCalendar { totalContributions }
        }
      }
    }"""
    data = github_json(
        "https://api.github.com/graphql",
        {"query": query, "variables": {"login": USERNAME}},
    )
    user = data.get("data", {}).get("user")
    if not user:
        raise RuntimeError("GitHub stats query returned no user data")
    values = [
        ("Contributions / last year", user["contributionsCollection"]["contributionCalendar"]["totalContributions"]),
        ("Merged pull requests", user["pullRequests"]["totalCount"]),
        ("Public repositories", user["repositories"]["totalCount"]),
        ("Followers", user["followers"]["totalCount"]),
    ]
    items = []
    for i, (label, value) in enumerate(values):
        col, row = i % 2, i // 2
        x, y = 32 + col * 239, 89 + row * 82
        items.extend([
            f'<text x="{x}" y="{y}" fill="#58a6ff" font-size="27" font-weight="700">{int(value):,}</text>',
            f'<text x="{x}" y="{y + 23}" fill="#8b949e" font-size="12">{escape(label)}</text>',
        ])
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="510" height="262" '
        'viewBox="0 0 510 262" role="img" aria-label="GitHub statistics">'
        '<rect x="1" y="1" width="508" height="260" rx="11" fill="#0d1117" stroke="#30363d" />'
        '<text x="30" y="36" fill="#e6edf3" font-size="17" font-weight="700">GITHUB STATS</text>'
        '<text x="482" y="36" text-anchor="end" fill="#3fb950" font-size="12">0PeterAdel</text>'
        '<path d="M30 51H480" stroke="#30363d" />'
        + "".join(items)
        + '<path d="M30 213H480" stroke="#30363d" />'
        '<text x="30" y="239" fill="#8b949e" font-size="11">Refreshed regularly via GitHub Actions</text>'
        '</svg>\n'
    )


def replace_block(readme, start, end, replacement):
    if readme.count(start) != 1 or readme.count(end) != 1:
        raise RuntimeError(f"Missing or duplicate README markers: {start}, {end}")
    before, remainder = readme.split(start, 1)
    _, after = remainder.split(end, 1)
    return before + replacement + after


def main():
    readme = README.read_text(encoding="utf-8")
    prs = verified_merged_prs()
    open_prs = verified_open_prs()
    readme = replace_block(readme, START, END, render_contributions(prs, open_prs))
    stats_svg = render_stats_card()
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(stats_svg, encoding="utf-8")
    README.write_text(readme, encoding="utf-8")
    print(f"Updated {len(prs)} merged PRs across {len({p['repo'] for p in prs})} external repositories; {len(open_prs)} open PRs")


if __name__ == "__main__":
    main()
