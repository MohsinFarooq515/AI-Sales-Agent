import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("OPENAI_CHAT_MODEL", "test-model")

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import GoogleCalendarCredentialDB


class GoogleCalendarTokenTests(unittest.TestCase):
    @patch("app.integrations.google_calendar.httpx.post")
    @patch("app.core.security.settings")
    @patch("app.integrations.google_calendar.settings")
    def test_refreshed_token_is_decrypted_before_return(self, calendar_settings,
                                                        security_settings, post):
        key = Fernet.generate_key().decode()
        security_settings.token_encryption_key = key
        calendar_settings.google_client_id = "client"
        calendar_settings.google_client_secret = "secret"
        from app.core.security import encrypt_secret
        engine = create_engine("sqlite://", poolclass=StaticPool,
                               connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        db.add(GoogleCalendarCredentialDB(id=1, access_token=encrypt_secret("old-access"),
            refresh_token=encrypt_secret("refresh"), expires_at=datetime.utcnow()-timedelta(minutes=1)))
        db.commit()
        response = MagicMock(is_error=False)
        response.json.return_value = {"access_token": "new-access", "expires_in": 3600}
        post.return_value = response
        from app.integrations.google_calendar import access_token
        self.assertEqual(access_token(db), "new-access")
        self.assertNotEqual(db.get(GoogleCalendarCredentialDB, 1).access_token, "new-access")
        db.close()


if __name__ == "__main__":
    unittest.main()
