#!/usr/bin/env bash
# Run with "preview" to check paths, or "prepare" to make local commits.
set -eu
set -o pipefail
mode=${1:-preview}
case "$mode" in preview|prepare) ;; *) echo "Usage: bash $0 [preview|prepare]" >&2; exit 2 ;; esac

qa_root=${QA_REPO:-"$HOME/bible translation/ETEN-Bible-translation-project"}
bot_root=${PILOT_REPO:-"$HOME/whatsapp-bot/eten-whatsapp-bot"}
qa_base=39be4e47f4e03064c429ceeb1c172e7d31e3be5e
bot_base=a2b10b19ebb6314336037b4524b51825506b34f5
branch=codex/sol-pilot-release
fail() { echo "$*" >&2; exit 1; }

check_repo() {
    git -C "$1" cat-file -e "$2^{commit}" || fail "Missing base commit in $1"
    [ "$(git -C "$1" rev-parse HEAD)" = "$2" ] || fail "The source checkout has moved since the file list was prepared: $1"
    if [ "$mode" = prepare ] && git -C "$1" show-ref --verify --quiet "refs/heads/$branch"; then
        fail "The branch $branch already exists in $1. Inspect it before continuing."
    fi
}

# Each path is a named source file. Copy its current contents to the clean
# worktree and stage it there; the original checkout and its index stay intact.
number=0
commit_files() {
    local message="$1" file
    shift
    number=$((number+1))
    printf '\n%02d  %s\n' "$number" "$message"
    for file in "$@"; do
        [ -f "$file" ] && [ ! -L "$file" ] || fail "Missing file: $PWD/$file"
    done
    if [ "$mode" = preview ]; then
        printf '    %s\n' "$@"
        return
    fi
    for file in "$@"; do
        mkdir -p "$work/$(dirname "$file")"
        cp -p "$file" "$work/$file"
    done
    git -C "$work" add -- "$@"
    git -C "$work" commit -m "$message"
}

check_repo "$qa_root" "$qa_base"
check_repo "$bot_root" "$bot_base"
if [ "$mode" = prepare ]; then
    trees=$(mktemp -d "${TMPDIR:-/tmp}/eten-sol-worktrees.XXXXXXXX")
    printf 'Release worktrees: %s\n' "$trees"
    git -C "$qa_root" worktree add -b "$branch" "$trees/qa" "$qa_base"
    git -C "$bot_root" worktree add -b "$branch" "$trees/pilot" "$bot_base"
    work="$trees/qa/v3/combo"
fi

cd "$qa_root/v3/combo"
q=qa_generation
commit_files 'feat(qa): verify prepared and generated questions against their exact verse windows' \
    "$q"/services/{qa_evidence,answerability,prepared_review,wh_type,hard_qa_generation,hard_qa_recovery,paired_generation,staged_generation,scored_generation}.py \
    "$q"/prompts/{qa,hard_qa,hard_qa_stages,scored_qa}.py \
    "$q"/scripts/{recover_hard,rewrite_anchors}.py \
    "$q"/tests/{test_answerability,test_scored_generation,test_staged_generation}.py \
    "$q/docs/supporting_evidence.md"
commit_files 'feat(mcq): check question clarity, answer fidelity, and distractor plausibility' \
    "$q"/services/{audit_inputs,mcq_complexity,mcq_target,window_mcq,mcq_conversion}.py \
    "$q"/{config,pipeline}.py "$q/evaluation/evaluator.py" \
    "$q"/scripts/{generate_hard,run_dataset_pipeline,shorten_only}.py \
    "$q"/tests/{test_qa_evidence,test_prepared_review,test_window_mcq,test_prepared_shorten,test_remove_difficult,test_route_mcq}.py \
    "$q/docs/hard_qa_generation.md"

cd "$bot_root"
if [ "$mode" = prepare ]; then work="$trees/pilot"; fi
data=evaluation/datasets
pipe=evaluation/scripts/pipeline
scripts=evaluation/scripts
tests=evaluation/tests
reports=evaluation/reports
shared=packages/eten-shared/eten_shared
mcq="$scripts/mcq"
pilot=platform/frontends/pilot
api=platform/backend/pilot
campaign="$scripts/campaigns/current"
bank="$data/qa/reviewed122_sol"

commit_files 'feat(qa): translate and verify the 122 reviewed questions in Simplified Chinese' \
    "$pipe"/{translate_reviewed122_zh,verify_reviewed122_zh,report_reviewed122_zh}.py \
    "$data/qa/reviewed122"/{english,zh,clean_zh_verses,pilot_review}.json "$tests/test_reviewed122_model_translation.py"
commit_files 'feat(passages): build and validate the Sol defect ladder across six doses' \
    "$pipe"/{compare_clean_passages,check_clean_passage_questions,prepare_clean_passage_conditions,verify_clean_passage_release,build_clean_passage_ladder}.py \
    "$scripts/scoring/current/translation_quality.py" \
    "$scripts"/variants/current/{create_every_sentence_grammar,create_grammar_variants}.py \
    "$data"/passages/tier1_zh_sol_v1{,_defect_ladder}_2026-11-09/{manifest,t1_*}.json \
    "$tests"/{test_clean_passage_comparison,test_clean_passage_ladder,test_grammar_variants}.py
blind="$data/blinded/tier1_sol_reviewed122_v1"
commit_files 'feat(eval): compare comprehension with original names, pseudonyms, and conflicting details' \
    "$pipe/blind_reviewed122.py" "$scripts"/pseudonyms/current/{pseudonymize_english_source,reconcile_qa_aliases}.py \
    "$scripts"/analysis/current/{check_blinding_comprehension,check_blinding_substitutions,check_chinese_conflicting_details}.py \
    "$data/pseudonym_remap/name_map_tier1_sol_reviewed122.json" "$tests/test_reviewed122_blinding.py" \
    "$blind/manifest.json" "$blind/audit/choices.json" "$blind"/passages/t1_*.json "$blind"/qa/{english,zh,pilot_review}.json \
    "$reports"/{blinded_comprehension,blinding_substitutions,chinese_conflicting_details}_2026-11-09/comparison.md
commit_files 'feat(mcq): flag answer-length, stem-repetition, and clause-structure clues' \
    "$mcq"/diagnostics/{audit_reviewed_mcq_targets,audit_live_option_complexity}.py "$tests/test_live_option_complexity.py" \
    "$reports/sol_clause_structure_2026-11-12/review.html" "$reports/sol_key_wording_117_2026-11-12/before_after.html"
commit_files 'feat(mcq): repair flagged questions twice and review exhausted items for retirement' \
    "$shared"/{manual_wording,mcq_retirement}.py "$bank/manual_wording.json" \
    "$mcq"/preparation/{relevance_chain,rewrite_distractors,sol_distractors}.py "$tests/test_sol_distractor_repair.py" \
    "$reports/sol_distractors_held12_repair1_2026-11-11/before_after.html" \
    "$reports/sol_distractors_judges9_repair2_2026-11-11/publication.json"
commit_files 'feat(qa): record manual wording and release 48 prepared and 66 from-scratch questions' \
    "$bank"/{english,zh,choice_release,pilot_review}.json \
    "$reports/sol_option_provenance"/{marked_questions.md,trace.html,trace.json} \
    "$reports/sol_pilot_readiness_2026-11-12"/{publication.md,review.html,dispositions.json} \
    "$reports/sol_readiness24_regeneration_2026-11-12"/{review.html,dispositions.json}
commit_files 'feat(pilot): import versioned Sol questions and preserve wording already shown to readers' \
    human_pilot/{pilot_import_reviewed122,review_pilot_stems}.py human_pilot/tests/test_stem_grounding.py \
    "$shared"/{experiment_plan,database}.py "$shared"/domain/{assignments,qa_eligibility}.py \
    platform/backend/admin/services/{participant_assignment_service,test_participants_service}.py \
    supabase/migrations/experiment_windows_question_set_groups.sql deploy/{vm-files.txt,README.md}
commit_files 'feat(pilot): show verse changes and manual wording labels in test previews' \
    "$api/service.py" "$pilot/frontend/app.js" "$pilot/styles.css" "$pilot/index.html" \
    platform/tests/test_pilot_service.py Dockerfile platform/Dockerfile
commit_files 'feat(pilot): let readers revisit and edit earlier questionnaire pages' \
    "$shared/pilot_questionnaire.py" "$api"/{questionnaire,routes}.py "$pilot/frontend/questionnaire.js" \
    platform/tests/test_pilot_questionnaire.py "$pilot/README.md"
commit_files 'feat(pilot): enable the 66-question from-scratch bank for regular study plans' \
    "$shared/question_discovery/experiment_selection.py"
commit_files 'feat(pilot): balance Latin-square rotations across enrollment batches at 12 and 16 readers' \
    human_pilot/build_experiment_plan.py human_pilot/tests/test_reviewed122.py human_pilot/README.md
commit_files 'feat(eval): audit evidence position and draft defect doses for individual verse windows' \
    "$pipe/build_prepared_window_conditions.py" "$reports/sol_prepared_evidence_positions_2026-11-12/plan.html" \
    "$reports/sol_prepared_window_shift_audit_2026-11-12/changes.html" "$reports/sol_prepared_window_conditions_2026-11-12/conditions.html"
commit_files 'feat(eval): reproduce the slides 35–43 experiment on both Sol question sets' \
    "$campaign"/{run_sol_slide_experiment,finish_sol_grammar_max,finish_sol_slide_readers,map_sol_slide_choices,score_sol_slide_open,report_sol_slide_experiment}.py \
    evaluation/README.md
commit_files 'docs(results): report prepared and from-scratch accuracy, abstention, and open-answer scores' \
    "$reports/sol_slides35_43_2026-11-13"/{from-scratch.html,from-scratch.csv,from-scratch-figures.pdf} \
    "$reports/sol_judges9_curse_stem_2026-11-13"/{prepared.html,prepared.csv,prepared-figures.pdf,judges9-item-comparison.csv}

if [ "$mode" = prepare ]; then
    printf '\nCreated 2 QA commits and 14 pilot commits on local branches named %s.\n' "$branch"
    printf 'Review with git log and push the QA branch first. Worktrees: %s\n' "$trees"
fi
