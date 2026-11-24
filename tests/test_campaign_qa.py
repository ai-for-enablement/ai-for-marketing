"""Unit tests for skills/campaign-qa/scripts/campaign_qa.py. Run: python3 -m unittest discover tests"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "campaign-qa" / "scripts"))
import campaign_qa as cq  # noqa: E402  # pyright: ignore[reportMissingImports]

CONFIG = """
[campaign]
name = "fall-promo"
name_pattern = "^[a-z0-9]+(-[a-z0-9]+)*$"

[utm]
required = ["utm_source", "utm_medium", "utm_campaign"]
allowed_mediums = ["email", "social"]
allowed_sources = ["newsletter", "linkedin"]
lowercase = true
tracked_domains = ["shop.example"]

[utm.channels]
email = "email"
social = "social"

[links]
blocked_hosts = ["staging.shop.example"]
require_https = true

[[facts]]
name = "promo code"
pattern = '\\b[A-Z]{4,}\\d{2}\\b'
expected = "FALL10"

[[facts]]
name = "end date"
pattern = '\\bends\\s+(October\\s+\\d{1,2})\\b'
expected = "October 31"

[landing]
file = "landing.html"
tracking_patterns = ['gtag/js']
required_form_fields = ["email"]
hidden_utm_fields = true

[claims]
flag_words = ["best", "guaranteed"]
flag_numbers = true
"""

GOOD_LINK = "https://shop.example/fall?utm_source=newsletter&utm_medium=email&utm_campaign=fall-promo"

LANDING = """<html><head><title>Fall promo</title>
<meta name="description" content="Fall promo.">
<script src="https://www.googletagmanager.com/gtag/js?id=G-1"></script></head>
<body><p>Use code FALL10. The promo ends October 31.</p>
<img src="/a.jpg" alt="A jacket">
<form action="https://shop.example/subscribe?utm_source=newsletter&utm_medium=email&utm_campaign=fall-promo">
<input name="email"><input type="hidden" name="utm_source">
<input type="hidden" name="utm_medium"><input type="hidden" name="utm_campaign">
</form></body></html>
"""


class CampaignCase(unittest.TestCase):
    def make(self, assets: dict[str, str], config: str = CONFIG) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "campaign.toml").write_text(config, encoding="utf-8")
        files = {"landing.html": LANDING, **assets}
        for name, text in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return root

    def checks(self, assets: dict[str, str], config: str = CONFIG) -> list[tuple[str, str]]:
        rep = cq.run(self.make(assets, config))
        return [(f.check, f.asset) for f in rep.findings]

    def email(self, body: str) -> dict[str, str]:
        return {"email/launch.md": body}


class CleanCampaign(CampaignCase):
    def test_clean_campaign_has_no_findings(self):
        found = self.checks({
            "email/launch.md": f"Use code FALL10. The promo ends October 31.\n\n[Shop now]({GOOD_LINK})\n",
            "social/linkedin.md": "Fall is here. https://shop.example/fall?utm_source=linkedin&utm_medium=social&utm_campaign=fall-promo\n",
        })
        self.assertEqual(found, [])

    def test_untracked_domains_need_no_utm(self):
        self.assertEqual(self.checks(self.email("Read https://news.other.example/story\n")), [])

    def test_static_files_need_no_utm(self):
        self.assertEqual(self.checks(self.email("![logo](https://shop.example/img/logo.png)\n")), [])

    def test_html_image_urls_are_not_links(self):
        html = '<p><img src="https://shop.example/hero.jpg" alt="Hero"></p>'
        self.assertEqual(self.checks({"email/launch.html": html}), [])


class LinkChecks(CampaignCase):
    def test_blocked_host(self):
        url = GOOD_LINK.replace("shop.example", "staging.shop.example")
        self.assertIn(("blocked-host", "email/launch.md"), self.checks(self.email(url)))

    def test_insecure_link(self):
        self.assertIn(("insecure-link", "email/launch.md"), self.checks(self.email(GOOD_LINK.replace("https", "http"))))

    def test_doubled_question_mark(self):
        self.assertIn(("malformed-url", "email/launch.md"), self.checks(self.email(GOOD_LINK.replace("?", "??"))))

    def test_space_in_url(self):
        url = GOOD_LINK.replace("newsletter", "news%20letter")
        found = self.checks(self.email(url))
        self.assertIn(("malformed-url", "email/launch.md"), found)
        self.assertIn(("utm-format", "email/launch.md"), found)


class UtmChecks(CampaignCase):
    def test_missing_campaign(self):
        url = GOOD_LINK.replace("&utm_campaign=fall-promo", "")
        self.assertIn(("utm-missing", "email/launch.md"), self.checks(self.email(url)))

    def test_uppercase_value(self):
        url = GOOD_LINK.replace("fall-promo", "Fall-Promo")
        self.assertIn(("utm-case", "email/launch.md"), self.checks(self.email(url)))

    def test_wrong_campaign(self):
        url = GOOD_LINK.replace("fall-promo", "summer-promo")
        self.assertIn(("utm-campaign", "email/launch.md"), self.checks(self.email(url)))

    def test_medium_not_allowed(self):
        url = GOOD_LINK.replace("utm_medium=email", "utm_medium=paid")
        self.assertIn(("utm-medium", "email/launch.md"), self.checks(self.email(url)))

    def test_medium_wrong_for_channel_folder(self):
        url = GOOD_LINK.replace("utm_medium=email", "utm_medium=social")
        self.assertIn(("utm-channel", "email/launch.md"), self.checks(self.email(url)))

    def test_unknown_source_is_a_warning(self):
        url = GOOD_LINK.replace("newsletter", "partner")
        rep = cq.run(self.make(self.email(url)))
        self.assertEqual([(f.check, f.severity) for f in rep.findings], [("utm-source", "warning")])


class FactChecks(CampaignCase):
    def test_promo_code_typo(self):
        self.assertIn(("fact-mismatch", "email/launch.md"), self.checks(self.email("Use code FALL01 today.\n")))

    def test_capture_group_compares_only_the_group(self):
        self.assertEqual(self.checks(self.email("The promo ends October 31, so hurry.\n")), [])
        self.assertIn(("fact-mismatch", "email/launch.md"), self.checks(self.email("The promo ends October 30.\n")))

    def test_html_tags_are_ignored(self):
        html = "<p>Use code <strong>FALL10</strong>. The promo ends <b>October 31</b>.</p>"
        self.assertEqual(self.checks({"email/launch.html": html}), [])


class LandingChecks(CampaignCase):
    def test_missing_landing_page(self):
        config = CONFIG.replace('file = "landing.html"', 'file = "missing.html"')
        self.assertIn(("landing-missing", "missing.html"), self.checks({}, config))

    def test_missing_tracking_and_hidden_fields(self):
        bare = LANDING.replace("gtag/js", "other.js").replace('<input type="hidden" name="utm_source">', "")
        found = self.checks({"landing.html": bare})
        self.assertIn(("tracking", "landing.html"), found)
        self.assertEqual(found.count(("utm-capture", "landing.html")), 1)

    def test_missing_meta(self):
        bare = LANDING.replace("<title>Fall promo</title>", "").replace('<meta name="description" content="Fall promo.">', "")
        self.assertEqual(self.checks({"landing.html": bare}).count(("page-meta", "landing.html")), 2)

    def test_missing_alt_text(self):
        self.assertIn(("alt-text", "landing.html"), self.checks({"landing.html": LANDING.replace(' alt="A jacket"', "")}))


class Claims(CampaignCase):
    def test_flag_words_and_unapproved_numbers_go_to_review(self):
        rep = cq.run(self.make(self.email("Our best jackets. Save 40% this week.\n")))
        self.assertEqual([(f.check, f.severity) for f in rep.findings], [("claim", "review")])
        self.assertIn("best", rep.findings[0].detail)
        self.assertIn("40%", rep.findings[0].detail)

    def test_naming_convention(self):
        config = CONFIG.replace('name = "fall-promo"', 'name = "Fall Promo"')
        self.assertIn(("naming", "campaign.toml"), self.checks({}, config))


class Cli(CampaignCase):
    def test_exit_codes(self):
        root = self.make(self.email("Use code FALL01.\n"))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cq.main([str(root)]), 1)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cq.main([str(root / "nope")]), 2)
        clean = self.make({})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cq.main([str(clean), "--format", "json"]), 0)


if __name__ == "__main__":
    unittest.main()
