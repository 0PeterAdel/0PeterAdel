"""Regression tests for dynamic external contributions in the GitHub profile."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_profile


class ProfileUpdateTests(unittest.TestCase):
    def test_discover_external_merged_and_open_prs_separately(self):
        def fake_github_json(url, payload=None):
            if "/search/issues?" in url:
                query = parse_qs(urlparse(url).query)["q"][0]
                if "is:merged" in query:
                    return {
                        "items": [
                            {"html_url": "https://github.com/CrossGL/crosstl/pull/4362"},
                            {"html_url": "https://github.com/alltheplaces/alltheplaces/pull/20474"},
                            {"html_url": "https://github.com/0PeterAdel/okal/pull/148"},
                        ]
                    }
                if "is:open" in query:
                    return {
                        "items": [
                            {"html_url": "https://github.com/CrossGL/crosstl/pull/4375"},
                            {"html_url": "https://github.com/alltheplaces/alltheplaces/pull/20473"},
                        ]
                    }
                raise AssertionError(f"Unexpected search: {query}")
            number = int(url.rsplit("/", 1)[-1])
            records = {
                4362: ("CrossGL/crosstl", "merged", "2026-11-11T17:10:32Z"),
                20474: ("alltheplaces/alltheplaces", "merged", "2026-11-11T14:15:06Z"),
                4375: ("CrossGL/crosstl", "open", None),
                20473: ("alltheplaces/alltheplaces", "open", None),
            }
            repo, state, merged = records[number]
            return {
                "user": {"login": "0PeterAdel"},
                "state": "closed" if merged else state,
                "merged_at": merged,
                "title": f"Test contribution {number}",
                "html_url": f"https://github.com/{repo}/pull/{number}",
                "updated_at": "2026-11-11T19:30:00Z",
            }

        with patch.object(update_profile, "github_json", side_effect=fake_github_json):
            merged = update_profile.verified_merged_prs()
            opened = update_profile.verified_open_prs()

        self.assertEqual({p["number"] for p in merged}, {4362, 20474})
        self.assertEqual({p["number"] for p in opened}, {4375, 20473})
        self.assertTrue(all(p["merged"] for p in merged))
        self.assertTrue(all("updated" in p for p in opened))

    def test_render_merged_and_open_status_and_escape_titles(self):
        merged = [
            {"repo": "CrossGL/crosstl", "number": 4362,
             "title": "Fix <mixed> integer types",
             "url": "https://github.com/CrossGL/crosstl/pull/4362",
             "merged": "2026-11-11T17:10:32Z"},
            {"repo": "CrossGL/crosstl", "number": 4384,
             "title": "Fix DirectX type tests",
             "url": "https://github.com/CrossGL/crosstl/pull/4384",
             "merged": "2026-11-11T13:42:59Z"},
        ]
        opened = [
            {"repo": "CrossGL/crosstl", "number": 4375,
             "title": "Fix & verify parser",
             "url": "https://github.com/CrossGL/crosstl/pull/4375",
             "updated": "2026-11-11T19:30:00Z"},
        ]
        html = update_profile.render_contributions(merged, opened)
        self.assertIn("2 merged PRs", html)
        self.assertIn("PR%20%234362-MERGED", html)
        self.assertIn("Open external pull requests (1)", html)
        self.assertIn("crosstl #4375", html)
        self.assertIn("Fix &amp; verify parser", html)
        self.assertIn("Fix &lt;mixed&gt; integer types", html)
        self.assertNotIn("PR%20%234375-MERGED", html)
        self.assertEqual(html.count(update_profile.START), 1)
        self.assertEqual(html.count(update_profile.END), 1)

    def test_readme_replacement_preserves_unrelated_sections(self):
        original = "Header\n" + update_profile.START + "\nstale\n" + update_profile.END + "\nFooter\n"
        new_section = update_profile.render_contributions(
            [{"repo": "PXDiv/Div-Acer-Manager-Max", "number": 280,
              "title": "Fix test", "url": "https://github.com/PXDiv/Div-Acer-Manager-Max/pull/280",
              "merged": "2026-11-10T19:00:00Z"}],
            [],
        )
        result = update_profile.replace_block(
            original, update_profile.START, update_profile.END, new_section
        )
        self.assertTrue(result.startswith("Header\n"))
        self.assertTrue(result.endswith("\nFooter\n"))
        self.assertNotIn("stale", result)

    def test_incomplete_merged_search_is_rejected(self):
        with patch.object(update_profile, "github_json", return_value={
            "items": [], "incomplete_results": True
        }):
            with self.assertRaisesRegex(RuntimeError, "Incomplete"):
                update_profile.verified_merged_prs()

    def test_oversized_search_is_rejected(self):
        with patch.object(update_profile, "github_json", return_value={
            "items": [], "total_count": 1001
        }):
            with self.assertRaisesRegex(RuntimeError, "oversized"):
                update_profile.verified_open_prs()

    def test_five_merges_count_all_but_show_four_badges(self):
        prs = [{"repo": "example/project", "number": n, "title": "Fix",
                "url": f"https://github.com/example/project/pull/{n}",
                "merged": f"2026-11-{n:02d}T00:00:00Z"} for n in range(1, 6)]
        html = update_profile.render_contributions(prs, [])
        self.assertIn("5 merged PRs", html)
        self.assertIn("+1 more merged PRs", html)
        self.assertEqual(html.count('-MERGED-'), 4)
        self.assertIn("Last refreshed:", html)

    def test_missing_merged_search_results_must_not_erase_readme(self):
        with patch.object(update_profile, "github_json", return_value={"items": []}):
            with self.assertRaisesRegex(RuntimeError, "zero merged PRs"):
                update_profile.verified_merged_prs()


if __name__ == "__main__":
    unittest.main()

