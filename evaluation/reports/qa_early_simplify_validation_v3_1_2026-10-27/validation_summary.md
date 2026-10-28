# Early simplification: focused validation

Implemented v3.1: freeze the comprehension target, remove unnecessary setup, then run two compact verification passes. Detailed structural diagnosis is reserved for residual wording failures.

## Your example

**Before:** 那个被邪灵附身的人制服了一些人。这些人随后带伤逃出了那房子，他们是谁？

**Generated and accepted:** 谁受伤逃出了那房子？

The user-confirmed target was identifying the people who escaped injured. The desired Chinese wording was withheld from model inputs and prompts. The inferred-target test also simplified the item, producing “谁带伤逃出了那房子？”.

Both verifications passed. The expected answer remains the seven sons of Sceva. No change was made to the clean passage or canonical questions.

## Results

| Focused case group | Result |
|---|---|
| Escapee question: original and split wording, each with inferred and explicit target | All four simplified to direct identity questions |
| Chinese Gold handkerchief question | Simplified; both verifications passed |
| Straightforward Chinese and English questions | Both kept unchanged |
| Causal question | Kept as a why question |
| Explicitly required overpowering relationship | Retained |
| Necessary time condition and event anchor | Both retained |
| Unsupported fixed answer | Held before rewriting |

Total: 5 simplified, 6 kept, 1 held. No item needed detailed structural diagnosis in the corrected run.

## Verifier controls

- The old split-clause candidate was rejected in both passes: context economy 2/3 for unnecessary event narration and its reference chain.
- Removing “吃饭前” from a question with two different departure events failed both passes: the tested time distinction was lost and another answer became possible.

## Correction found during development

The initial run incorrectly held a clear Chinese question in one pass because the verifier scored background details in the passage as question setup. Version 3.1 explicitly excludes the passage from language scoring and requires verbatim candidate wording for every nonzero rating. All 12 cases were rerun under the corrected rules; the initial run and implementation snapshot were retained.

## Scope and integrity

106 software tests passed. All 11 ready records passed two complete verifications, fixed metadata and option-label order were checked, and all 42 baseline source hashes remain unchanged. These are focused development cases, not a held-out accuracy estimate or human comprehension validation. The full Gold72/Hard66 sets have not been rerun with v3.1.

- report.md: all proposals, relation roles and judgments.
- ready_cases.json: passing items, including unchanged controls.
- rewritten_cases.json: the five accepted changes.
- verification.json: integrity checks.
