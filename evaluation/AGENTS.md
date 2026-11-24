# Evaluation workflow preference

User instruction recorded November 18, 2026: while developing or revising a
pipeline, run it on just one Bible passage until the workflow is finalized.

- Limit model generation, review, and repair calls to that passage and its
  associated QA windows. Keep the same passage across iterations so changes
  can be compared.
- Show the selected passage, results, and remaining issues before expanding
  the run. Reuse valid cached results where possible.
- Wait until the user considers the workflow finalized and authorizes the
  larger run before processing the full bank. Earlier full-bank requests do
  not authorize repeated full-bank runs during further rule development.
- Local checks and tests that do not make model/API calls can cover the full
  dataset. A later explicit user instruction can change the run scope.
