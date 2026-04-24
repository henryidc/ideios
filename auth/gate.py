from config import TIER_LIMITS, RESEARCH_LIMITS, STUDENT_TIERS, TIER_DISPLAY

ADMIN_EMAILS = {"yaoyinhairongmike@gmail.com"}


def is_edu_email(email: str) -> bool:
    return email.strip().lower().endswith(".edu")


def get_available_tiers(email: str) -> dict:
    if email.strip().lower() in ADMIN_EMAILS or is_edu_email(email):
        return dict(TIER_DISPLAY)
    return {t: v for t, v in TIER_DISPLAY.items() if t not in STUDENT_TIERS}


def is_admin(email: str) -> bool:
    return email.strip().lower() in ADMIN_EMAILS


def can_write_essay(tier: str, essays_used: int, email: str = "") -> bool:
    if is_admin(email):
        return True
    return essays_used < TIER_LIMITS.get(tier, 0)


def essays_remaining(tier: str, essays_used: int, email: str = "") -> int:
    if is_admin(email):
        return 999
    return max(0, TIER_LIMITS.get(tier, 0) - essays_used)


def can_run_research(tier: str, research_used: int, email: str = "") -> bool:
    if is_admin(email):
        return True
    return research_used < RESEARCH_LIMITS.get(tier, 0)


def research_remaining(tier: str, research_used: int, email: str = "") -> int:
    if is_admin(email):
        return 999
    return max(0, RESEARCH_LIMITS.get(tier, 0) - research_used)
