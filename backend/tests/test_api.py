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
        self.assertIn("sessionStorage.getItem('sits_agent_session')", widget)
        self.assertIn("localStorage.removeItem('sits_agent_session')", widget)
        self.assertIn("function linkifyServices", widget)
        self.assertIn("https://systematicitsolutions.com/seo/local-seo", widget)
        self.assertIn("link.target='_blank'", widget)

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

    def test_event_and_dashboard(self):
        self.assertEqual(self.client.post("/api/events", json={
            "event_type": "visitor.page_view", "data": {"url": "https://example.com"}
        }).status_code, 202)
        response = self.client.get("/api/admin/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("totals", response.json())
        self.assertLessEqual(len(response.json()["frequently_asked_questions"]), 5)

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
        self.assertEqual(body["actions"][0]["type"], "navigate")
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
