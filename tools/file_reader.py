import io
import base64
import anthropic
import config

COMPRESS_THRESHOLD = 6000   # characters; below this, pass raw text directly
COMPRESSED_MAX = 5000       # character cap on AI-extracted output

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _extract_pdf_vision(raw: bytes) -> str:
    """Send PDF to Claude Vision — preserves equations as LaTeX."""
    b64 = base64.standard_b64encode(raw).decode("utf-8")
    response = _get_client().messages.create(
        model=config.PDF_VISION_MODEL,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
                },
                {
                    "type": "text",
                    "text": (
                        "Extract all text from this document exactly as written. "
                        "For mathematical expressions, render them in LaTeX: "
                        "use $...$ for inline math and $$...$$ for display equations. "
                        "Preserve all notation, symbols, and structure faithfully."
                    ),
                },
            ],
        }],
    )
    return response.content[0].text.strip()


def extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    raw = uploaded_file.read()

    if name.endswith(".txt"):
        return raw.decode("utf-8", errors="ignore")

    if name.endswith(".pdf"):
        return _extract_pdf_vision(raw)

    if name.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs)

    return ""


def extract_all(uploaded_files) -> str:
    parts = []
    for f in uploaded_files:
        text = extract_text(f).strip()
        if text:
            parts.append(f"--- {f.name} ---\n{text}")
    return "\n\n".join(parts)


def _ai_extract(raw_text: str, topic: str) -> str:
    """Use Haiku to pull the most relevant content from a large document."""
    import anthropic
    import config

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=config.RESEARCHER_MODEL,
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": (
                f"Topic the student is writing about: {topic}\n\n"
                f"Document:\n{raw_text[:20000]}\n\n"
                "Extract only the passages, data points, quotes, and arguments that are "
                "directly relevant to the topic above. Preserve exact wording where possible. "
                f"Output must not exceed {COMPRESSED_MAX} characters. Skip irrelevant sections entirely."
            )
        }]
    )
    return response.content[0].text.strip()


def process_resources(raw_text: str, topic: str) -> str:
    """
    Return raw_text if small enough to pass cheaply.
    Otherwise compress with AI to extract only what's relevant to the topic.
    """
    if not raw_text.strip():
        return ""
    if len(raw_text) <= COMPRESS_THRESHOLD:
        return raw_text
    return _ai_extract(raw_text, topic)
