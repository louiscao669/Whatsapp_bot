# Tier-1 MCQ validation against BSB

Date: 2026-08-14

## Scope

Validated the 90 canonical MCQ records in
`evaluation/datasets/qa/tier1_QAs_easy/t1_*_all_formats.json` against the 10
BSB passages in `evaluation/datasets/passages/tier1_bsb/`.

The requested 94-item manifest does not exist in the current workspace. The
upstream pre-clean combined export contains 93 records; the canonical cleaned
set contains 90. This report does not invent or silently add four records.

## Result

| Status | Count |
|---|---:|
| Pass unchanged | 86 |
| Rewrite wording, preserve ID and key | 3 |
| Unsupported as written, repair choice text | 1 |
| Rekey | 0 |
| Ambiguous | 0 |
| Verse-window update | 0 |
| Total reviewed | 90 |

All keyed facts remain compatible with BSB after the four wording repairs
below. No item needs a different answer letter, and BSB retains the evidence in
the currently assigned verse/window for every item.

## Required repairs

### `t1_judg9:w5fv` — unsupported as written

- Current question: `Who is Abimelech's father?`
- Current keyed choice D: `Gideon`
- BSB evidence, Judges 9:1: `Abimelech son of Jerubbaal`
- Problem: the supplied BSB passage does not establish that Jerubbaal is Gideon.
  The item therefore requires outside Bible knowledge.
- Repair: keep ID and key D; change choice D to `Jerubbaal`.
- Window: keep `9:1–3`.

### `t1_judg17_18:e4u2` — rewrite keyed wording

- Current question: `Why are Dan's descendants seeking territory?`
- Current keyed choice D: `They couldn't occupy their assigned land`
- BSB evidence, Judges 18:1: no inheritance had yet fallen to the tribe of Dan
  among the tribes of Israel.
- Problem: not yet receiving an inheritance is not the same claim as being
  unable to occupy an assigned territory.
- Repair: keep ID and key D; change D to
  `They had not yet received an inheritance among Israel's tribes`.
- Window: keep `18:1–3`.

### `t1_acts19:b1be` — rewrite stem

- Current question: `What do handkerchiefs do when they touch Paul?`
- Current keyed choice D: `Heal the sick and expel spirits`
- BSB evidence, Acts 19:11–12: handkerchiefs and aprons that had touched Paul
  were taken to the sick; diseases and evil spirits then left them.
- Problem: the current stem attaches the effect to touching Paul instead of to
  being taken to the sick.
- Repair: keep ID and key D; change the stem to
  `What happened when handkerchiefs and aprons that had touched Paul were taken to the sick?`
- Window: keep `19:11–13`.

### `t1_acts23:exnu` — rewrite stem and keyed choice

- Current question: `What do 40 men plan to do with Paul according to their presentation to the priests?`
- Current keyed choice D: `Bring him to the council to kill him`
- BSB evidence, Acts 23:14–15: the Sanhedrin is to request that Paul be brought
  down on a pretext; the conspirators plan to kill him on the way.
- Problem: Paul is not to be killed at the council, and the conspirators are not
  themselves the party that brings him.
- Repair: keep ID and key D. Use:
  - Stem: `How do the conspirators plan to get close enough to kill Paul?`
  - D: `Have the Sanhedrin request his transfer, then kill him on the way`
- Window: keep `23:14–16`.

## Pre-existing structural warnings

These are not caused by the BSB change, but they remain in the canonical
90-record set:

- `t1_2chr26:rxf3` and `t1_2chr26:rxf3#2` have identical MCQ content.
- `t1_acts20:jxkk` and `t1_acts20:jxkk#2` have identical MCQ content.

If membership must remain fixed, retain them and document the duplicate
weighting. If the goal is 90 independent questions, the `#2` copies should not
be treated as independent evidence.

## Passage-level disposition

| Passage | Reviewed | Repair | Unchanged |
|---|---:|---:|---:|
| 2 Chronicles 26 | 15 | 0 | 15 |
| 2 Kings 6:24–7:20 | 9 | 0 | 9 |
| Acts 20:7–12 | 3 | 0 | 3 |
| Judges 17–18 | 12 | 1 | 11 |
| Judges 9 | 17 | 1 | 16 |
| 2 Kings 11 | 7 | 0 | 7 |
| Acts 23:12–35 | 5 | 1 | 4 |
| 2 Samuel 21:15–22 | 1 | 0 | 1 |
| Acts 19:11–20 | 3 | 1 | 2 |
| 1 Kings 13 | 18 | 0 | 18 |

