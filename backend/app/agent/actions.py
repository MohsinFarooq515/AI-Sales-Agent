from typing import Dict, List

from app.agent.models import LeadProfile
from app.core.config import settings


def build_browser_actions(user_message: str, sources: List[Dict], lead: LeadProfile) -> List[Dict]:
    """Translate conversational intent into safe actions executed by the widget."""
    text = user_message.casefold()
    actions = []
    if any(word in text for word in ("book", "appointment", "meeting", "schedule")):
        actions.append({"type": "book_meeting", "label": "Book with Google Calendar",
                        "url": f"{settings.app_base_url}/booking"})
    if any(word in text for word in ("call", "phone", "speak")) and settings.company_phone:
        actions.append({"type": "call", "label": "Call us", "url": f"tel:{settings.company_phone}"})
    if any(word in text for word in ("contact form", "inquiry", "proposal", "quote")):
        actions.append({
            "type": "fill_form", "label": "Review inquiry form",
            "url": f"{settings.app_base_url}/inquiry",
            "fields": {"name": lead.full_name, "email": lead.email, "phone": lead.phone,
                       "company": lead.company_name, "website": lead.website_url,
                       "message": lead.business_problem},
        })
    navigation_words = ("show", "open", "take me", "page", "portfolio", "case stud", "testimonial", "blog", "service")
    if sources and any(word in text for word in navigation_words):
        actions.append({"type": "navigate", "label": f"Open {sources[0]['title']}", "url": sources[0]["url"]})
    return actions[:3]
