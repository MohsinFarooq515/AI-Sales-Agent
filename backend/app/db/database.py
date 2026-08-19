import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


load_dotenv()


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "app"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_FILE = DATA_DIR / "ai_sales_agent.db"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + DEFAULT_DB_FILE.as_posix(),
)

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False
    }


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def apply_compatible_schema_updates():
    """Add nullable lead fields introduced after the initial demo schema."""
    columns = {column["name"] for column in inspect(engine).get_columns("leads")}
    with engine.begin() as connection:
        if "persona" not in columns:
            connection.execute(text("ALTER TABLE leads ADD COLUMN persona VARCHAR(50)"))
        if "meeting_booked" not in columns:
            connection.execute(text(
                "ALTER TABLE leads ADD COLUMN meeting_booked BOOLEAN NOT NULL DEFAULT 0"
            ))
    conversation_columns = {
        column["name"] for column in inspect(engine).get_columns("conversations")
    }
    if "last_conversion_prompt_turn" not in conversation_columns:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE conversations "
                "ADD COLUMN last_conversion_prompt_turn INTEGER"
            ))
    if "attention_offer_shown" not in conversation_columns:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE conversations "
                "ADD COLUMN attention_offer_shown BOOLEAN NOT NULL DEFAULT 0"
            ))


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
