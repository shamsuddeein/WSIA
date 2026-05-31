from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from reports.scraper import BASE_URL


ARTICLE_HTML = """
<article class="post">
  <h2 class="post-title"><a href="/alpha">Alpha Hack</a></h2>
  <div class="post-excerpt"><p>Alpha description.</p></div>
  <div class="post-meta">
    <time datetime="2026-05-30T00:00:00Z"></time>
    <a href="/?tag=DeFi">DeFi</a>
  </div>
</article>
"""


class DummyResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
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
    def test_backfill_paginates_until_empty_page(
        self,
        mock_get,
        mock_is_duplicate,
        mock_create_report,
        mock_sleep,
    ):
        mock_get.side_effect = [
            DummyResponse(ARTICLE_HTML),
            DummyResponse(ARTICLE_HTML),
            DummyResponse("<html><body></body></html>"),
        ]
        mock_create_report.side_effect = lambda **kwargs: SimpleNamespace(
            pk=mock_create_report.call_count,
            title=kwargs["title"],
        )

        out = StringIO()
        call_command("backfill_rekt", delay=0, stdout=out)

        urls = [call.args[0] for call in mock_get.call_args_list]
        self.assertEqual(
            urls,
            [
                BASE_URL,
                f"{BASE_URL}/page/2/",
                f"{BASE_URL}/page/3/",
            ],
        )
        self.assertEqual(mock_create_report.call_count, 2)
        self.assertEqual(mock_is_duplicate.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertIn("No article cards found on page 3; stopping pagination.", out.getvalue())

    @patch("reports.management.commands.backfill_rekt.requests.get")
    def test_backfill_raises_on_fetch_failure(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("network timed out")

        with self.assertRaisesMessage(CommandError, "Failed to fetch page 1"):
            call_command("backfill_rekt", delay=0, stdout=StringIO(), stderr=StringIO())

    @patch("reports.management.commands.backfill_rekt.time.sleep")
    @patch("reports.management.commands.backfill_rekt.create_report")
    @patch("reports.management.commands.backfill_rekt.is_duplicate", return_value=False)
    @patch("reports.management.commands.backfill_rekt.requests.get")
    def test_backfill_stops_on_404_after_first_page(
        self,
        mock_get,
        mock_is_duplicate,
        mock_create_report,
        mock_sleep,
    ):
        mock_get.side_effect = [
            DummyResponse(ARTICLE_HTML),
            DummyResponse(status_code=404),
        ]
        mock_create_report.return_value = SimpleNamespace(pk=1, title="Alpha Hack")

        out = StringIO()
        call_command("backfill_rekt", delay=0, stdout=out)

        self.assertEqual(mock_create_report.call_count, 1)
        self.assertEqual(mock_is_duplicate.call_count, 1)
        self.assertIn("Page 2 returned 404; stopping pagination.", out.getvalue())
