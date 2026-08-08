from app.agent.models import (
    LeadProfile,
    LeadTemperature,
)


def calculate_lead_score(
    lead: LeadProfile,
) -> LeadProfile:

    score = 0

    # Contact information
    if lead.full_name:
        score += 5

    if lead.email:
        score += 10

    if lead.phone:
        score += 10

    # Business qualification
    if lead.company_name:
        score += 5

    if lead.website_url:
        score += 5

    if lead.industry:
        score += 5

    # Buying intent
    if lead.required_services:
        score += 15

    if lead.business_problem:
        score += 10

    if lead.budget:
        score += 10

    if lead.timeline:
        score += 10

    # Strong conversion signals
    if lead.wants_meeting:
        score += 10

    if lead.wants_callback:
        score += 5

    if lead.wants_proposal:
        score += 10

    score = min(score, 100)

    if score >= 70:
        temperature = LeadTemperature.HOT

    elif score >= 35:
        temperature = LeadTemperature.WARM

    else:
        temperature = LeadTemperature.COLD

    lead.score = score
    lead.temperature = temperature

    return lead