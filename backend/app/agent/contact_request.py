import re
from typing import Optional


CONTACT_TARGETS = (
    ("sales team", r"sales?\s+(?:team|department|representative|rep|person)"),
    ("CEO", r"(?:the\s+)?ceo"),
    ("founder", r"(?:the\s+)?(?:co-?founder|founder)"),
    ("owner", r"(?:the\s+)?(?:business\s+|company\s+)?owner"),
    ("manager", r"(?:the\s+)?(?:sales\s+|general\s+)?manager"),
    ("director", r"(?:the\s+)?(?:sales\s+|managing\s+)?director"),
    ("team", r"(?:a\s+)?(?:team\s+member|human|person|representative|someone)"),
)

CONTACT_INTENT = re.compile(
    r"\b(?:contact|speak|talk|connect|chat|get\s+in\s+touch|reach|communicate)\b",
    flags=re.IGNORECASE,
)


def requested_contact_target(user_message: str) -> Optional[str]:
    """Return an explicitly requested company role, without inferring one."""
    if not CONTACT_INTENT.search(user_message):
        return None
    for label, pattern in CONTACT_TARGETS:
        if re.search(rf"\b{pattern}\b", user_message, flags=re.IGNORECASE):
            return label
    return None


def contact_request_answer(target: str, has_email: bool) -> str:
    """Build the guaranteed English handover acknowledgement."""
    if has_email:
        return f"Our {target} will contact you at the email address you shared."
    return f"Please share your email address so our {target} can contact you."
