import os
import unittest
from unittest.mock import MagicMock, patch
from cryptography.fernet import Fernet

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_CHAT_MODEL", "test-model")

from app.agent.actions import build_browser_actions
from app.agent.lead_scoring import calculate_lead_score
from app.agent.models import LeadProfile, LeadTemperature, SalesStage
from app.agent.sales_stage import determine_sales_stage
from app.agent.sales_agent import (SalesAgentService, detect_response_language,
                                   extract_explicit_visitor_name)
from app.rag.refresh import content_fingerprint
from app.core.security import decrypt_secret, encrypt_secret


class LeadLogicTests(unittest.TestCase):
    def test_latest_message_name_extraction_is_explicit(self):
        self.assertEqual(
            extract_explicit_visitor_name(
                "My name is Demo Lead. My company is BrightSmile Demo Clinic."
            ),
            "Demo Lead",
        )
        self.assertEqual(
            extract_explicit_visitor_name("Call me Ana María, I need SEO."),
            "Ana María",
        )
        self.assertIsNone(extract_explicit_visitor_name("I need SEO for Mohsin Ltd."))

    def test_stored_name_is_not_used_to_address_an_unintroduced_visitor(self):
        service = object.__new__(SalesAgentService)
        service.model = "test-model"
        service.client = MagicMock()
        service.client.responses.create.return_value.output_text = "Certainly, Sir."
        service.generate_response(
            "What do you recommend?",
            [{"role": "assistant", "content": "Welcome back, Mohsin."}],
            LeadProfile(full_name="Mohsin"),
            "discovery",
            retrieval_results=[],
            response_language="English",
        )
        request = service.client.responses.create.call_args.kwargs
        self.assertNotIn("Mohsin", request["input"])
        self.assertIn('begin the\n    response with "Sir,"', request["instructions"])
        self.assertIn("MANDATORY VISITOR ADDRESS: Sir", request["input"])

    def test_language_fallback_does_not_copy_previous_language(self):
        self.assertEqual(detect_response_language("Ecom website designer"), "English")
        self.assertEqual(
            detect_response_language("saya ingin berbicara dengan perusahaan Anda"),
            "Indonesian",
        )
        self.assertEqual(
            detect_response_language("mujhe website design chahiye"),
            "Urdu written in Roman script",
        )
        self.assertEqual(detect_response_language("مجھے ویب سائٹ چاہیے"), "Urdu or Arabic")

    @patch("app.core.security.settings")
    def test_secret_encryption_round_trip(self, settings):
        settings.token_encryption_key = Fernet.generate_key().decode()
        encrypted = encrypt_secret("private-token")
        self.assertTrue(encrypted.startswith("enc:"))
        self.assertNotIn("private-token", encrypted)
        self.assertEqual(decrypt_secret(encrypted), "private-token")
    def test_knowledge_fingerprint_ignores_page_order(self):
        first = [{"url": "a", "content_hash": "1"}, {"url": "b", "content_hash": "2"}]
        self.assertEqual(content_fingerprint(first), content_fingerprint(list(reversed(first))))
    def test_complete_lead_is_hot_and_capped(self):
        lead = calculate_lead_score(LeadProfile(
            full_name="A", email="a@example.com", phone="123", company_name="ACME",
            website_url="https://example.com", industry="Retail", required_services=["SEO"],
            business_problem="Low traffic", budget="$5k", timeline="30 days",
            wants_meeting=True, wants_proposal=True,
        ))
        self.assertEqual(lead.score, 100)
        self.assertEqual(lead.temperature, LeadTemperature.HOT)

    def test_stage_precedence(self):
        self.assertEqual(determine_sales_stage(LeadProfile(requested_human=True,
                         wants_meeting=True)), SalesStage.HANDOVER)
        self.assertEqual(determine_sales_stage(LeadProfile(email="a@example.com",
                         required_services=["SEO"])), SalesStage.QUALIFICATION)

    @patch("app.agent.actions.settings")
    def test_actions_are_intent_driven(self, settings):
        settings.calendly_url = "https://calendly.com/example"
        settings.company_phone = "+15551234"
        actions = build_browser_actions("Show the service and book a call", [
            {"title": "Local SEO", "url": "https://systematicitsolutions.com/seo/local-seo"}
        ], LeadProfile())
        self.assertEqual({a["type"] for a in actions}, {"book_meeting", "call", "navigate"})


if __name__ == "__main__":
    unittest.main()
