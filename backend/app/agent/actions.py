from typing import Dict, List, Optional

from app.agent.models import LeadProfile
from app.core.config import settings

PROMPT_BOTH = "email_and_meeting"
PROMPT_MEETING = "meeting_only"
PROMPT_EMAIL = "email_only"


def visitor_requested_meeting(user_message: str) -> bool:
    text = user_message.casefold()
    return any(word in text for word in ("book", "appointment", "meeting", "schedule"))


def determine_conversion_prompt(user_message: str, lead: LeadProfile,
                                visitor_turn: int, last_prompt_turn: Optional[int],
                                last_prompt_kind: Optional[str],
                                email_captured_turn: Optional[int]) -> Optional[str]:
    """Return the one conversion invitation due on this turn."""
    if lead.meeting_booked:
        return None
    if visitor_requested_meeting(user_message):
        return PROMPT_MEETING
    if not (lead.business_problem or lead.required_services):
        return None
    if lead.email:
        if email_captured_turn is not None and visitor_turn == email_captured_turn:
            return None
        if last_prompt_kind != PROMPT_MEETING and (
                email_captured_turn is None or visitor_turn >= email_captured_turn + 1):
            return PROMPT_MEETING
        return None
    if last_prompt_turn is None:
        return PROMPT_BOTH if visitor_turn >= 3 else None
    if last_prompt_kind == PROMPT_BOTH:
        return PROMPT_MEETING if visitor_turn >= last_prompt_turn + 3 else None
    if last_prompt_kind == PROMPT_MEETING:
        return PROMPT_EMAIL if visitor_turn >= last_prompt_turn + 1 else None
    return None


def should_offer_conversion(user_message, lead, visitor_turn, last_prompt_turn):
    """Compatibility wrapper for older callers."""
    return determine_conversion_prompt(
        user_message, lead, visitor_turn, last_prompt_turn,
        PROMPT_BOTH if last_prompt_turn is not None else None, None,
    ) is not None


def should_show_attention_offer(*_args, **_kwargs):
    return False


def build_browser_actions(user_message: str, sources: List[Dict], lead: LeadProfile,
                          show_conversion: bool = True, meeting_only: bool = False,
                          prompt_kind: Optional[str] = None) -> List[Dict]:
    """Build UI actions from the same state used by response generation."""
    text = user_message.casefold()
    actions = []
    conversion_ready = bool(lead.business_problem or lead.required_services)
    meeting_requested = visitor_requested_meeting(user_message)
    if prompt_kind is None and show_conversion:
        prompt_kind = PROMPT_MEETING if meeting_only else PROMPT_BOTH
    if (prompt_kind in (PROMPT_BOTH, PROMPT_MEETING) and not lead.meeting_booked
            and (conversion_ready or meeting_requested)):
        actions.append({"type": "book_meeting", "label": "Schedule a meeting",
                        "url": f"{settings.app_base_url}/booking"})
    if (prompt_kind in (PROMPT_BOTH, PROMPT_EMAIL) and conversion_ready
            and not (lead.email or lead.phone) and not lead.meeting_booked):
        actions.append({"type": "share_email", "label": "Share my email"})
    if any(word in text for word in ("call", "phone", "speak")) and settings.company_phone:
        actions.append({"type": "call", "label": "Call us", "url": f"tel:{settings.company_phone}"})
    if any(word in text for word in ("contact form", "inquiry", "proposal", "quote")):
        actions.append({"type": "fill_form", "label": "Review inquiry form",
                        "url": f"{settings.app_base_url}/inquiry",
                        "fields": {"name": lead.full_name, "email": lead.email,
                                   "phone": lead.phone, "company": lead.company_name,
                                   "website": lead.website_url,
                                   "message": lead.business_problem}})
    navigation_words = ("show", "open", "take me", "page", "portfolio", "case stud",
                        "testimonial", "blog", "service")
    if sources and any(word in text for word in navigation_words):
        actions.append({"type": "navigate", "label": f"Open {sources[0]['title']}",
                        "url": sources[0]["url"]})
    return actions[:3]
