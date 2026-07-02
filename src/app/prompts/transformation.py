ATOMIC_UNIT_SYSTEM = """You decompose source text into atomic units for a research retrieval system.

An atomic unit is ONE self-contained statement that is fully understandable without any surrounding context.

Rules:
- Exactly one claim, fact, definition, or statistic per unit.
- Resolve every pronoun and ambiguous reference using the document metadata provided. Never output "it", "they", "this method" — name the entity.
- Preserve meaning exactly. Do not merge, summarize, or editorialize.
- Keep qualifiers: dates, numbers, conditions, and attribution ("According to <source>...") when the text presents something as a claim rather than settled fact.
- Ignore navigation text, ads, cookie notices, author bios, and calls to action.

Return ONLY valid JSON, no markdown fences:
{"units": [{"text": "...", "kind": "fact" | "definition" | "statistic" | "claim" | "opinion"}]}
If the text contains no substantive content, return {"units": []}."""

def build_atomic_unit_messages(chunk_text: str, title: str, url: str, topic: str) -> list[dict]:
    user = (
        f"Document title: {title}\n"
        f"URL: {url}\n"
        f"Research topic: {topic}\n\n"
        f"Text:\n{chunk_text}"
    )
    return [
        {"role": "system", "content": ATOMIC_UNIT_SYSTEM},
        {"role": "user", "content": user},
    ]