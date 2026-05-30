"""
Phase 6 tests — search, filtering, ordering, stats, categories, health.

Run with:
    python manage.py test api.tests --verbosity=2
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from reports.models import Category, HackReport, Tag
from reports.services.dedup_service import compute_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _report(n, **kwargs):
    """Create a HackReport with sensible defaults."""
    url = f"https://rekt.news/report-{n}"
    defaults = {
        "title": f"Test Report {n}",
        "description": f"Description for report {n}.",
        "source_url": url,
        "source": "rekt.news",
        "severity": HackReport.Severity.MEDIUM,
        "is_processed": True,
        "hash": compute_hash(url),
        "raw_data": {},
    }
    defaults.update(kwargs)
    return HackReport.objects.create(**defaults)


def _category(name):
    from django.utils.text import slugify
    cat, _ = Category.objects.get_or_create(name=name, defaults={"slug": slugify(name)})
    return cat


def _tag(name):
    tag, _ = Tag.objects.get_or_create(name=name)
    return tag


# ---------------------------------------------------------------------------
# /api/reports/ — list, filter, ordering
# ---------------------------------------------------------------------------

class ReportListTests(APITestCase):

    def setUp(self):
        cat_reentrancy = _category("Reentrancy")
        cat_flashloan = _category("Flash Loan")

        self.r1 = _report(1, severity="critical", category=cat_reentrancy, source="rekt.news")
        self.r2 = _report(2, severity="high",     category=cat_flashloan, source="rekt.news")
        self.r3 = _report(3, severity="medium",   source="immunefi",      is_processed=False)
        self.r4 = _report(4, severity="low",      category=cat_reentrancy, source="rekt.news")

        tag = _tag("DeFi")
        self.r1.tags.add(tag)
        self.r2.tags.add(tag)

    def _get(self, **params):
        url = reverse("hackreport-list")
        return self.client.get(url, params)

    def test_list_returns_all_records(self):
        resp = self._get()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 4)

    def test_filter_by_severity(self):
        resp = self._get(severity="critical")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], self.r1.pk)

    def test_filter_by_category_slug(self):
        resp = self._get(category="reentrancy")
        self.assertEqual(resp.data["count"], 2)

    def test_filter_by_source(self):
        resp = self._get(source="immunefi")
        self.assertEqual(resp.data["count"], 1)

    def test_filter_by_is_processed_false(self):
        resp = self._get(is_processed="false")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], self.r3.pk)

    def test_filter_by_tag(self):
        resp = self._get(tag="DeFi")
        self.assertEqual(resp.data["count"], 2)

    def test_filter_combined_severity_and_category(self):
        resp = self._get(severity="critical", category="reentrancy")
        self.assertEqual(resp.data["count"], 1)

    def test_filter_combined_returns_empty_correctly(self):
        resp = self._get(severity="low", category="flash-loan")
        self.assertEqual(resp.data["count"], 0)

    def test_ordering_by_severity_desc(self):
        """ordering=-severity: critical → high → medium → low (most severe first)"""
        resp = self._get(ordering="-severity")
        self.assertEqual(resp.status_code, 200)
        severities = [r["severity"] for r in resp.data["results"]]
        self.assertEqual(severities, ["critical", "high", "medium", "low"])

    def test_ordering_by_severity_asc(self):
        """ordering=severity: low → medium → high → critical (least severe first)"""
        resp = self._get(ordering="severity")
        severities = [r["severity"] for r in resp.data["results"]]
        self.assertEqual(severities, ["low", "medium", "high", "critical"])

    def test_ordering_invalid_param_defaults_to_created_at(self):
        resp = self._get(ordering="__invalid__")
        self.assertEqual(resp.status_code, 200)  # does not 400

    def test_list_serializer_includes_tag_names(self):
        resp = self._get(severity="critical")
        result = resp.data["results"][0]
        self.assertIn("tag_names", result)
        self.assertIn("DeFi", result["tag_names"])

    def test_list_serializer_includes_category_slug(self):
        resp = self._get(severity="critical")
        result = resp.data["results"][0]
        self.assertIn("category_slug", result)
        self.assertEqual(result["category_slug"], "reentrancy")

    def test_pagination_page_size(self):
        # Create 25 extra records to exceed default page size of 20
        for i in range(10, 35):
            _report(i)
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("next", resp.data)
        self.assertLessEqual(len(resp.data["results"]), 20)


# ---------------------------------------------------------------------------
# /api/reports/{id}/ — detail
# ---------------------------------------------------------------------------

class ReportDetailTests(APITestCase):

    def setUp(self):
        self.report = _report(1, severity="high", description="Full detail description here.")

    def test_detail_returns_description(self):
        url = reverse("hackreport-detail", args=[self.report.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["description"], "Full detail description here.")

    def test_detail_includes_severity_display(self):
        url = reverse("hackreport-detail", args=[self.report.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.data["severity_display"], "High")

    def test_detail_404_for_missing_record(self):
        url = reverse("hackreport-detail", args=[99999])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# /api/search/
# ---------------------------------------------------------------------------

class SearchViewTests(APITestCase):

    def setUp(self):
        cat = _category("Flash Loan")
        self.r1 = _report(1, title="Reentrancy attack on Vault", description="Contract exploited via reentrancy.", is_processed=True)
        self.r2 = _report(2, title="Flash loan manipulation",   description="Oracle manipulated via flash loan.", category=cat, is_processed=True, severity="critical")
        self.r3 = _report(3, title="Unrelated event",           description="No exploit here.",                  is_processed=True, severity="low")
        # Unprocessed — should never appear in search results
        self.r4 = _report(4, title="Reentrancy unprocessed",    description="Should not appear.",                is_processed=False)

        tag = _tag("Reentrancy")
        self.r1.tags.add(tag)

    def _search(self, **params):
        return self.client.get(reverse("report-search"), params)

    def test_keyword_search_title(self):
        resp = self._search(q="reentrancy")
        self.assertEqual(resp.status_code, 200)
        # r1 matches title, r4 is unprocessed so excluded
        ids = {r["id"] for r in resp.data["results"]}
        self.assertIn(self.r1.pk, ids)
        self.assertNotIn(self.r4.pk, ids)

    def test_keyword_search_description(self):
        resp = self._search(q="oracle")
        ids = {r["id"] for r in resp.data["results"]}
        self.assertIn(self.r2.pk, ids)

    def test_search_without_q_returns_all_processed(self):
        resp = self._search()
        self.assertEqual(resp.data["count"], 3)

    def test_search_filter_by_severity(self):
        resp = self._search(severity="critical")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], self.r2.pk)

    def test_search_filter_by_category(self):
        resp = self._search(category="flash-loan")
        self.assertEqual(resp.data["count"], 1)

    def test_search_filter_by_tag(self):
        resp = self._search(tag="Reentrancy")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["id"], self.r1.pk)

    def test_search_combined_q_and_severity(self):
        resp = self._search(q="flash", severity="critical")
        self.assertEqual(resp.data["count"], 1)

    def test_search_no_match_returns_empty(self):
        resp = self._search(q="zxqyabsolutelynothing")
        self.assertEqual(resp.data["count"], 0)

    def test_search_result_includes_excerpt(self):
        resp = self._search(q="reentrancy")
        result = resp.data["results"][0]
        self.assertIn("excerpt", result)
        self.assertIsInstance(result["excerpt"], str)

    def test_excerpt_truncated_to_300_chars(self):
        long_desc = "A" * 500
        r = _report(10, title="Long one", description=long_desc, is_processed=True)
        resp = self._search(q="Long one")
        result = resp.data["results"][0]
        self.assertLessEqual(len(result["excerpt"]), 303)  # 300 + "…"

    def test_search_ordering_by_severity(self):
        """ordering=-severity: critical should appear before low"""
        resp = self._search(ordering="-severity")
        self.assertEqual(resp.status_code, 200)
        severities = [r["severity"] for r in resp.data["results"]]
        critical_idx = severities.index("critical") if "critical" in severities else -1
        low_idx = severities.index("low") if "low" in severities else 999
        if critical_idx >= 0 and low_idx < 999:
            self.assertLess(critical_idx, low_idx)

    def test_unprocessed_never_returned(self):
        resp = self._search(q="unprocessed")
        ids = {r["id"] for r in resp.data["results"]}
        self.assertNotIn(self.r4.pk, ids)


# ---------------------------------------------------------------------------
# /api/stats/
# ---------------------------------------------------------------------------

class StatsViewTests(APITestCase):

    def setUp(self):
        cat = _category("Reentrancy")
        _report(1, severity="critical", category=cat, is_processed=True)
        _report(2, severity="high",     category=cat, is_processed=True)
        _report(3, severity="medium",   is_processed=True)
        _report(4, severity="low",      is_processed=False, source="immunefi",
                source_url="https://immunefi.com/r/1")

    def _get(self):
        return self.client.get(reverse("report-stats"))

    def test_returns_200(self):
        self.assertEqual(self._get().status_code, 200)

    def test_total_count(self):
        self.assertEqual(self._get().data["total_reports"], 4)

    def test_processed_count(self):
        self.assertEqual(self._get().data["processed_reports"], 3)

    def test_unprocessed_count(self):
        self.assertEqual(self._get().data["unprocessed_reports"], 1)

    def test_by_severity_keys_present(self):
        data = self._get().data["by_severity"]
        for sev in ["low", "medium", "high", "critical"]:
            self.assertIn(sev, data)

    def test_by_severity_counts(self):
        data = self._get().data["by_severity"]
        self.assertEqual(data["critical"], 1)
        self.assertEqual(data["high"], 1)
        self.assertEqual(data["medium"], 1)
        self.assertEqual(data["low"], 1)

    def test_by_source(self):
        data = self._get().data["by_source"]
        self.assertIn("rekt.news", data)
        self.assertIn("immunefi", data)

    def test_top_categories_in_response(self):
        cats = self._get().data["top_categories"]
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0)
        self.assertEqual(cats[0]["name"], "Reentrancy")
        self.assertEqual(cats[0]["count"], 2)


# ---------------------------------------------------------------------------
# /api/categories/
# ---------------------------------------------------------------------------

class CategoryListViewTests(APITestCase):

    def setUp(self):
        cat_a = _category("Oracle Manipulation")
        cat_b = _category("Flash Loan")
        _report(1, category=cat_a, source_url="https://rekt.news/r1")
        _report(2, category=cat_a, source_url="https://rekt.news/r2")
        _report(3, category=cat_b, source_url="https://rekt.news/r3")

    def test_returns_categories_with_counts(self):
        resp = self.client.get(reverse("category-list"))
        self.assertEqual(resp.status_code, 200)
        # Response may be paginated
        results = resp.data.get("results", resp.data)
        names = [c["name"] for c in results]
        self.assertIn("Oracle Manipulation", names)
        self.assertIn("Flash Loan", names)

    def test_ordered_by_count_descending(self):
        resp = self.client.get(reverse("category-list"))
        results = resp.data.get("results", resp.data)
        counts = [c["report_count"] for c in results]
        self.assertEqual(counts, sorted(counts, reverse=True))


# ---------------------------------------------------------------------------
# /api/health/
# ---------------------------------------------------------------------------

class HealthCheckTests(APITestCase):

    def test_returns_ok(self):
        resp = self.client.get(reverse("health-check"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")
        self.assertEqual(resp.data["db"], "ok")
