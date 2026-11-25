"""
Fast tests for the grounding checker — no keys, no network, under a second.
Each one locks in a rule we learned the hard way.
"""

from monitoring.quality import grounding


def test_code_is_not_a_citation():
    # INC-012: files[0] in code was once read as citation [0]
    answer = (
        "Read the first uploaded file with `files[0]` from the input list [1].\n"
        "```js\nconst f = files[0]\n```"
    )
    result = grounding(answer, num_sources=5)
    assert result["fake_citations"] == 0
    assert result["score"] == 1.0


def test_fake_citation_is_caught():
    # Only 5 sources exist, so [7] points at nothing
    answer = "Supabase stores your data in a dedicated Postgres database [7]."
    assert grounding(answer, num_sources=5)["fake_citations"] == 1


def test_uncited_claim_lowers_the_score():
    answer = (
        "Supabase gives every project a full Postgres database [1]. "
        "Row level security controls which rows each user is allowed to read."
    )
    assert grounding(answer, num_sources=5)["score"] == 0.5


def test_heading_citations_do_not_count():
    # OBS-011: strict by design — a citation on a heading covers no claims.
    # If this rule ever changes, the 58% baseline must be re-measured.
    answer = (
        "## Setup [1]\n"
        "- Create a new project in the Supabase dashboard\n"
        "- Copy the project URL and the anon key"
    )
    assert grounding(answer, num_sources=5)["score"] == 0.0


def test_no_claims_means_no_score():
    # A short reply has nothing to check, so no score (not a zero)
    assert grounding("Too short.", num_sources=5)["score"] is None