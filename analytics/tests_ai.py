from unittest.mock import patch
from django.test import TestCase
from reports.models import HackReport
from analytics.tasks import enrich_report_with_ai
from analytics.ai_service import generate_summary, generate_embedding

class AILayerTests(TestCase):
    def setUp(self):
        self.report = HackReport.objects.create(
            title="Test Hack",
            description="A very bad hack happened.",
            source_url="https://example.com/hack",
            hash="12345",
            is_processed=True
        )

    @patch('analytics.ai_service.get_client')
    def test_missing_api_key_safe(self, mock_get_client):
        """Test that AI tasks fail gracefully when API key is missing."""
        mock_get_client.return_value = None
        
        result = enrich_report_with_ai(self.report.id)
        
        self.assertEqual(result["status"], "no_change")
        self.report.refresh_from_db()
        self.assertIsNone(self.report.ai_summary)
        self.assertIsNone(self.report.embedding)

    @patch('analytics.ai_service.openai.OpenAI')
    def test_successful_enrichment(self, mock_openai_class):
        """Test that summaries and embeddings are saved correctly."""
        # Setup mock responses
        mock_client = mock_openai_class.return_value
        
        # Mock chat completion for summary
        mock_chat_response = mock_client.chat.completions.create.return_value
        mock_chat_response.choices = [type('obj', (object,), {'message': type('obj', (object,), {'content': 'Mocked AI summary.'})()})]
        
        # Mock embedding
        mock_embed_response = mock_client.embeddings.create.return_value
        mock_embed_response.data = [type('obj', (object,), {'embedding': [0.1] * 1536})()]
        
        # We also need get_client to return the mocked client.
        with patch('analytics.ai_service.get_client', return_value=mock_client):
            result = enrich_report_with_ai(self.report.id)
            
        self.assertEqual(result["status"], "success")
        self.report.refresh_from_db()
        self.assertEqual(self.report.ai_summary, "Mocked AI summary.")
        self.assertEqual(len(self.report.embedding), 1536)
