"""Pure verdict helpers for the MCQ distractor audits. No third-party imports, on purpose.

relevance_chain.py pulls in langchain and pydantic at import time, so anything defined there
is unreachable from `--self-test`, which must run offline with no API and no extra packages.
These three functions carry the whole decision rule of the falseness gate -- in particular
that ONLY 'supported' is a failure -- so they are exactly the part worth testing. They are
re-exported from relevance_chain, so existing imports keep working.

Verdict objects are duck-typed: anything with .answer_status, .reason, .quote and
.suggested_fix works, which is what lets the self-tests use a five-line stub.
"""
from __future__ import annotations


def falseness_failing_letters(audit):
    """Letters whose distractor the answer context SUPPORTS -- the only failing status.

    'unsupported' is the healthy case and must never be treated as a defect: a distractor the
    passage is silent about is what a good distractor looks like. Conflating the two is how
    the 2026-09-12 hand-drafted replacements went the other way -- every option so obviously
    outside the passage that it was implausible, closed-book 0.154 -> 0.462.
    """
    return sorted(L for L, v in audit.items()
                  if getattr(v, "answer_status", None) == "supported")


def falseness_feedback(audit):
    """Regeneration prompt text for the distractors the answer context turned out to support."""
    lines = []
    for L in sorted(audit):
        v = audit[L]
        if getattr(v, "answer_status", None) != "supported":
            continue
        lines.append(f"- {L} is TRUE for this passage, so the item has two defensible "
                     f"answers: {getattr(v, 'reason', '')}")
        quote = getattr(v, "quote", None)
        if quote:
            lines[-1] += f"\n  the context says: {quote}"
        fix = getattr(v, "suggested_fix", None)
        if fix:
            lines[-1] += f"\n  suggested replacement: {fix}"
    return "\n".join(lines)


def falseness_status_counts(audit):
    """{'supported': n, 'contradicted': n, 'unsupported': n} -- for the run summary."""
    counts = {"supported": 0, "contradicted": 0, "unsupported": 0}
    for v in audit.values():
        st = getattr(v, "answer_status", None)
        if st in counts:
            counts[st] += 1
    return counts
