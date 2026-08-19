import os
import json
import unittest
import uuid
from unittest.mock import patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_CHAT_MODEL", "test-model")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.api.analytics import require_admin
from app.agent.models import LeadExtraction
from app.db.database import Base, get_db


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                   poolclass=StaticPool)
        Base.metadata.create_all(cls.engine)
        cls.session_factory = sessionmaker(bind=cls.engine)

    def setUp(self):
        app.dependency_overrides[require_admin] = lambda: None
        def test_db():
            db = self.session_factory()
            try:
                yield db
            finally:
                db.close()
        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_health_and_static_pages(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/demo").status_code, 200)
        self.assertEqual(self.client.get("/admin").status_code, 200)
        widget = self.client.get("/widget/widget.js").text
        self.assertNotIn("sessionStorage.getItem('sits_agent_session')", widget)
        self.assertIn("localStorage.removeItem('sits_agent_session')", widget)
        self.assertIn("function linkifyServices", widget)
        self.assertIn("https://systematicitsolutions.com/seo/local-seo", widget)
        self.assertIn("link.target='_blank'", widget)
        self.assertIn("function requestChatStream", widget)
        self.assertIn("[502,503,504]", widget)
        self.assertIn("May I have your name, please?", widget)
        self.assertIn("a.type==='share_email'", widget)
        self.assertIn("function showEmailCapture", widget)
        self.assertIn("Submit email", widget)
        self.assertIn("if(!session||sending)return", widget)

    def test_empty_chat_is_rejected(self):
        response = self.client.post("/api/chat", json={"message": "   "})
        self.assertEqual(response.status_code, 400)

    @patch("app.api.chat.sales_agent.retrieve_knowledge")
    @patch("app.api.chat.sales_agent.identify_response_language", return_value="English")
    @patch("app.api.chat.sales_agent.generate_response")
    @patch("app.api.chat.lead_extractor.extract")
    def test_widget_uuid_session_is_normalized_for_sqlite(self, extract, generate,
                                                           identify, retrieve):
        extract.return_value = LeadExtraction()
        retrieve.return_value = []
        generate.return_value = {"answer": "Hello", "sources": []}
        session_id = str(uuid.uuid4())
        response = self.client.post("/api/chat", json={
            "message": "Hello", "session_id": session_id
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["session_id"], session_id)

    @patch("app.api.chat.sales_agent.retrieve_knowledge", return_value=[])
    @patch("app.api.chat.sales_agent.identify_response_language", return_value="English")
    @patch("app.api.chat.sales_agent.generate_response",
           return_value={"answer": "Reply", "sources": []})
    @patch("app.api.chat.lead_extractor.extract", return_value=LeadExtraction())
    def test_explicit_name_persists_within_session_without_model_extraction(
            self, extract, generate, identify, retrieve):
        session_id = str(uuid.uuid4())
        first = self.client.post("/api/chat", json={
            "message": "My name is Demo Lead. I need Local SEO.",
            "session_id": session_id,
        })
        second = self.client.post("/api/chat", json={
            "message": "What do you recommend next?",
            "session_id": session_id,
        })

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["lead"]["full_name"], "Demo Lead")
        self.assertEqual(second.json()["lead"]["full_name"], "Demo Lead")
        self.assertEqual(generate.call_args_list[1].args[2].full_name, "Demo Lead")

    @patch("app.api.chat.sales_agent.retrieve_knowledge", return_value=[])
    @patch("app.api.chat.sales_agent.identify_response_language", return_value="English")
    @patch("app.api.chat.sales_agent.generate_response",
           return_value={"answer": "Helpful reply", "sources": []})
    @patch("app.api.chat.lead_extractor.extract")
    def test_conversion_actions_are_suppressed_during_cooldown(
            self, extract, generate, identify, retrieve):
        extract.side_effect = [
            LeadExtraction(business_problem="Website gets few customers"),
            LeadExtraction(email="james@example.com"),
            LeadExtraction(persona="entrepreneur"),
            LeadExtraction(industry="Hospitality"),
            LeadExtraction(timeline="This month"),
        ]
        session_id = str(uuid.uuid4())
        messages = [
            "My website gets very few customers",
            "james@example.com",
            "It is for my own business",
            "I work in hospitality",
            "I want to begin this month",
        ]
        responses = [self.client.post("/api/chat", json={
            "message": message, "session_id": session_id,
        }).json() for message in messages]

        self.assertEqual(
            [action["type"] for action in responses[0]["actions"]],
            ["book_meeting", "share_email"],
        )
        self.assertEqual(responses[1]["actions"], [])
        self.assertEqual(responses[2]["actions"], [])
        self.assertEqual(responses[3]["actions"], [])
        self.assertEqual(
            [action["type"] for action in responses[4]["actions"]],
            ["book_meeting"],
        )
        # The model receives the same cadence directive as the UI actions.
        self.assertFalse(generate.call_args_list[1].args[6])
        self.assertTrue(generate.call_args_list[4].args[6])

    @patch("app.api.chat.sales_agent.retrieve_knowledge", return_value=[])
    @patch("app.api.chat.sales_agent.identify_response_language", return_value="English")
    @patch("app.api.chat.sales_agent.generate_response",
           return_value={"answer": "Helpful reply", "sources": []})
    @patch("app.api.chat.lead_extractor.extract")
    def test_attention_offer_is_shown_once_after_contact_options_are_ignored(
            self, extract, generate, identify, retrieve):
        extract.side_effect = [
            LeadExtraction(business_problem="Website gets few customers"),
            LeadExtraction(),
            LeadExtraction(),
        ]
        session_id = str(uuid.uuid4())
        first = self.client.post("/api/chat", json={
            "message": "My website gets very few customers",
            "session_id": session_id,
        }).json()
        second = self.client.post("/api/chat", json={
            "message": "How would you improve it?",
            "session_id": session_id,
        }).json()
        third = self.client.post("/api/chat", json={
            "message": "Which part should be fixed first?",
            "session_id": session_id,
        }).json()

        self.assertEqual(
            [action["type"] for action in first["actions"]],
            ["book_meeting", "share_email"],
        )
        self.assertEqual(
            [action["type"] for action in second["actions"]],
            ["book_meeting"],
        )
        self.assertEqual(third["actions"], [])
        self.assertTrue(generate.call_args_list[1].args[7])
        self.assertFalse(generate.call_args_list[2].args[7])

    def test_event_and_dashboard(self):
        self.assertEqual(self.client.post("/api/events", json={
            "event_type": "visitor.page_view", "data": {"url": "https://example.com"}
        }).status_code, 202)
        response = self.client.get("/api/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("totals", response.json())
        self.assertLessEqual(len(response.json()["frequently_asked_questions"]), 5)

    @patch("app.api.google_calendar.sync_lead_background")
    @patch("app.api.google_calendar.create_event")
    def test_booking_captures_name_email_and_meeting_status(self, create_event, sync):
        create_event.return_value = {
            "id": "event-1",
            "htmlLink": "https://calendar.google.com/event-1",
            "hangoutLink": "https://meet.google.com/example",
        }
        session_id = str(uuid.uuid4())
        with self.session_factory() as db:
            from app.db.repository import get_or_create_conversation
            get_or_create_conversation(db, session_id)
        response = self.client.post("/api/google-calendar/book", json={
            "session_id": session_id,
            "start": "2030-01-02T10:00:00Z",
            "timezone": "UTC",
            "name": "Ahmed Khan",
            "email": "ahmed@example.com",
        })
        self.assertEqual(response.status_code, 200)
        with self.session_factory() as db:
            from app.db.repository import get_lead_profile
            lead = get_lead_profile(db, session_id)
        self.assertEqual(lead.full_name, "Ahmed Khan")
        self.assertEqual(lead.email, "ahmed@example.com")
        self.assertTrue(lead.wants_meeting)
        self.assertTrue(lead.meeting_booked)
        history = self.client.get(f"/api/conversations/{session_id}").json()
        self.assertEqual(
            history["messages"][-1]["content"],
            "Thank you for scheduling a meeting. Our team will get back to you. "
            "Do you have any further questions?",
        )

    def test_dashboard_is_public_but_crm_writes_remain_protected(self):
        app.dependency_overrides.pop(require_admin, None)
        try:
            self.assertEqual(self.client.get("/api/admin/dashboard").status_code, 200)
            self.assertEqual(self.client.get("/api/admin/leads").status_code, 200)
            response = self.client.put("/api/admin/leads/not-a-lead", json={
                "status": "new", "assigned_to": None,
                "follow_up_at": None, "notes": None,
            })
            self.assertIn(response.status_code, (401, 503))
        finally:
            app.dependency_overrides[require_admin] = lambda: None

    @patch("app.api.chat.sales_agent.retrieve_knowledge", return_value=[])
    @patch("app.api.chat.sales_agent.identify_response_language", return_value="English")
    @patch("app.api.chat.lead_extractor.extract", return_value=LeadExtraction())
    @patch("app.api.chat.sales_agent.generate_response")
    def test_streaming_chat_emits_delta_and_done(self, generate, extract, identify,
                                                 retrieve):
        def streamed(*args):
            args[-1]("Hello")
            args[-1](" there")
            return {"answer": "Hello there", "sources": []}
        generate.side_effect = streamed
        with self.client.stream("POST", "/api/chat/stream",
                                json={"message": "Hello"}) as response:
            events = [json.loads(line) for line in response.iter_lines() if line]
        self.assertEqual(response.status_code, 200)
        self.assertEqual([event["delta"] for event in events[:2]],
                         ["Hello", " there"])
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["data"]["answer"], "Hello there")

    @patch("app.api.chat.sync_lead_background")
    @patch("app.api.analytics.sync_lead_background")
    @patch("app.api.chat.sales_agent.retrieve_knowledge")
    @patch("app.api.chat.sales_agent.identify_response_language", return_value="English")
    @patch("app.api.chat.sales_agent.generate_response")
    @patch("app.api.chat.lead_extractor.extract")
    def test_complete_chat_workflow(self, extract, generate, identify, retrieve,
                                    analytics_sync, chat_sync):
        retrieve.return_value = []
        extract.return_value = LeadExtraction(email="lead@example.com",
                                              required_services=["Local SEO"],
                                              business_problem="Needs local leads")
        generate.return_value = {"answer": "Local SEO can improve local discovery.",
                                 "sources": [{"title": "Local SEO",
                                              "url": "https://systematicitsolutions.com/seo/local-seo",
                                              "score": 0.9}]}
        response = self.client.post("/api/chat", json={"message": "Show me Local SEO"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["lead"]["temperature"], "warm")
        self.assertEqual(body["sales_stage"], "qualification")
        self.assertIn("navigate", {action["type"] for action in body["actions"]})
        history = self.client.get(f'/api/conversations/{body["session_id"]}')
        self.assertEqual(len(history.json()["messages"]), 2)
        reply = self.client.post(f'/api/admin/conversations/{body["session_id"]}/reply',
                                 json={"message": "A sales specialist has joined."})
        updates = self.client.get(f'/api/conversations/{body["session_id"]}/updates',
                                  params={"after_id": body["message_id"]})
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(updates.json()[0]["content"], "A sales specialist has joined.")
        crm = self.client.put(f'/api/admin/leads/{body["session_id"]}', json={
            "status": "qualified", "assigned_to": "Demo Sales Rep",
            "follow_up_at": "2030-01-02T10:00:00", "notes": "Send proposal"
        })
        self.assertEqual(crm.status_code, 200)
        managed = self.client.get('/api/admin/leads').json()[0]
        self.assertEqual(managed["crm_status"], "qualified")
        self.assertEqual(managed["assigned_to"], "Demo Sales Rep")
        analytics_sync.assert_called()
        details = self.client.get(f'/api/inquiries/{body["session_id"]}')
        self.assertEqual(details.json()["email"], "lead@example.com")
        inquiry = self.client.post(f'/api/inquiries/{body["session_id"]}', json={
            "full_name": "Demo Lead", "company_name": "Example Co",
            "email": "lead@example.com", "required_services": ["Local SEO"],
            "business_problem": "Needs more local customers"
        })
        self.assertEqual(inquiry.status_code, 200)
        self.assertTrue(inquiry.json()["submitted"])
