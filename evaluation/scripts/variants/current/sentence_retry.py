"""Recover previously approved sentence edits and failure feedback without API calls."""

from pathlib import Path

from evaluation.scripts.variants.current import create_grammar_variants as grammar


def load_retry_seed(text: str, snapshot: Path, passage: str) -> tuple[dict, dict]:
    bank_dir = snapshot / passage / "grammar/_grammar_bank"
    state = grammar.read_json_object(snapshot / "run_state.json")
    config = state["configuration"]
    records = {}
    for name, field in (("proposals.json", "proposals"), ("judgments.json", "judgments"),
                        ("meaning_judgments.json", "reviews")):
        path = bank_dir / name
        records[field] = grammar.read_json_object(path)[field] if path.exists() else {}
    banks = [grammar.read_json_object(path) for path in sorted(bank_dir.glob("bank_*.json"))]
    banks = [bank for bank in banks if bank.get("source_sha256") == grammar.json_digest(text)
             and bank.get("spec", {}).get("unit_mode") == "sentence"]
    if len(banks) > 1:
        review_path = bank_dir.parent / "sentence_review.json"
        if review_path.exists():
            reports = grammar.read_json_object(review_path)["files"]
            ids = {r["bank_id"] for r in reports.values()
                   if r["source_sha256"] == grammar.json_digest(text)}
            banks = [bank for bank in banks if bank["bank_id"] in ids]
        if len(banks) != 1:
            raise grammar.GrammarError("Retry source has ambiguous sentence banks.")
    saved = banks[0] if banks else None
    if saved:
        grammar.validate_grammar_bank(text, saved)
        spec = saved["spec"]
    else:
        # Interrupted runs may have durable approvals but no final bank yet.
        # Only the known old strict sentence policy is reconstructed here.
        proposer = {"model": config["generator_model"],
                    "prompt_sha256": grammar.json_digest(grammar.PROPOSAL_PROMPT),
                    "schema_sha256": grammar.json_digest(grammar.PROPOSAL_SCHEMA)}
        judge = {"model": config["judge_model"],
                 "prompt_sha256": grammar.json_digest(grammar.JUDGE_PROMPT),
                 "schema_sha256": grammar.json_digest(grammar.JUDGE_SCHEMA)}
        meaning = grammar.GrammarMeaningCache(bank_dir, model=config["judge_model"], offline=True)
        spec = {
            "version": grammar.BANK_VERSION, "source_sha256": grammar.json_digest(text),
            "seed": config["seed"] + grammar.seed_offset(passage),
            "edit_style": grammar.EDIT_STYLE, "max_candidates": config["candidates"],
            "rearrangement_policy": grammar.REARRANGEMENT_POLICY,
            "proposer": proposer, "proposal_batch_size": config["batch_size"], "judge": judge,
            "meaning_policy": grammar.MEANING_POLICY, "meaning_judge": meaning.identity,
            "protected_pattern": grammar.EXTRA_PROTECTED.pattern if grammar.EXTRA_PROTECTED else None,
            "unit_mode": "sentence", "segmentation_policy": "sentence_punctuation_verse_fragments_v1",
        }
    units = grammar.passage_units(text, unit_mode="sentence")
    offsets, offset = [], 0
    for unit in units:
        offsets.append(offset)
        offset += len(unit["text"])
    entries = list(saved["entries"]) if saved else []
    accepted = {entry["unit_index"] for entry in entries}
    attempts = {}
    matched = 0
    for proposal_id, record in records["proposals"].items():
        request = record["request"]
        if request.get("original_passage") != text or record["generator"] != spec["proposer"]:
            continue
        if proposal_id != grammar.json_digest({"generator": spec["proposer"], "request": request}):
            raise grammar.GrammarError("Retry source proposal has an invalid cache identity.")
        response = grammar.validate_proposal_response(record["response"], request)
        groups = {group["unit_index"]: group["candidates"] for group in response["clauses"]}
        matched += 1
        for clause in request["clauses"]:
            index = clause["unit_index"]
            if (not 0 <= index < len(units) or clause["original_clause"] != units[index]["text"]
                    or clause["clause_start"] != offsets[index]):
                raise grammar.GrammarError("Retry source sentence does not match the clean source.")
            if index in accepted:
                continue
            feedback = attempts.setdefault(index, [])
            if not groups[index]:
                feedback.append({"round": request.get("retry_round", 0), "outcome": "no_candidate"})
            for proposal in groups[index]:
                candidate = proposal["edited_clause"]
                attempt = {"round": request.get("retry_round", 0), "edited_clause": candidate}
                if not grammar.valid_structural_candidate(clause["original_clause"], candidate,
                                                          [grammar.LLM_OPERATION]):
                    feedback.append({**attempt, "outcome": "hard_check_rejected"})
                    continue
                review_request = {"original_passage": text, "clause_start": offsets[index],
                                  "original_clause": clause["original_clause"], "edited_clause": candidate}
                judgment_id = grammar.json_digest({"judge": spec["judge"], "request": review_request})
                judged = records["judgments"].get(judgment_id)
                if judged is None:
                    feedback.append({**attempt, "outcome": "review_interrupted"})
                    continue
                if judged["request"] != review_request or judged["judge"] != spec["judge"]:
                    raise grammar.GrammarError("Retry source grammar review identity mismatch.")
                judgment = judged["judgment"]
                if not grammar.judgment_accepts(judgment, candidate):
                    feedback.append({**attempt, "outcome": "grammar_rejected", "feedback": judgment})
                    continue
                meaning_id = grammar.json_digest({"reviewer": spec["meaning_judge"],
                                                  "request": review_request})
                reviewed = records["reviews"].get(meaning_id)
                if reviewed is None:
                    feedback.append({**attempt, "outcome": "meaning_review_interrupted"})
                    continue
                if reviewed["request"] != review_request or reviewed["reviewer"] != spec["meaning_judge"]:
                    raise grammar.GrammarError("Retry source meaning review identity mismatch.")
                meaning_review = reviewed["review"]
                if not grammar.meaning_review_accepts(meaning_review, candidate):
                    feedback.append({**attempt, "outcome": "meaning_rejected",
                                     "feedback": meaning_review["judgment"]})
                    continue
                if saved:
                    raise grammar.GrammarError("Retry source has an approval missing from its final bank.")
                entries.append({
                    "unit_index": index, "verse": units[index]["verse"],
                    "content_chars": units[index]["content_chars"], "original_text": clause["original_clause"],
                    "corrupted_text": candidate, "operations": [grammar.LLM_OPERATION],
                    "proposal_id": proposal_id, "proposal": proposal,
                    "judgment_id": judgment_id, "judgment": judgment,
                    "meaning_review_id": meaning_id, "meaning_review": meaning_review,
                })
                accepted.add(index)
                break
    if not saved and not matched:
        raise grammar.GrammarError("No compatible sentence proposals found in retry source.")
    if not saved:
        total = sum(unit["content_chars"] for unit in units if unit["affectable"])
        affected = sum(entry["content_chars"] for entry in entries)
        saved = {"schema_version": grammar.BANK_VERSION, "bank_id": grammar.json_digest(spec),
                 "spec": spec, "source_sha256": grammar.json_digest(text), "max_rate": 1.0,
                 "total_content_chars": total, "affected_content_chars": affected,
                 "actual_affected_rate": affected / total if total else 0,
                 "target_met": affected == total, "exhausted": affected < total,
                 "entries": entries, "recovered_from_cached_reviews": True}
        grammar.validate_grammar_bank(text, saved)
    return saved, {index: history for index, history in attempts.items() if index not in accepted}
