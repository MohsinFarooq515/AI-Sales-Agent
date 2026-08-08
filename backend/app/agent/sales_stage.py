from app.agent.models import (
    LeadProfile,
    SalesStage,
)


def determine_sales_stage(
    lead: LeadProfile,
) -> SalesStage:

    if lead.requested_human:
        return SalesStage.HANDOVER

    if (
        lead.wants_meeting
        or lead.wants_callback
        or lead.wants_proposal
    ):
        return SalesStage.CONVERSION

    contact_available = (
        bool(lead.email)
        or bool(lead.phone)
    )

    if (
        lead.required_services
        and contact_available
    ):
        return SalesStage.QUALIFICATION

    if (
        lead.business_problem
        or lead.industry
        or lead.required_services
    ):
        return SalesStage.RECOMMENDATION

    return SalesStage.DISCOVERY