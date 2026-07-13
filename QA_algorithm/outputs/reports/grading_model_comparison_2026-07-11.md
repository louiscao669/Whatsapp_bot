# Core-Claim Grading Model Comparison

Generated: 2026-07-11

## Purpose

We tested whether `gpt-4o-mini` or `gpt-5.4-mini` is safer for regrading open QA answers with the stricter core-claim rubric.

The target failure mode is over-crediting answers that mention true nearby passage context but do not answer the required slot. Example:

```text
Question: What healed the bleeding woman?
Expected: Her faith in Person F.
Generated: The power emitted healed the bleeding woman.
Desired grade: 0.0 incorrect
```

## Rubric

The grader was instructed to be semantically flexible about wording, rough grammar, anonymized names, and equivalent phrasing, but strict about the expected answer's core claim and required answer slot.

Allowed scores:

```text
1.0 = contains the expected core claim
0.5 = partially answers the right slot but is incomplete, broad, or missing an important element
0.0 = wrong slot, nearby context only, contradiction, or missing the core claim
```

## Small Calibration

On the initial 10-case hand-picked test set, both models matched the expected grades on all cases.

```text
Model          Correct expected grades
gpt-4o-mini    10 / 10
gpt-5.4-mini   10 / 10
```

This small set was not enough to expose model behavior differences.

## Larger Sample

I then sampled 60 open-answer cases from existing `scores_target_llama.json` files:

```text
20 suspect old-correct / low-embedding cases
15 old-incorrect / possible partial cases
10 clean old-correct controls
10 clean old-incorrect controls
5 borderline cases
```

The models disagreed on 18 / 60 cases.

## Results

```text
Model          Incorrect   Partial   Correct
gpt-4o-mini    25          19        16
gpt-5.4-mini   38          4         18
```

Relative to the old binary grades:

```text
gpt-4o-mini:
  correct -> incorrect: 4
  correct -> correct:   16
  correct -> partial:   12
  incorrect -> incorrect: 21
  incorrect -> partial:   7

gpt-5.4-mini:
  correct -> incorrect: 11
  correct -> correct:   18
  correct -> partial:   3
  incorrect -> incorrect: 27
  incorrect -> partial:   1
```

## Important Disagreements

### Wrong Slot

```text
Question: 人物己为何让鬼魔保持沉默？
Expected: Person F is the Son of Most High A.
Generated: He rebuked them and told them not to speak.

gpt-4o-mini:  1.0 correct
gpt-5.4-mini: 0.0 incorrect
```

This is exactly the old failure mode: the answer gives the action, not the reason.

### Related Context Instead Of Core Claim

```text
Question: 是什么医治了流血的妇人？
Expected: Her faith in Person F.
Generated: His touch.

gpt-4o-mini:  0.5 partial
gpt-5.4-mini: 0.0 incorrect
```

`gpt-4o-mini` still gives partial credit for related context. `gpt-5.4-mini` correctly treats it as the wrong cause.

### Missing Required Result

```text
Question: 磐石地上的种子是谁？
Expected: Receive word, fall during testing.
Generated: The seeds on the rocky ground are those who joyfully receive the words when they hear them.

gpt-4o-mini:  1.0 correct
gpt-5.4-mini: 0.5 partial
```

`gpt-4o-mini` misses that the generated answer omits the key result: falling away during testing.

## Recommendation

Use `gpt-5.4-mini` for the full core-claim regrade.

Rationale:

- It is stricter about the required answer slot.
- It is less likely to reward nearby passage context.
- It better addresses the specific grading-noise issue that distorted the 1.5b method ranking.
- The larger sample exposed leniency in `gpt-4o-mini` that the 10-case smoke test did not catch.

## Output Handling

The regrade should write separate files named:

```text
scores_target_llama_core_claim.json
```

This keeps the old `scores_target_llama.json` files available for comparison.
