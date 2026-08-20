import os
import unittest
from unittest.mock import MagicMock, patch
from cryptography.fernet import Fernet

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_CHAT_MODEL", "test-model")

from app.agent.actions import (
    build_browser_actions,
    determine_conversion_prompt,
    PROMPT_BOTH,
    PROMPT_EMAIL,
    PROMPT_MEETING,
    PROMPT_MEETING_AFTER_EMAIL,
    PROMPT_PHONE,
    PROMPT_COMPANY_PHONE,
    should_offer_conversion,
    should_show_attention_offer,
)
from app.agent.lead_scoring import calculate_lead_score
from app.agent.models import LeadProfile, LeadTemperature, SalesStage
from app.agent.sales_stage import determine_sales_stage
from app.agent.sales_agent import (SalesAgentService, detect_response_language,
                                   extract_explicit_visitor_name,
                                   extract_initial_name_reply,
                                   is_language_neutral_message,
                                   resolve_response_language,
                                   normalize_visitor_address)
from app.agent.contact_request import (contact_request_answer,
                                       requested_contact_target)
from app.rag.refresh import content_fingerprint
from app.core.security import decrypt_secret, encrypt_secret


class LeadLogicTests(unittest.TestCase):
    def test_explicit_member_contact_request_uses_saved_email_state(self):
        self.assertEqual(
            requested_contact_target("I wanna contact with the CEO"), "CEO"
        )
        self.assertEqual(
            requested_contact_target("Can I speak to your sale team?"), "sales team"
        )
        self.assertEqual(
            requested_contact_target("Please connect me with the founder"), "founder"
        )
        self.assertIsNone(requested_contact_target("Tell me about your founder"))
        self.assertEqual(
            contact_request_answer("CEO", True),
            "Our CEO will contact you at the email address you shared.",
        )
        self.assertEqual(
            contact_request_answer("founder", False),
            "Please share your email address so our founder can contact you.",
        )

    @patch("app.agent.actions.settings")
    def test_contact_request_offers_email_only_when_missing(self, settings):
        settings.company_phone = ""
        missing = build_browser_actions(
            "I want to talk to the CEO", [], LeadProfile(), show_conversion=False
        )
        saved = build_browser_actions(
            "I want to talk to the CEO", [], LeadProfile(email="lead@example.com"),
            show_conversion=False,
        )
        self.assertEqual([action["type"] for action in missing], ["share_email"])
        self.assertEqual(missing[0]["label"], "Share my name & email")
        self.assertTrue(missing[0]["fields"]["name_required"])
        self.assertEqual(saved, [])

    def test_contact_request_response_bypasses_normal_conversion_strategy(self):
        service = object.__new__(SalesAgentService)
        service.model = "test-model"
        service.client = MagicMock()
        with_email = service.generate_response(
            "I want to contact the founder",
            [{"role": "user", "content": "I want to contact the founder"}],
            LeadProfile(email="lead@example.com"),
            "handover",
            retrieval_results=[],
            response_language="English",
            allow_conversion_prompt=False,
        )
        without_email = service.generate_response(
            "Let me speak with your CEO",
            [{"role": "user", "content": "Let me speak with your CEO"}],
            LeadProfile(),
            "handover",
            retrieval_results=[],
            response_language="English",
            allow_conversion_prompt=False,
        )
        self.assertEqual(
            with_email["answer"],
            "Our founder will contact you at the email address you shared.",
        )
        self.assertEqual(
            without_email["answer"],
            "Please share your email address so our CEO can contact you.",
        )
        service.client.responses.create.assert_not_called()

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
        self.assertIsNone(extract_initial_name_reply("clothing brand"))
        self.assertIsNone(extract_initial_name_reply("tell me about yourself"))
        self.assertEqual(extract_initial_name_reply("i am hamza khan"), "hamza khan")

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
        self.assertIn("strict language lock", request["instructions"])
        self.assertIn("budget range in mind", request["instructions"])
        self.assertIn("CONTACT STATUS:\nNO_CONTACT", request["input"])
        self.assertEqual(result["answer"], "Here is the plan.")

    def test_language_fallback_does_not_copy_previous_language(self):
        self.assertEqual(detect_response_language("Ecom website designer"), "English")
        self.assertEqual(detect_response_language("clothing brand"), "English")
        self.assertEqual(
            detect_response_language("tell me about yourself"), "English"
        )
        self.assertEqual(
            detect_response_language("NO website at that time, want website"),
            "English",
        )
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
        self.assertEqual(anonymous[1]["label"], "Share my name & email")
        named = build_browser_actions(
            "My website gets no customers", [],
            LeadProfile(full_name="James", business_problem="Website gets no customers"),
        )
        self.assertEqual(named[1]["label"], "Share my email")
        self.assertFalse(named[1]["fields"]["name_required"])
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
        name_only = build_browser_actions(
            "James Here", [], LeadProfile(full_name="James Here", email="old@example.com")
        )
        self.assertEqual(name_only, [])

    def test_conversion_prompt_follows_non_repetitive_sequence(self):
        lead = LeadProfile(business_problem="Needs more customers")
        self.assertEqual(determine_conversion_prompt(
            "Help", lead, 2, None, None, None), PROMPT_EMAIL)
        self.assertEqual(determine_conversion_prompt(
            "More", lead, 3, 2, PROMPT_EMAIL, None), PROMPT_MEETING_AFTER_EMAIL)
        self.assertIsNone(determine_conversion_prompt(
            "Still unsure", lead, 4, 3, PROMPT_MEETING_AFTER_EMAIL, None))

    def test_email_capture_asks_details_then_meeting(self):
        lead = LeadProfile(email="lead@example.com", business_problem="Low sales")
        self.assertIsNone(determine_conversion_prompt(
            "lead@example.com", lead, 3, None, None, 3))
        self.assertEqual(determine_conversion_prompt(
            "Traffic fell last month", lead, 4, None, None, 3), PROMPT_MEETING)

    def test_late_phone_fallback_runs_once_and_stops_when_phone_is_shared(self):
        anonymous = LeadProfile(business_problem="Needs more customers")
        self.assertEqual(determine_conversion_prompt(
            "Tell me more", anonymous, 8, 7, PROMPT_EMAIL, None), PROMPT_PHONE)
        self.assertEqual(determine_conversion_prompt(
            "What else?", anonymous, 9, 8, PROMPT_PHONE, None),
            PROMPT_COMPANY_PHONE,
        )
        self.assertIsNone(determine_conversion_prompt(
            "Continue", anonymous, 10, 9, PROMPT_COMPANY_PHONE, None))
        identified = LeadProfile(phone="+92 300 1234567",
                                 business_problem="Needs more customers")
        self.assertIsNone(determine_conversion_prompt(
            "+92 300 1234567", identified, 9, 8, PROMPT_PHONE, None))
        emailed = LeadProfile(email="lead@example.com",
                              business_problem="Needs more customers")
        self.assertNotIn(determine_conversion_prompt(
            "Continue", emailed, 8, 7, PROMPT_EMAIL, 3),
            (PROMPT_PHONE, PROMPT_COMPANY_PHONE))

    def test_late_phone_fallback_returns_required_visitor_messages(self):
        service = object.__new__(SalesAgentService)
        service.model = "test-model"
        service.client = MagicMock()
        history = [{"role": "user", "content": f"Question {turn}"}
                   for turn in range(1, 9)]
        request_number = service.generate_response(
            "Question 8", history, LeadProfile(), "discovery",
            retrieval_results=[], response_language="English",
            conversion_prompt_kind=PROMPT_PHONE,
        )
        offer_number = service.generate_response(
            "Question 9", history + [{"role": "user", "content": "Question 9"}],
            LeadProfile(), "discovery", retrieval_results=[],
            response_language="English",
            conversion_prompt_kind=PROMPT_COMPANY_PHONE,
        )
        self.assertIn("share your contact number", request_number["answer"])
        self.assertIn("call our team directly", offer_number["answer"])
        service.client.responses.create.assert_not_called()

    @patch("app.agent.actions.settings")
    def test_company_phone_fallback_adds_call_action(self, settings):
        settings.company_phone = "+1 626-381-8293"
        actions = build_browser_actions(
            "Tell me more", [], LeadProfile(), show_conversion=False,
            prompt_kind=PROMPT_COMPANY_PHONE,
        )
        self.assertEqual(actions, [{
            "type": "call", "label": "Call us: +1 626-381-8293",
            "url": "tel:+1 626-381-8293"
        }])

    def test_legacy_attention_offer_is_disabled(self):
        lead = LeadProfile(business_problem="Low online sales")
        self.assertFalse(should_show_attention_offer(
            "How would you improve it?", lead, 3, 2, False
        ))
        self.assertFalse(should_show_attention_offer(
            "Tell me more", lead, 4, 2, True
        ))
        self.assertFalse(should_show_attention_offer(
            "Tell me more",
            LeadProfile(business_problem="Low sales", email="lead@example.com"),
            3,
            2,
            False,
        ))

    def test_first_post_name_response_only_asks_for_purpose(self):
        service = object.__new__(SalesAgentService)
        service.model = "test-model"
        service.client = MagicMock()
        result = service.generate_response(
            "James Here",
            [{"role": "user", "content": "James Here"}],
            LeadProfile(full_name="James Here"),
            "discovery",
            retrieval_results=[],
            response_language="English",
        )
        self.assertEqual(
            result["answer"],
            "Welcome James Here, How can we assist you today?",
        )
        service.client.responses.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
