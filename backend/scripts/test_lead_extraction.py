import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(BACKEND_DIR),
)


from app.agent.lead_extractor import (
    LeadExtractor,
    merge_lead_profile,
)

from app.agent.lead_scoring import (
    calculate_lead_score,
)

from app.agent.models import LeadProfile


def print_profile(lead):
    print()
    print("-" * 60)

    print(
        f"Name: {lead.full_name}"
    )

    print(
        f"Company: {lead.company_name}"
    )

    print(
        f"Email: {lead.email}"
    )

    print(
        f"Phone: {lead.phone}"
    )

    print(
        f"Website: {lead.website_url}"
    )

    print(
        f"Industry: {lead.industry}"
    )

    print(
        f"Location: {lead.location}"
    )

    print(
        f"Services: {lead.required_services}"
    )

    print(
        f"Problem: {lead.business_problem}"
    )

    print(
        f"Budget: {lead.budget}"
    )

    print(
        f"Timeline: {lead.timeline}"
    )

    print(
        f"Wants meeting: {lead.wants_meeting}"
    )

    print(
        f"Wants proposal: {lead.wants_proposal}"
    )

    print(
        f"Score: {lead.score}/100"
    )

    print(
        f"Temperature: "
        f"{lead.temperature.value.upper()}"
    )


def main():

    extractor = LeadExtractor()

    lead = LeadProfile()

    messages = [
        (
            "My name is Ahmed Khan. "
            "I run Bright Smile Dental, "
            "a dental clinic in Houston."
        ),
        (
            "Our website is "
            "https://brightsmile.example. "
            "We're struggling to get enough "
            "local appointments and I'm interested "
            "in Local SEO."
        ),
        (
            "You can reach me at "
            "ahmed@example.com or +1 555 123 4567. "
            "Our budget is around $3,000 and we'd "
            "like to start this month. "
            "I'd also like to book a meeting and "
            "receive a proposal."
        ),
    ]

    conversation = []

    for index, message in enumerate(
        messages,
        start=1,
    ):
        conversation.append(
            f"Visitor: {message}"
        )

        conversation_text = "\n".join(
            conversation
        )

        extracted = extractor.extract(
            conversation_text
        )

        lead = merge_lead_profile(
            lead,
            extracted,
        )

        lead = calculate_lead_score(
            lead
        )

        print()
        print("=" * 60)
        print(
            f"AFTER MESSAGE {index}"
        )
        print("=" * 60)

        print_profile(lead)


if __name__ == "__main__":
    main()