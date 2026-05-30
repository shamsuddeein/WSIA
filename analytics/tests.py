"""
Phase 4 tests — analytics cleaning, severity, category, and tag sync.

Run with:
    python manage.py test analytics.tests --verbosity=2
"""

from django.test import TestCase

from analytics.cleaner import clean_text, extract_max_dollar_amount, normalize_report
from analytics.tag_sync import sync_tags
from reports.models import Category, HackReport, Tag
from reports.services.category_service import assign_category, assign_severity_smart
from reports.services.dedup_service import compute_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(**kwargs) -> HackReport:
    """Create a minimal HackReport for testing."""
    defaults = {
        "title": "Test Report",
        "description": "A test description.",
        "source_url": f"https://rekt.news/test-{HackReport.objects.count()}",
        "source": "rekt.news",
        "is_processed": False,
        "raw_data": {},
    }
    defaults.update(kwargs)
    defaults["hash"] = compute_hash(defaults["source_url"])
    return HackReport.objects.create(**defaults)


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------

class CleanTextTests(TestCase):

    def test_strips_html_tags(self):
        self.assertEqual(clean_text("<b>Bold</b> text"), "Bold text")

    def test_collapses_whitespace(self):
        self.assertEqual(clean_text("foo    bar   baz"), "foo bar baz")

    def test_strips_leading_trailing(self):
        self.assertEqual(clean_text("  hello  "), "hello")

    def test_none_returns_empty(self):
        self.assertEqual(clean_text(None), "")

    def test_empty_returns_empty(self):
        self.assertEqual(clean_text(""), "")

    def test_unescapes_html_entities(self):
        self.assertEqual(clean_text("AT&amp;T &mdash; Leader"), "AT&T — Leader")

    def test_removes_control_characters(self):
        text = "hello\x00world\x01foo"
        result = clean_text(text)
        self.assertNotIn("\x00", result)
        self.assertNotIn("\x01", result)
        self.assertIn("hello", result)

    def test_preserves_newlines(self):
        result = clean_text("line one\nline two")
        self.assertIn("\n", result)

    def test_unicode_normalisation(self):
        # café — NFC normalisation should give consistent output
        result = clean_text("caf\u00e9")
        self.assertEqual(result, "café")

    def test_nested_html(self):
        html = "<div><p>Attacker <strong>drained</strong> $5M.</p></div>"
        result = clean_text(html)
        self.assertNotIn("<", result)
        self.assertIn("drained", result)


# ---------------------------------------------------------------------------
# extract_max_dollar_amount
# ---------------------------------------------------------------------------

class DollarAmountTests(TestCase):

    def test_million_long(self):
        self.assertEqual(extract_max_dollar_amount("$5 million drained"), 5_000_000)

    def test_million_short_m(self):
        self.assertEqual(extract_max_dollar_amount("$100M exploit"), 100_000_000)

    def test_thousand_k(self):
        self.assertEqual(extract_max_dollar_amount("$500k stolen"), 500_000)

    def test_decimal_million(self):
        self.assertAlmostEqual(
            extract_max_dollar_amount("$3.98 million across three chains"),
            3_980_000,
            places=0,
        )

    def test_picks_largest(self):
        result = extract_max_dollar_amount("$1M here and $50M there")
        self.assertEqual(result, 50_000_000)

    def test_no_amount_returns_zero(self):
        self.assertEqual(extract_max_dollar_amount("no money mentioned"), 0.0)

    def test_billion(self):
        self.assertEqual(extract_max_dollar_amount("$1 billion hack"), 1_000_000_000)


# ---------------------------------------------------------------------------
# assign_severity_smart
# ---------------------------------------------------------------------------

class SeverityTests(TestCase):

    def test_critical_by_amount(self):
        self.assertEqual(assign_severity_smart("Attacker stole $50 million"), "critical")

    def test_high_by_amount(self):
        self.assertEqual(assign_severity_smart("$10M drained from protocol"), "high")

    def test_medium_by_amount(self):
        self.assertEqual(assign_severity_smart("$500k lost in exploit"), "medium")

    def test_critical_by_keyword_drained(self):
        # No dollar amount — falls to keyword rule
        self.assertEqual(assign_severity_smart("The vault was drained"), "critical")

    def test_default_medium(self):
        self.assertEqual(assign_severity_smart("Something vague happened"), "medium")

    def test_millions_keyword_fallback(self):
        self.assertEqual(assign_severity_smart("Attacker made off with millions"), "high")


# ---------------------------------------------------------------------------
# assign_category
# ---------------------------------------------------------------------------

class CategoryTests(TestCase):

    def test_reentrancy(self):
        cat = assign_category("Classic reentrancy attack on the vault")
        self.assertIsNotNone(cat)
        self.assertEqual(cat.name, "Reentrancy")

    def test_flash_loan(self):
        cat = assign_category("Flash loan manipulation drained the pool")
        self.assertIsNotNone(cat)
        self.assertEqual(cat.name, "Flash Loan")

    def test_oracle_manipulation(self):
        cat = assign_category("Oracle price manipulation allowed exploit")
        self.assertIsNotNone(cat)
        self.assertEqual(cat.name, "Oracle Manipulation")

    def test_bridge_exploit(self):
        cat = assign_category("Cross-chain bridge exploit discovered")
        self.assertIsNotNone(cat)
        self.assertEqual(cat.name, "Bridge Exploit")

    def test_supply_chain(self):
        cat = assign_category("Supply chain attack via malicious npm package")
        self.assertIsNotNone(cat)
        self.assertEqual(cat.name, "Supply Chain Attack")

    def test_no_match_returns_none(self):
        cat = assign_category("Something completely unrelated")
        self.assertIsNone(cat)

    def test_creates_category_if_missing(self):
        self.assertEqual(Category.objects.count(), 0)
        assign_category("Reentrancy vulnerability")
        self.assertEqual(Category.objects.count(), 1)

    def test_does_not_duplicate_category(self):
        assign_category("Reentrancy in contract A")
        assign_category("Another reentrancy attack")
        self.assertEqual(Category.objects.filter(name="Reentrancy").count(), 1)


# ---------------------------------------------------------------------------
# sync_tags
# ---------------------------------------------------------------------------

class TagSyncTests(TestCase):

    def test_creates_tags_from_raw_data(self):
        report = _make_report(raw_data={"tags": ["Flash Loan", "DeFi"]})
        sync_tags(report)
        tag_names = set(report.tags.values_list("name", flat=True))
        self.assertIn("Flash Loan", tag_names)
        self.assertIn("DeFi", tag_names)

    def test_no_duplicate_tags(self):
        report = _make_report(raw_data={"tags": ["Reentrancy", "Reentrancy"]})
        sync_tags(report)
        self.assertEqual(report.tags.filter(name="Reentrancy").count(), 1)

    def test_empty_tags_is_noop(self):
        report = _make_report(raw_data={"tags": []})
        sync_tags(report)
        self.assertEqual(report.tags.count(), 0)

    def test_no_tags_key_is_noop(self):
        report = _make_report(raw_data={})
        sync_tags(report)
        self.assertEqual(report.tags.count(), 0)

    def test_blank_tag_names_skipped(self):
        report = _make_report(raw_data={"tags": ["", "  ", "Valid Tag"]})
        sync_tags(report)
        tag_names = list(report.tags.values_list("name", flat=True))
        self.assertNotIn("", tag_names)
        self.assertIn("Valid Tag", tag_names)

    def test_does_not_remove_existing_tags(self):
        existing_tag = Tag.objects.create(name="Existing")
        report = _make_report(raw_data={"tags": ["New Tag"]})
        report.tags.add(existing_tag)
        sync_tags(report)
        tag_names = set(report.tags.values_list("name", flat=True))
        self.assertIn("Existing", tag_names)
        self.assertIn("New Tag", tag_names)


# ---------------------------------------------------------------------------
# normalize_report (integration)
# ---------------------------------------------------------------------------

class NormalizeReportTests(TestCase):

    def test_full_pipeline(self):
        report = _make_report(
            title="  <b>Flash Loan Attack</b>  ",
            description="<p>Attacker used a flash loan to drain $5 million from the pool.</p>",
            raw_data={"tags": ["Flash Loan", "DeFi"]},
        )
        self.assertFalse(report.is_processed)

        normalize_report(report)
        report.refresh_from_db()

        self.assertTrue(report.is_processed)
        self.assertNotIn("<b>", report.title)
        self.assertNotIn("<p>", report.description)
        self.assertEqual(report.title, "Flash Loan Attack")
        self.assertEqual(report.severity, "high")       # $5M → high
        self.assertIsNotNone(report.category)
        self.assertEqual(report.category.name, "Flash Loan")
        self.assertIn("Flash Loan", report.tags.values_list("name", flat=True))

    def test_does_not_overwrite_existing_category(self):
        cat = Category.objects.create(name="Manual Category")
        report = _make_report(
            title="Reentrancy exploit",
            description="Some text",
            raw_data={},
        )
        report.category = cat
        report.save()

        normalize_report(report)
        report.refresh_from_db()

        # Category should NOT have been changed by normalization
        self.assertEqual(report.category.name, "Manual Category")

    def test_sets_is_processed_true(self):
        report = _make_report()
        normalize_report(report)
        report.refresh_from_db()
        self.assertTrue(report.is_processed)

    def test_critical_severity_large_amount(self):
        report = _make_report(
            title="Massive bridge hack",
            description="$100 million drained across multiple chains.",
            raw_data={},
        )
        normalize_report(report)
        report.refresh_from_db()
        self.assertEqual(report.severity, "critical")
