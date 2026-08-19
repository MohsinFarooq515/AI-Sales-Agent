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
                                   extract_explicit_visitor_name,
                                   extract_initial_name_reply,
                                   is_language_neutral_message,
                                   resolve_response_language,
                                   normalize_visitor_address)
from app.rag.refresh import content_fingerprint
from app.core.security import decrypt_secret, encrypt_secret


class LeadLogicTests(unittest.TestCase):
    def test_visitor_address_is_deterministic(self):
        self.assertEqual(
            normalize_visitor_address("Sir, here is the plan.", "Demo Lead"),
            "Demo Lead, here is the plan.",
        )
        self.assertEqual(
            normalize_visitor_address("Hello Demo Lead! Welcome.", "Demo Lead"),
            "Demo Lead, Welcome.",
        )
        self.assertEqual(
            normalize_visitor_address("Here is the plan.", "Sir"),
            "Sir, Here is the plan.",
        )

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
        self.assertEqual(extract_initial_name_reply("Ahmed Khan"), "Ahmed Khan")
        self.assertEqual(extract_initial_name_reply("I'm Ahmed"), "Ahmed")
        self.assertIsNone(extract_initial_name_reply("I need a website"))

    def test_name_collected_in_current_session_is_reused(self):
        service = object.__new__(SalesAgentService)
        service.model = "test-model"
        service.client = MagicMock()
        service.client.responses.create.return_value.output_text = "Here is the plan."
        result = service.generate_response(
            "What do you recommend?",
            [{"role": "assistant", "content": "Welcome back, Mohsin."}],
            LeadProfile(full_name="Mohsin"),
            "discovery",
            retrieval_results=[],
            response_language="English",
        )
        request = service.client.responses.create.call_args.kwargs
        history_section = request["input"].split("RECENT CONVERSATION:", 1)[1].split(
            "RELEVANT WEBSITE KNOWLEDGE:", 1
        )[0]
        self.assertNotIn("Mohsin", history_section)
        self.assertIn("visitors who may know nothing about", request["instructions"])
        self.assertIn("CONTACT STATUS:\nNO_CONTACT", request["input"])
        self.assertEqual(result["answer"], "Here is the plan.")

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

    def test_language_neutral_contact_details_keep_previous_language(self):
        history = [
            {"role": "user", "content": "I need help marketing my school."},
            {"role": "assistant", "content": "How can we contact you?"},
            {"role": "user", "content": "mohsin@yopmail.com"},
        ]
        self.assertTrue(is_language_neutral_message("mohsin@yopmail.com"))
        self.assertTrue(is_language_neutral_message("+92 300 1234567"))
        self.assertEqual(
            resolve_response_language("mohsin@yopmail.com", history), "English"
        )
        portuguese_history = [
            {"role": "user", "content": "Como posso melhorar minha empresa?"},
            {"role": "user", "content": "cliente@example.com"},
        ]
        self.assertEqual(
            resolve_response_language("cliente@example.com", portuguese_history),
            "Portuguese",
        )

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

    @patch("app.agent.actions.settings")
    def test_conversion_actions_follow_contact_status(self, settings):
        settings.app_base_url = "https://example.com"
        settings.company_phone = ""
        anonymous = build_browser_actions(
            "My website gets no customers", [],
            LeadProfile(business_problem="Website gets no customers"),
        )
        self.assertEqual(
            [action["type"] for action in anonymous],
            ["book_meeting", "share_email"],
        )
        identified = build_browser_actions(
            "Here is my email", [],
            LeadProfile(email="lead@example.com", business_problem="Low sales"),
        )
        self.assertEqual([action["type"] for action in identified], ["book_meeting"])
        booked = build_browser_actions(
            "Tell me more", [],
            LeadProfile(email="lead@example.com", wants_meeting=True, meeting_booked=True),
        )
        self.assertEqual(booked, [])
        requested = build_browser_actions(
            "I want a meeting", [], LeadProfile(wants_meeting=True)
        )
        self.assertEqual(requested[0]["type"], "book_meeting")


if __name__ == "__main__":
    unittest.main()
