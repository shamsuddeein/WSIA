from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from reports.scraper import BASE_URL


INDEX_HTML = """
<html>
  <body>
    <script src="/_next/static/chunks/pages/_app-test.js"></script>
  </body>
</html>
"""

BUNDLE_JS = r"""
self.webpackChunk_N_E.push([[2888],{
  56426:function(e){
    e.exports=JSON.parse('{"timestamp":1,"posts":[{"date":"5/29/2026","title":"Alpha Hack","tags":["DeFi","Rekt"],"excerpt":"Alpha description.","slug":"alpha-hack"},{"date":"5/28/2026","title":"Beta Hack","tags":["Bridge"],"excerpt":"Beta description.","slug":"beta-hack"}]}')
  },
  11024:function(e){
    e.exports=JSON.parse('{"timestamp":1,"posts":[{"date":"5/29/2026","title":"测试","tags":[],"excerpt":"中文","slug":"zh-alpha"}]}')
  }
}]);
"""

ARTICLE_HTML = """
<article class="post">
  <h2 class="post-title"><a href="/alpha">Alpha Hack</a></h2>
  <div class="post-excerpt"><p>Alpha description.</p></div>
  <div class="post-meta">
    <time>Friday, May 29, 2026</time>
    <a href="/?tag=DeFi">DeFi</a>
  </div>
</article>
"""


class DummyResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.content = text.encode()
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code < 400:
            return

        exc = requests.exceptions.HTTPError(f"{self.status_code} Error")
        exc.response = self
        raise exc


class BackfillRektCommandTests(SimpleTestCase):
    @patch("reports.management.commands.backfill_rekt.time.sleep")
    @patch("reports.management.commands.backfill_rekt.create_report")
    @patch("reports.management.commands.backfill_rekt.is_duplicate", return_value=False)
    @patch("reports.management.commands.backfill_rekt.requests.get")
    def test_backfill_reads_next_bundle(
        self,
        mock_get,
        mock_is_duplicate,
        mock_create_report,
        mock_sleep,
    ):
        mock_get.side_effect = [DummyResponse(INDEX_HTML), DummyResponse(BUNDLE_JS)]
        mock_create_report.side_effect = lambda **kwargs: SimpleNamespace(
            pk=mock_create_report.call_count,
            title=kwargs["title"],
        )

        out = StringIO()
        call_command("backfill_rekt", delay=0, stdout=out)

        urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertEqual(urls, [BASE_URL, f"{BASE_URL}/_next/static/chunks/pages/_app-test.js"])
        self.assertEqual(mock_create_report.call_count, 2)
        self.assertEqual(mock_is_duplicate.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

        first_article = mock_create_report.call_args_list[0].kwargs
        self.assertEqual(first_article["source_url"], f"{BASE_URL}/alpha-hack")
        self.assertEqual(first_article["description"], "Alpha description.")
        self.assertEqual(first_article["raw_data"]["tags"], ["DeFi", "Rekt"])
        self.assertEqual(first_article["raw_data"]["source"], "next_bundle")
        self.assertIn("Loaded article metadata from Next.js bundle.", out.getvalue())

    @patch("reports.management.commands.backfill_rekt.create_report")
    @patch("reports.management.commands.backfill_rekt.is_duplicate", return_value=False)
    @patch("reports.management.commands.backfill_rekt.requests.get")
    def test_backfill_honors_max_articles_zero(
        self,
        mock_get,
        mock_is_duplicate,
        mock_create_report,
    ):
        mock_get.side_effect = [DummyResponse(INDEX_HTML), DummyResponse(BUNDLE_JS)]

        call_command("backfill_rekt", max_articles=0, delay=0, stdout=StringIO())

        self.assertEqual(mock_create_report.call_count, 0)
        self.assertEqual(mock_is_duplicate.call_count, 0)

    @patch("reports.management.commands.backfill_rekt.time.sleep")
    @patch("reports.management.commands.backfill_rekt.create_report")
    @patch("reports.management.commands.backfill_rekt.is_duplicate", return_value=False)
    @patch("reports.management.commands.backfill_rekt.requests.get")
    def test_backfill_falls_back_to_homepage_cards(
        self,
        mock_get,
        mock_is_duplicate,
        mock_create_report,
        mock_sleep,
    ):
        mock_get.return_value = DummyResponse(ARTICLE_HTML)
        mock_create_report.return_value = SimpleNamespace(pk=1, title="Alpha Hack")

        out = StringIO()
        call_command("backfill_rekt", delay=0, stdout=out)

        self.assertEqual(mock_create_report.call_count, 1)
        self.assertEqual(mock_is_duplicate.call_count, 1)
        article = mock_create_report.call_args.kwargs
        self.assertEqual(article["source_url"], f"{BASE_URL}/alpha")
        self.assertEqual(article["raw_data"]["source"], "homepage_cards")
        self.assertIn("Bundle metadata unavailable; falling back to homepage cards.", out.getvalue())

    @patch("reports.management.commands.backfill_rekt.requests.get")
    def test_backfill_raises_on_index_fetch_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("network timed out")

        with self.assertRaisesMessage(CommandError, "Failed to fetch rekt.news index"):
            call_command("backfill_rekt", delay=0, stdout=StringIO(), stderr=StringIO())
