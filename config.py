import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM = os.getenv("RESEND_FROM", "onboarding@resend.dev")

EXTRACT_MODEL    = "claude-haiku-4-5-20251001"   # search query, file text extraction
INTERVIEW_MODEL  = "claude-sonnet-4-6"            # live interview questions
BRIEF_MODEL      = "claude-sonnet-4-6"            # research brief compilation
PDF_VISION_MODEL = "claude-sonnet-4-6"            # PDF math/vision extraction
WRITER_MODEL     = "claude-opus-4-7"              # first draft
CRITIC_MODEL     = "claude-opus-4-7"              # critique
REVISE_MODEL     = "claude-opus-4-7"              # final revision

# legacy alias kept for any direct references
RESEARCHER_MODEL = EXTRACT_MODEL


def get_models(is_paid: bool) -> dict:
    if is_paid:
        return {
            "interview": INTERVIEW_MODEL,
            "brief":     BRIEF_MODEL,
            "writer":    WRITER_MODEL,
            "critic":    CRITIC_MODEL,
            "revise":    REVISE_MODEL,
        }
    return {
        "interview": EXTRACT_MODEL,        # Haiku
        "brief":     EXTRACT_MODEL,        # Haiku
        "writer":    "claude-sonnet-4-6",  # Sonnet (not Opus)
        "critic":    "claude-sonnet-4-6",
        "revise":    "claude-sonnet-4-6",
    }

TIER_LIMITS = {
    "guest":            0,   # non-.edu, no free trial
    "free":             1,   # .edu only
    "student_premium": 10,
    "student_pro":     25,
    "premium":         10,
    "pro":             30,
}

# Research Discovery runs per month (0 = feature locked for that tier)
RESEARCH_LIMITS = {
    "guest":            0,
    "free":             0,
    "student_premium":  1,
    "student_pro":      3,
    "premium":          1,
    "pro":              5,
}

STUDENT_TIERS = {"free", "student_premium", "student_pro"}

TIER_DISPLAY = {
    "free":             "Free — 1 essay/month",
    "student_premium":  "Student Premium — $15/month · 10 essays · 1 research run",
    "student_pro":      "Student Pro — $28/month · 25 essays · 3 research runs",
    "premium":          "Premium — $25/month · 10 essays · 1 research run",
    "pro":              "Pro — $49/month · 30 essays · 5 research runs",
}
