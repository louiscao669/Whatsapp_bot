# Whole-question burden experiment

Four prompts: previous wording gate as baseline; whole-item dimension rubric; target-preserving counterfactual comparison; independent dimension gates. The three new prompts and their 0–3 dimension anchors were frozen before calls. All use GPT-6.1 Sol. The baseline retains its original output schema; the new prompts return dimension scores and evidence, so this comparison concerns complete screening procedures, not a single isolated sentence added to an identical response schema.

Forty cases, twice per prompt, shuffled batches of eight: twenty previously examined real questions (eight provisionally clear, eight concerns, four borderline); four focal handkerchief variants; four constructed diagnostic examples; twelve seeded real corpus questions absent from prior prompt trials. Categories and previous scores are not supplied. Descriptive case IDs are retained in the main comparison and may provide incidental cues. A separate focal repeat uses neutral IDs and independently shuffled order to check whether conclusions persist without descriptive variant IDs.

The four constructed examples check explicit leakage, its nonleaking counterpart, a necessary location anchor, and an underspecified question missing that anchor. Explicit target metadata is provided for the constructed and focal items. Other targets must be inferred, with that status reported. The intended target matters: a setup can supply contextual information without leaking the particular outcome being tested.

The English and Chinese questions use different passage scopes and formats. No language or dataset superiority inference is justified. Full English source context can make broad temporal questions ambiguous; native-language trial decisions depend on the exact context shown. Keep the context with every judgment.

The dimension rubric separates naturalness, avoidable processing burden, context adequacy/necessity, and answer leakage. A simple passive, why-question, necessary temporal condition or name is not intrinsically a failure. Multiple sentences must be assessed jointly. The model must identify concrete avoidable burden instead of mechanically rejecting clause types. Counterfactual rewrites are diagnostic proposals, not approved replacements; compare semantic targets before using them.

These are predicted burden judgments, not measured human burden. The clear controls and prior concerns are provisional assistant annotations. The fresh corpus sample is new to these trials but was not independently labelled by humans, so it is not a validated held-out benchmark. No accuracy/sensitivity claims should be made from agreement alone. Repetitions on a question are correlated; report case-level consistency and disagreements.

Prompts are not adjusted after results in this experiment. Production questions and prompts are unchanged. All raw outputs, request hashes, model identifiers, usage and dimension/decision consistency checks are retained.
