import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(BACKEND_DIR),
)


from app.agent.lead_scoring import (
    calculate_lead_score,
)

from app.agent.models import LeadProfile


def test_lead(name, lead):

    result = calculate_lead_score(
        lead
    )

    print()
    print("=" * 60)
    print(name)
    print("=" * 60)

    print(
        f"Score: {result.score}/100"
    )

    print(
        f"Temperature: "
        f"{result.temperature.value.upper()}"
    )


def main():

    test_lead(
        "Visitor A",
        LeadProfile(
            industry="Dental Clinic",
            required_services=[
                "Local SEO"
            ],
        ),
    )

    test_lead(
        "Visitor B",
        LeadProfile(
            full_name="John Smith",
            email="john@example.com",
            company_name="ABC Dental",
            industry="Dental Clinic",
            website_url="https://example.com",
            required_services=[
                "Local SEO",
                "Google Ads",
            ],
            business_problem=(
                "Need more local appointments"
            ),
        ),
    )

    test_lead(
        "Visitor C",
        LeadProfile(
            full_name="Sarah",
            email="sarah@example.com",
            phone="+1234567890",
            company_name="Demo Store",
            industry="E-commerce",
            website_url="https://example.com",
            required_services=[
                "Shopify SEO"
            ],
            business_problem=(
                "Low organic sales"
            ),
            budget="$2,000-$5,000",
            timeline="Within 30 days",
            wants_meeting=True,
            wants_proposal=True,
        ),
    )


if __name__ == "__main__":
    main()