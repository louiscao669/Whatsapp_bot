"""LangChain relevance audit for MCQ distractors — the second-model check.

The rewrite prompt alone cannot be trusted to enforce "every distractor must be a possible
ANSWER to the question". Its characteristic failure is the true-but-irrelevant distractor:

    Q: 珂温和哈丽为什么被认为是义人？
    A. 他们属于洛谷的祭司班次     <- true, in the passage, but not a REASON for righteousness
    B. 他们是隆松的后裔           <- same
    C. 他们是索伦王兰维时代的人   <- same
    D. 他们无可指摘地遵守了诫命   [correct]

All three distractors are drawn from the passage and all three are true, yet a respondent who
merely understands the question eliminates them without reading anything. The item measures
nothing.

This module asks a SECOND model one narrow question per distractor -- "could this be the
answer, to someone who has not read the passage?" -- and returns the verdicts so the caller
can regenerate the failures. Kept separate from the rewriter on purpose: the model that wrote
an option is the worst judge of whether it is relevant.

House style follows qa_generation/prompts/*.py: ChatPromptTemplate | llm.with_structured_output.
"""
from __future__ import annotations

import os
import warnings
from typing import List, Literal, Optional

# langchain-openai's with_structured_output round-trips the parsed object through a field
# typed as None, so pydantic emits a serializer warning on every single call. It is cosmetic
# -- the parsed RelevanceAudit is returned intact -- but at ~100 items it drowns the log.
# Filtered narrowly by message so real pydantic warnings still surface.
warnings.filterwarnings(
    "ignore",
    message=r".*PydanticSerializationUnexpectedValue.*",
    category=UserWarning,
)

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

LETTERS = "ABCD"


# ------------------------------------------------------------------ output schema
class DistractorVerdict(BaseModel):
    letter: Literal["A", "B", "C", "D"]
    is_possible_answer: bool = Field(
        description="True if someone who had NOT read the passage could believe this is the "
                    "answer to the question. False if it can be ruled out on relevance alone "
                    "-- i.e. it does not address what the question asks."
    )
    reason: str = Field(description="One short clause. Chinese or English.")
    suggested_fix: Optional[str] = Field(
        default=None,
        description="If is_possible_answer is false, a rewritten option that DOES answer the "
                    "question, reusing the same passage material where possible.",
    )


class RelevanceAudit(BaseModel):
    verdicts: List[DistractorVerdict]


# ------------------------------------------------------------------------- prompt
relevance_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You audit the distractors of a Chinese reading-comprehension multiple-choice "
        "question. Judge ONE thing only: is each distractor a possible ANSWER to the question "
        "asked?\n\n"
        "A distractor is a possible answer if a reader who has NOT read the passage could "
        "believe it might be correct. It is NOT a possible answer if it can be dismissed on "
        "relevance alone -- if it is a true or plausible statement that simply does not "
        "address what the question asks. Example: for '为什么被认为是义人？' (why were they "
        "considered righteous?), '他们是某人的后裔' is a fact about ancestry, not a reason for "
        "righteousness, so it is NOT a possible answer.\n\n"
        "Do NOT judge whether the distractor is true, and do NOT judge the correct option. "
        "Being false is what a distractor is for. Judge only relevance to the question.\n\n"
        "When a distractor fails, supply suggested_fix: the same passage material recast so it "
        "DOES answer the question. Return a verdict for every distractor letter given.",
    ),
    (
        "human",
        "QUESTION: {question}\n\n"
        "CORRECT OPTION ({correct}): {correct_text}\n"
        "  -- note what KIND of answer this is; the distractors must be the same kind.\n\n"
        "DISTRACTORS TO AUDIT:\n{distractors}\n\n"
        "ANSWER CONTEXT (for judging what material is available, not for judging truth):\n"
        "{window}",
    ),
])


# OpenAI's July 2026 line is the GPT-5.6 family: sol ($5/$30 per MTok), terra ($2.50/$15),
# luna ($1/$6). They are REASONING models -- quality is controlled by reasoning_effort
# (none/low/medium/high/xhigh/max), not by temperature, which reasoning models ignore or
# reject. Terra at medium effort is the sweet spot for this job: the audit is a judgment
# call, which is exactly what reasoning buys, but it is a narrow one-question judgment that
# does not need the frontier model.
REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def build_relevance_chain(model: str = "gpt-5.6-terra", provider: str = "openai",
                          temperature: float = 0.0, reasoning_effort: str | None = "medium"):
    """ChatPromptTemplate | structured-output LLM. Returns a runnable."""
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        llm = ChatOllama(model=model, temperature=temperature,
                         base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    else:
        from langchain_openai import ChatOpenAI
        kwargs = {"model": model}
        if any(model.startswith(p) for p in REASONING_PREFIXES):
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort   # temperature is not the knob
        else:
            kwargs["temperature"] = temperature
        llm = ChatOpenAI(**kwargs)
    return relevance_prompt | llm.with_structured_output(RelevanceAudit)


# -------------------------------------------------------------------------- audit
def audit_distractors(chain, question, options, correct, window):
    """Return {letter: DistractorVerdict} for the three distractors.

    On any failure (parse error, refusal, transport) returns {} -- an empty audit means
    "no opinion", and the caller keeps the item rather than discarding it on a flake.
    """
    letters = [L for L in LETTERS if L != correct and options.get(L)]
    body = "\n".join(f"{L}. {options[L]}" for L in letters)
    try:
        out = chain.invoke({
            "question": question,
            "correct": correct,
            "correct_text": options.get(correct, ""),
            "distractors": body,
            "window": window,
        })
    except Exception:
        return {}
    if out is None:
        return {}
    verdicts = getattr(out, "verdicts", None) or []
    return {v.letter: v for v in verdicts if v.letter in letters}


# ------------------------------------------------- meaning guard for the answer rewrite
class Equivalence(BaseModel):
    same_fact: bool = Field(
        description="True only if the two sentences assert the SAME fact about the passage: "
                    "same entities, same relation, same polarity, same numbers. Rewording, "
                    "length and style differences do not matter."
    )
    reason: str = Field(description="One short clause.")


equivalence_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You check whether a rewritten answer option still asserts exactly the same fact as "
        "the original. Judge the CLAIM, not the wording: length, phrasing and register may "
        "differ freely. Answer same_fact=false if any entity, relation, number, or polarity "
        "changed, or if the rewrite is vaguer or broader in a way that would change whether "
        "it is the correct answer to the question.",
    ),
    ("human", "QUESTION: {question}\n\nORIGINAL: {original}\nREWRITTEN: {rewritten}"),
])


def build_equivalence_chain(model: str = "gpt-5.6-sol", provider: str = "openai",
                            reasoning_effort: str | None = "low"):
    """Guard for the correct-option rewrite: it must not move the fact under test."""
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        llm = ChatOllama(model=model, temperature=0.0,
                         base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    else:
        from langchain_openai import ChatOpenAI
        kwargs = {"model": model}
        if any(model.startswith(p) for p in REASONING_PREFIXES):
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
        else:
            kwargs["temperature"] = 0.0
        llm = ChatOpenAI(**kwargs)
    return equivalence_prompt | llm.with_structured_output(Equivalence)


def check_equivalent(chain, question, original, rewritten):
    """True if the rewrite preserves the fact. Fails CLOSED: on any error, returns False so
    the caller keeps the original -- a lost length match is cheap, a drifted fact is not."""
    try:
        out = chain.invoke({"question": question, "original": original,
                            "rewritten": rewritten})
    except Exception:
        return False
    return bool(out is not None and getattr(out, "same_fact", False))


def failing_letters(audit):
    return sorted(L for L, v in audit.items() if not v.is_possible_answer)


def audit_feedback(audit):
    """Human/model-readable summary of what failed, for the regeneration prompt."""
    lines = []
    for L in sorted(audit):
        v = audit[L]
        if v.is_possible_answer:
            continue
        line = f"- {L} is not a possible answer to the question: {v.reason}"
        if v.suggested_fix:
            line += f"\n  suggested replacement: {v.suggested_fix}"
        lines.append(line)
    return "\n".join(lines)
