"""
Grounding check — a free, instant quality signal on every answer.

Our prompt requires a source like [1] on every claim. This checks whether the
model followed that rule:
  - what share of claim sentences carry a source
  - whether any source number points at a source that doesn't exist

It is a warning signal, not proof: a sentence can carry [1] while [1] doesn't
actually say that. An LLM judge on a sample can be added later for that.

Code is ignored throughout: `files[0]` in a code sample is not a citation (INC-012).
"""

import re

CITATION = re.compile(r"\[(\d+)\]")
MIN_WORDS = 6       # shorter lines ("Here's how:") aren't real claims
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?!\[\d)|(?<=\])\s+(?=[A-Z])")


def without_code(answer):
    """Remove code so it is never read as text or citations.

    Code blocks are dropped. Inline code becomes the word 'code', so a sentence
    like "Call `signInWithOAuth()` with `github` [1]" keeps its length.
    """
    text = re.sub(r"```.*?```", " ", answer, flags=re.DOTALL)
    return re.sub(r"`[^`\n]*`", "code", text)


def claim_sentences(text):
    """Split code-free text into sentences worth checking."""
    claims = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):                     # skip blanks and headings
            continue
        line = re.sub(r"^([-*]|\d+\.)\s+", "", line)             # drop bullet markers
        for sentence in SENTENCE_END.split(line):
            if len(sentence.split()) >= MIN_WORDS:
                claims.append(sentence)
    return claims


def grounding(answer, num_sources):
    """Score one answer. Returns counts plus a 0-1 score (None if nothing to check)."""
    text = without_code(answer)
    claims = claim_sentences(text)
    cited = [s for s in claims if CITATION.search(s)]
    refs = [int(n) for n in CITATION.findall(text)]
    fake = [n for n in refs if n < 1 or n > num_sources]
    return {
        "claims": len(claims),
        "cited": len(cited),
        "score": round(len(cited) / len(claims), 3) if claims else None,
        "fake_citations": len(fake),
    }