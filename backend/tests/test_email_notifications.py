import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_CHAT_MODEL", "test-model")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.integrations.email_notifications import send_notification, send_visitor_reply


class EmailNotificationTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", poolclass=StaticPool,
                               connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()

    def tearDown(self):
        self.db.close()

    @patch("app.integrations.email_notifications.smtplib.SMTP")
    @patch("app.integrations.email_notifications.settings")
    def test_real_smtp_delivery_path(self, settings, smtp):
        settings.smtp_host = "smtp.example.com"
        settings.smtp_port = 587
        settings.smtp_from_email = "agent@example.com"
        settings.sales_notification_emails = ["sales@example.com"]
        settings.smtp_use_ssl = False
        settings.smtp_use_tls = True
        settings.smtp_username = "agent@example.com"
        settings.smtp_password = "secret"
        settings.app_base_url = "http://localhost:8000"
        connection = MagicMock()
        smtp.return_value.__enter__.return_value = connection
        record = send_notification(self.db, "session-1", "lead.created",
                                   {"email": "lead@example.com", "score": 80})
        self.assertEqual(record.status, "delivered")
        connection.starttls.assert_called_once()
        connection.login.assert_called_once()
        connection.send_message.assert_called_once()

    @patch("app.integrations.email_notifications.smtplib.SMTP")
    @patch("app.integrations.email_notifications.settings")
    def test_visitor_reply_is_sent_to_lead_email(self, settings, smtp):
        settings.smtp_host = "smtp.example.com"
        settings.smtp_port = 587
        settings.smtp_from_email = "agent@example.com"
        settings.sales_notification_emails = ["sales@example.com"]
        settings.smtp_use_ssl = False
        settings.smtp_use_tls = True
        settings.smtp_username = "agent@example.com"
        settings.smtp_password = "secret"
        connection = MagicMock()
        smtp.return_value.__enter__.return_value = connection

        record = send_visitor_reply(self.db, "session-2", "visitor@example.com",
                                    "Visitor", "We will contact you shortly.")

        self.assertEqual(record.status, "delivered")
        sent = connection.send_message.call_args.args[0]
        self.assertEqual(sent["To"], "visitor@example.com")
        self.assertIn("We will contact you shortly.", sent.get_content())


if __name__ == "__main__":
    unittest.main()
