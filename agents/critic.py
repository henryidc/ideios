import anthropic
import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


_SYSTEM = """You are the Critic for Ideios, an academic writing assistant. Your job is to evaluate drafts with precision and honesty.

Evaluate on:
1. Argument clarity — is the thesis clear and specific?
2. Evidence — are claims supported or merely asserted?
3. Structure — does the piece flow logically?
4. Voice — does it sound like the student or like generic AI output?
5. Opening and closing — are they strong?

Be direct. Name specific problems and propose specific fixes. Do not praise vaguely."""


_RESEARCH_CRITIC_SYSTEM = """You are the Critic for Ideios, evaluating a research paper draft.

Evaluate on:
1. Research question — is it precise, specific, and answerable?
2. Contribution — is the novelty clearly stated and defensible?
3. Methodology — is the approach justified and described with enough precision?
4. Limitations — are they acknowledged honestly and specifically?
5. Argument flow — does the paper build logically from problem to contribution to implications?
6. Academic integrity — are all claims grounded in what the researcher expressed (no invented claims)?

Be direct. Name specific problems with specific fixes. Do not praise vaguely."""


def critique_research_paper(draft: str, research_brief: str, model: str = None) -> str:
    response = _get_client().messages.create(
        model=model or config.CRITIC_MODEL,
        max_tokens=1000,
        system=[{"type": "text", "text": _RESEARCH_CRITIC_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": (
                f"Research brief (what the researcher intended):\n{research_brief}\n\n"
                f"Draft to evaluate:\n{draft}\n\n"
                "Provide structured critique with specific, actionable feedback.\n\n"
                "Format:\n"
                "**Strengths** (2-3 points)\n"
                "**Issues** (2-4 specific problems with proposed fixes)\n"
                "**Priority fix** (the single most important change)"
            ),
        }],
    )
    return response.content[0].text


def critique_draft(draft: str, research_brief: str, model: str = None) -> str:
    response = _get_client().messages.create(
        model=model or config.CRITIC_MODEL,
        max_tokens=800,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": (
                f"Research brief (what the student intended):\n{research_brief}\n\n"
                f"Draft to evaluate:\n{draft}\n\n"
                "Provide structured critique with specific, actionable feedback.\n\n"
                "Format:\n"
                "**Strengths** (2-3 points)\n"
                "**Issues** (2-4 specific problems with proposed fixes)\n"
                "**Priority fix** (the single most important change)"
            )
        }]
    )
    return response.content[0].text
