from agents.researcher import compile_brief
from agents.writer import write_draft, revise_draft
from agents.critic import critique_draft


def run_essay_pipeline(topic: str, conversation: list, resources: str = "") -> dict:
    """
    Full pipeline: research brief → first draft → critique → revised final draft.
    conversation: list of {"role": "assistant"|"user", "content": "..."} dicts from the interview.
    resources: extracted text from any uploaded files.
    """
    brief = compile_brief(topic, conversation, resources)
    draft = write_draft(brief)
    critique = critique_draft(draft, brief)
    final_draft = revise_draft(draft, critique)

    return {
        "brief": brief,
        "draft": draft,
        "critique": critique,
        "final_draft": final_draft,
    }
