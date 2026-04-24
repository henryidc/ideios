import json as _json
import anthropic
import config
from tools.search import search_web

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


_INTERVIEW_SYSTEM = """You are conducting a structured research interview to help a student develop their thinking before writing an essay. You follow a logical arc — but you stay responsive and conversational, never robotic.

Interview arc (move through these phases in order, but don't rush):

Phase 1 — Clarify the focus
  Understand exactly what aspect of the topic they want to address. What is the specific question or angle? What are they NOT writing about?

Phase 2 — Surface their personal view
  What do they actually think? What's their gut reaction? Have they experienced this firsthand? What bothers or excites them about this topic?

Phase 3 — Sharpen the argument
  What specific claim do they want to make? What would someone who disagrees say, and how would they respond? What is the one thing they most want the reader to walk away believing?

Phase 4 — Design the structure
  At the START of Phase 4, before asking any question, generate a concrete draft structure based on everything discussed so far. Use this exact format:

  📋 Draft Structure:
  **Introduction** — [hook approach + thesis]
  **Section 1: [Title]** — [core idea for this section]
  **Section 2: [Title]** — [core idea for this section]
  **Section 3: [Title]** — [core idea for this section]
  **Conclusion** — [what the reader should walk away believing]

  Default to 3 body sections. Adjust up or down only if the topic complexity, argument structure, or user's explicit preference clearly calls for it.

  Then ask: "Does this feel right? Which part would you adjust?"
  Refine the structure based on their feedback — match their voice and logical flow — before moving to Phase 5.
  Only move to Phase 5 when they are happy with the structure.

Phase 5 — Evidence and data
  Do they have research, statistics, or sources to support their points? Where would data strengthen the argument? Are there examples — personal or external — that would make it concrete?

Rules:
- Ask exactly one question per turn, never more
- Complete each phase before moving to the next — but if an answer naturally bridges two phases, follow it
- When they give a rich answer, probe deeper before moving on
- Never suggest what their argument should be — only ask questions that help them find it themselves
- Be conversational and warm, not clinical
- If they uploaded resources, reference them when relevant in Phase 5"""


def first_question(topic: str, model: str = None) -> str:
    response = _get_client().messages.create(
        model=model or config.INTERVIEW_MODEL,
        max_tokens=200,
        system=[{"type": "text", "text": _INTERVIEW_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": (
                f"The student wants to write about: {topic}\n\n"
                "Begin Phase 1. Ask a question that helps clarify exactly what aspect or angle "
                "of this topic they want to focus on. The topic statement may be broad — help them narrow it."
            )
        }]
    )
    return response.content[0].text.strip()


def next_question(topic: str, conversation: list, model: str = None) -> str:
    messages = [
        {
            "role": "user",
            "content": f"The student is writing about: {topic}\n\nBegin the interview."
        }
    ]
    for turn in conversation:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({
        "role": "user",
        "content": (
            "Ask your next interview question. One question only. "
            "Follow the interview arc — decide whether to probe deeper on the last answer "
            "or advance to the next phase. Never skip phases."
        )
    })

    response = _get_client().messages.create(
        model=model or config.INTERVIEW_MODEL,
        max_tokens=200,
        system=[{"type": "text", "text": _INTERVIEW_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=messages
    )
    return response.content[0].text.strip()


def make_search_query(topic: str, resources: str = "") -> str:
    if resources.strip():
        prompt = (
            "Based on the topic and the student's uploaded resources below, "
            "generate a search query to find web sources that corroborate or support "
            "the key claims in those resources. Stay within 380 characters, no punctuation.\n\n"
            f"Topic: {topic}\n\nResources (excerpt):\n{resources[:1000]}"
        )
    else:
        prompt = (
            "Extract the core academic topic from this prompt as a search query. "
            "Be as specific as possible within 380 characters, no punctuation.\n\n"
            f"{topic}"
        )
    response = _get_client().messages.create(
        model=config.EXTRACT_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()[:380]


def build_brief(topic: str, conversation: list, resources: str, search_results: list, model: str = None) -> str:
    sources_text = "\n".join([
        f"- {r.get('title', '')}: {r.get('content', '')[:300]}"
        for r in search_results[:4]
    ]) if search_results else "No web sources available."

    interview_text = "\n".join([
        f"{'Researcher' if t['role'] == 'assistant' else 'Student'}: {t['content']}"
        for t in conversation
    ])

    resource_section = f"\nStudent's uploaded resources:\n{resources}" if resources.strip() else ""

    response = _get_client().messages.create(
        model=model or config.BRIEF_MODEL,
        max_tokens=1000,
        system=[{"type": "text", "text": _INTERVIEW_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": (
                f"Topic: {topic}\n\n"
                f"Interview transcript:\n{interview_text}"
                f"{resource_section}\n\n"
                f"Web context:\n{sources_text}\n\n"
                "Write a research brief for the Writer agent. Include:\n"
                "- Core argument (what the student wants to say, in their own words)\n"
                "- 3-4 supporting points drawn directly from the interview transcript\n"
                "- Background framing only from web sources (context the reader needs — "
                "NOT claims or arguments the student did not express)\n"
                "- Suggested essay structure (intro, 2-3 body sections, conclusion)\n\n"
                "Critical rule: every claim and argument must trace back to something "
                "the student said. Web sources provide framing, not ideas."
            )
        }]
    )
    return response.content[0].text


def compile_brief(topic: str, conversation: list, resources: str = "") -> str:
    query = make_search_query(topic, resources)
    search_results = search_web(query)
    return build_brief(topic, conversation, resources, search_results)


# ── Research Discovery Mode ───────────────────────────────────────────────────

_DISCOVER_SYSTEM = """You are a research analyst identifying gaps and open problems in academic literature.

Given search results about a research area, output 3-5 specific, actionable research gaps as a JSON array. Each gap must be:
- Specific enough to be a real, scoped research question (not "more research needed")
- Grounded in what the sources show is missing or underexplored
- Interesting enough that a researcher would want to pursue it

Output only valid JSON, no other text:
[
  {
    "title": "Gap title — 10 words max",
    "description": "1-2 sentences describing the gap precisely.",
    "why_interesting": "1 sentence on why this is worth pursuing."
  }
]"""

_RESEARCH_INTERVIEW_SYSTEM = """You are a research advisor conducting a structured interview to help a researcher develop a research paper. Your job is to surface their own thinking and expertise — not add ideas they have not expressed.

Interview arc (move through these phases in order):

Phase 1 — Research Question
  What is the precise gap or problem they are addressing? What is the specific research question? What are the boundaries of this study?

Phase 2 — Contribution & Novelty
  What is new about this work? What does it add that existing literature does not? What would be lost if this paper were never written?

Phase 3 — Methodology
  How will they approach this? What methods, frameworks, or data sources? Why this approach over alternatives?

Phase 4 — Limitations & Scope
  Where does this approach not apply? What assumptions are being made? What are the honest limitations?

Phase 5 — Implications
  What does this mean for the field? What should other researchers do or think differently? What practical applications follow?

Rules:
- Ask exactly one question per turn, never more
- Do not suggest the researcher's answers — only ask questions that help them surface what they already know
- Be collegial, not clinical — you are a peer, not an examiner
- Complete each phase before moving to the next
- Reference earlier answers to probe deeper when they give a rich response"""


def discover_research_gaps(area: str, model: str = None) -> list:
    queries = [
        f"{area} recent advances 2024 2025",
        f"{area} challenges limitations open problems",
        f"{area} future directions research gaps",
    ]
    seen_urls, all_results = set(), []
    for q in queries:
        for r in search_web(q, max_results=4):
            url = r.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    sources_text = "\n".join(
        f"[{r.get('title', '')}]: {r.get('content', '')[:400]}"
        for r in all_results[:10]
    ) or "No search results available."

    response = _get_client().messages.create(
        model=model or config.BRIEF_MODEL,
        max_tokens=1200,
        system=_DISCOVER_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Research area: {area}\n\n"
                f"Literature search results:\n{sources_text}\n\n"
                "Identify 3-5 research gaps. Output JSON only."
            ),
        }],
    )

    text = response.content[0].text.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1].lstrip("json").strip() if len(parts) > 1 else text

    try:
        return _json.loads(text)
    except Exception:
        return []


def first_question_research(gap: dict, area: str, model: str = None) -> str:
    response = _get_client().messages.create(
        model=model or config.INTERVIEW_MODEL,
        max_tokens=250,
        system=[{"type": "text", "text": _RESEARCH_INTERVIEW_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": (
                f"Research area: {area}\n"
                f"Selected gap: {gap['title']} — {gap['description']}\n\n"
                "Begin Phase 1. Ask a question that helps the researcher clarify their precise research question "
                "within this gap. Be specific to their gap, not generic."
            ),
        }],
    )
    return response.content[0].text.strip()


def next_question_research(gap: dict, area: str, conversation: list, model: str = None) -> str:
    messages = [{
        "role": "user",
        "content": (
            f"Research area: {area}\n"
            f"Research gap: {gap['title']} — {gap['description']}\n\n"
            "Begin the research interview."
        ),
    }]
    for turn in conversation:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({
        "role": "user",
        "content": (
            "Ask your next interview question. One question only. "
            "Follow the interview arc — decide whether to probe the last answer deeper "
            "or advance to the next phase. Never skip phases."
        ),
    })

    response = _get_client().messages.create(
        model=model or config.INTERVIEW_MODEL,
        max_tokens=250,
        system=[{"type": "text", "text": _RESEARCH_INTERVIEW_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    return response.content[0].text.strip()


def build_research_brief(gap: dict, area: str, conversation: list, resources: str,
                         search_results: list, model: str = None) -> str:
    sources_text = "\n".join([
        f"- {r.get('title', '')}: {r.get('content', '')[:300]}"
        for r in search_results[:4]
    ]) if search_results else "No web sources available."

    interview_text = "\n".join([
        f"{'Advisor' if t['role'] == 'assistant' else 'Researcher'}: {t['content']}"
        for t in conversation
    ])

    resource_section = f"\nResearcher's uploaded materials:\n{resources}" if resources.strip() else ""

    response = _get_client().messages.create(
        model=model or config.BRIEF_MODEL,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": (
                f"Research area: {area}\n"
                f"Gap being addressed: {gap['title']} — {gap['description']}\n\n"
                f"Interview transcript:\n{interview_text}"
                f"{resource_section}\n\n"
                f"Relevant literature:\n{sources_text}\n\n"
                "Write a research brief for the Writer agent. Include:\n"
                "- Precise research question (from the researcher's own words)\n"
                "- Core contribution and novelty (from the interview, not inferred)\n"
                "- Methodology the researcher described\n"
                "- Key limitations the researcher acknowledged\n"
                "- Implications for the field (researcher's own framing)\n"
                "- Background framing from literature search (context only — "
                "not as claims the researcher did not make)\n"
                "- Suggested paper structure (Abstract, Introduction, Related Work, "
                "Methodology, Discussion, Conclusion)\n\n"
                "Critical rule: every claim must trace back to something the researcher "
                "said in the interview. Literature search provides framing, not ideas."
            ),
        }],
    )
    return response.content[0].text
