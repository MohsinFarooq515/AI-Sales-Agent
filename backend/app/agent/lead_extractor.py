import json
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from app.agent.models import (
    LeadExtraction,
    LeadProfile,
)


BACKEND_DIR = Path(__file__).resolve().parents[2]

# Always use this backend's configured key instead of a stale key inherited
# from Bash/PowerShell.
load_dotenv(BACKEND_DIR / ".env", override=True)


LEAD_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name": {
            "type": ["string", "null"]
        },
        "company_name": {
            "type": ["string", "null"]
        },
        "email": {
            "type": ["string", "null"]
        },
        "phone": {
            "type": ["string", "null"]
        },
        "website_url": {
            "type": ["string", "null"]
        },
        "industry": {
            "type": ["string", "null"]
        },
        "required_services": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "business_problem": {
            "type": ["string", "null"]
        },
        "location": {
            "type": ["string", "null"]
        },
        "budget": {
            "type": ["string", "null"]
        },
        "timeline": {
            "type": ["string", "null"]
        },
        "wants_meeting": {
            "type": ["boolean", "null"]
        },
        "wants_callback": {
            "type": ["boolean", "null"]
        },
        "wants_proposal": {
            "type": ["boolean", "null"]
        },
        "requested_human": {
            "type": ["boolean", "null"]
        },
    },
    "required": [
        "full_name",
        "company_name",
        "email",
        "phone",
        "website_url",
        "industry",
        "required_services",
        "business_problem",
        "location",
        "budget",
        "timeline",
        "wants_meeting",
        "wants_callback",
        "wants_proposal",
        "requested_human",
    ],
    "additionalProperties": False,
}


class LeadExtractor:
    def __init__(
        self,
        model: Optional[str] = None,
    ):
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured."
            )

        self.model = (
            model
            or os.getenv("OPENAI_CHAT_MODEL")
        )

        if not self.model:
            raise RuntimeError(
                "OPENAI_CHAT_MODEL is not configured."
            )

        self.client = OpenAI(
            api_key=api_key
        )

    def extract(
        self,
        conversation_text: str,
    ) -> LeadExtraction:

        instructions = """
You extract sales lead information from a website visitor conversation.

Rules:

1. Extract only information explicitly provided by the visitor.
2. Never invent missing contact information.
3. Never infer a company name unless the visitor states it.
4. Never infer budget or timeline.
5. required_services must contain only services the visitor explicitly
   requests or says they are interested in.
6. Do NOT convert a business problem into a service recommendation.
   Example:
   "I need more local customers"
   should be stored as business_problem, not as "Local SEO".
7. business_problem should briefly describe the visitor's stated problem.
8. If information has not been provided, return null.
9. For required_services, return an empty array when none were explicitly
   mentioned.
10. Set intent booleans only when the visitor clearly expresses that intent.
"""

        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=conversation_text,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "lead_extraction",
                    "strict": True,
                    "schema": LEAD_EXTRACTION_SCHEMA,
                }
            },
            store=False,
        )

        data = json.loads(
            response.output_text
        )

        return LeadExtraction(**data)


def merge_lead_profile(
    current: LeadProfile,
    extracted: LeadExtraction,
) -> LeadProfile:

    string_fields = [
        "full_name",
        "company_name",
        "email",
        "phone",
        "website_url",
        "industry",
        "business_problem",
        "location",
        "budget",
        "timeline",
    ]

    for field_name in string_fields:
        value = getattr(
            extracted,
            field_name,
        )

        if value:
            setattr(
                current,
                field_name,
                value,
            )

    for service in extracted.required_services:
        if service not in current.required_services:
            current.required_services.append(
                service
            )

    boolean_fields = [
        "wants_meeting",
        "wants_callback",
        "wants_proposal",
        "requested_human",
    ]

    for field_name in boolean_fields:
        value = getattr(
            extracted,
            field_name,
        )

        if value is True:
            setattr(
                current,
                field_name,
                True,
            )

    return current
