import anthropic
import config

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


_SYSTEM = """You are the Writer for Ideios, an academic writing assistant. You produce structured academic prose that expresses the student's own thinking — not generic content.

Rules:
- Every claim, argument, and supporting point must come from what the student said in the interview. No exceptions.
- Web sources in the brief are background framing only — use them to establish context for the reader (e.g. "researchers have noted...") but never as a source of claims the student did not make themselves.
- Write in the student's voice, grounded in their exact words and phrasing where possible
- Produce well-structured prose with clear transitions
- Target 600-900 words unless the brief specifies otherwise
- Do not pad, hedge, or add ideas the student did not surface
- For any mathematical expressions, use LaTeX notation: $...$ for inline math, $$...$$ for display equations"""


def write_draft(research_brief: str, model: str = None) -> str:
    response = _get_client().messages.create(
        model=model or config.WRITER_MODEL,
        max_tokens=2000,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": f"Research brief:\n{research_brief}\n\nWrite the first draft now."
        }]
    )
    return response.content[0].text


_RESEARCH_SYSTEM = """You are the Writer for Ideios, producing an academic research paper draft. You write in the researcher's own voice, grounded entirely in what they expressed during the interview.

Output structure (use these exact headings):
**Abstract** (150-200 words): problem, approach, contribution, implications
**Introduction**: establish the gap, state the research question, preview the paper
**Related Work**: position this work relative to existing approaches
**Methodology**: the researcher's approach, clearly justified
**Discussion**: what the findings mean, honest limitations acknowledged
**Conclusion**: contribution restated, future directions

Rules:
- Every claim, argument, and finding must come from what the researcher said in the interview. No exceptions.
- Literature references in the brief are for framing only — use them to position the work (e.g. "prior work has shown...") but never as a source of claims the researcher did not make themselves.
- 1500-2500 words total
- Academic register but clear and direct — no unnecessary jargon
- Do not invent citations; write [Author, Year] only where the researcher named specific works
- For mathematical expressions use LaTeX: $...$ inline, $$...$$ for display
- Do not pad with generic field overviews the researcher did not mention"""


def write_research_paper(research_brief: str, model: str = None) -> str:
    response = _get_client().messages.create(
        model=model or config.WRITER_MODEL,
        max_tokens=3500,
        system=[{"type": "text", "text": _RESEARCH_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": f"Research brief:\n{research_brief}\n\nWrite the research paper draft now.",
        }],
    )
    return response.content[0].text


def revise_research_paper(draft: str, critique: str, model: str = None) -> str:
    response = _get_client().messages.create(
        model=model or config.REVISE_MODEL,
        max_tokens=3500,
        system=[{"type": "text", "text": _RESEARCH_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": (
                f"Original draft:\n{draft}\n\n"
                f"Critic's feedback:\n{critique}\n\n"
                "Revise the paper. Address every point in the feedback. "
                "Preserve the researcher's voice and all claims they expressed."
            ),
        }],
    )
    return response.content[0].text


def revise_draft(draft: str, critique: str, model: str = None) -> str:
    response = _get_client().messages.create(
        model=model or config.REVISE_MODEL,
        max_tokens=2000,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": (
                f"Original draft:\n{draft}\n\n"
                f"Critic's feedback:\n{critique}\n\n"
                "Revise the draft. Address every point in the feedback. Preserve the student's voice and core argument."
            )
        }]
    )

    return response.content[0].text
