# Where the selection came from

The original selection took place in a Codex chat. On August 28, 2026 at 9:09 a.m. Eastern, the user asked:

> can you get the strong QAs from all the passages

The active turn recorded `gpt-5.6-sol` at low reasoning effort. At 9:11 a.m. the assistant reported that it had consolidated 66 questions across 12 passage units. It wrote `tier1_strong_candidates.json`. These events and the destination are in the [original local chat archive](</Users/louiscao/.codex/sessions/2026/08/17/rollout-2026-08-17T14-42-18-01a01108-19fa-7382-b032-96e2e0403cc6.jsonl.zst>). The [consolidated selection](</Users/louiscao/bible translation/ETEN-Bible-translation-project/v3/combo-v3-plus/v3/combo/qa_generation/outputs/tier1_hard_v3/tier1_strong_candidates.json>) matches all 66 published English questions and keys.

The final request relied on earlier exchanges. On August 21, the assistant named “naturalness, self-containment, answer completeness, and discriminating value” as the selection criteria. On August 26, the user asked for the strong candidates from the Tier 1 pipeline results. In its first pass the assistant described excluding vague, unnatural, incidental, redundant or weakly discriminating items. It corrected verse metadata for nine otherwise acceptable questions. The final selection followed a corrected Judges 18 run.

Claude's September 4 artifact displays the selected questions with four rubric dimensions: structure dependence, statement uniqueness, answer certainty, and centrality. The accessible Claude history yielded the artifact and its description. I found no originating Claude selection instruction. [Strong-66 Candidate Set in Claude](https://claude.ai/epitaxy/artifact/KE19Ma4JwD58oVfqs8mcst)

The benchmark's **original_request** arm uses the verbatim final user request with common scoring and output instructions. **historical_context** augments it with a reconstruction of earlier criteria, and **luke_examples** adds examples from the earlier Luke discussion. **claude_artifact_rubric** tests a new prompt based on the displayed rubric. All runs omit the historical selection decisions, per-window rationale, generator scores and ranks. These are prompt replays on the original items, not restorations of the full chat or original model snapshot. The [frozen design and exact prompts](design.json) give the wording used.
