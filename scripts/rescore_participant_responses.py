#!/usr/bin/env python3
"""
Re-score existing participant_responses using per-language keyword matching.

Usage (from repo root):
  python scripts/rescore_participant_responses.py RESPONSE_ID ...
  python scripts/rescore_participant_responses.py --qa-item-id UUID
  python scripts/rescore_participant_responses.py --participant "test user 2"
  python scripts/rescore_participant_responses.py --commit RESPONSE_ID

For audio rows, ensure transcript_text is populated (Whisper STT on ingest or manual edit).
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app import create_app
from app.database import get_session_factory
from app.models import Participant, ParticipantResponse, ReviewStatus
from app.services.chatbot_workflow import (
    audio_answer_lacks_usable_transcript,
    has_usable_text_for_keyword_scoring,
    score_text_response_for_participant,
)
from app.services.mcq_service import (
    choice_response_is_correct,
    choice_response_letter,
    is_choice_scored_item,
)
from app.services.transcription_service import (
    is_transcription_enabled,
    transcribe_whatsapp_audio,
)


def load_responses(db, response_ids, qa_item_id, participant_query):
    statement = (
        select(ParticipantResponse)
        .options(
            selectinload(ParticipantResponse.participant),
            selectinload(ParticipantResponse.qa_item),
        )
        .order_by(ParticipantResponse.received_at.desc())
    )

    if response_ids:
        statement = statement.where(ParticipantResponse.id.in_(response_ids))
    if qa_item_id:
        statement = statement.where(ParticipantResponse.qa_item_id == qa_item_id)
    if participant_query:
        statement = statement.join(Participant).where(
            or_(
                Participant.display_name.ilike(f"%{participant_query}%"),
                Participant.wa_id.ilike(f"%{participant_query}%"),
            )
        )

    return db.scalars(statement).all()


def score_response_row(db, response, retranscribe: bool):
    participant = response.participant
    qa_item = response.qa_item
    if not participant or not qa_item:
        return {"error": "Missing participant or qa_item relation"}

    response_type = response.response_type or ""
    transcript_text = response.transcript_text
    response_text = response.response_text
    media_url = response.media_url
    analysis_text = transcript_text or response_text or ""
    choice_correct = None

    if (
        retranscribe
        and response_type == "audio"
        and response.media_url
        and is_transcription_enabled()
    ):
        language_hint = (participant.target_language or "eng").strip() or "eng"
        transcription = transcribe_whatsapp_audio(
            media_id=response.media_id,
            mime_type=None,
            sha256=None,
            media_url=response.media_url,
            language_hint=language_hint,
        )
        transcript_text = transcription.text
        analysis_text = transcript_text or response_text or ""

    unusable_audio_transcript = audio_answer_lacks_usable_transcript(
        transcript_text,
        response_type,
    )

    if is_choice_scored_item(qa_item):
        normalized_text = None
        correctness_score = None
        matched_keywords = []
        missing_keywords = []
        keyword_scored = False
        needs_expert_review = False
        flag_reason = None
        choice_correct = choice_response_is_correct(qa_item, analysis_text)
    elif unusable_audio_transcript:
        normalized_text = analysis_text
        correctness_score = None
        matched_keywords = []
        missing_keywords = []
        needs_expert_review = True
        if not (transcript_text or "").strip():
            flag_reason = "Pending expert review: no transcript for audio answer."
        else:
            flag_reason = "Pending expert review: placeholder transcript (not keyword-scored)."
        keyword_scored = False
    elif has_usable_text_for_keyword_scoring(
        transcript_text, response_text, response_type
    ):
        (
            normalized_text,
            correctness_score,
            matched_keywords,
            missing_keywords,
            needs_expert_review,
            flag_reason,
        ) = score_text_response_for_participant(db, qa_item, participant, analysis_text)
        keyword_scored = True
    else:
        (
            normalized_text,
            correctness_score,
            matched_keywords,
            missing_keywords,
            needs_expert_review,
            flag_reason,
        ) = score_text_response_for_participant(db, qa_item, participant, analysis_text)
        keyword_scored = bool((response_text or "").strip())

    if is_choice_scored_item(qa_item):
        is_correct = "yes (auto)" if choice_correct else "no (auto)"
        review_status = ReviewStatus.AUTO.value
    elif needs_expert_review:
        is_correct = "pending"
        review_status = ReviewStatus.PENDING.value
    elif correctness_score is not None and correctness_score < 1.0:
        is_correct = "no (auto)"
        review_status = ReviewStatus.AUTO.value
    else:
        is_correct = "yes (auto)"
        review_status = ReviewStatus.AUTO.value

    result = {
        "normalized_text": normalized_text,
        "correctness_score": correctness_score,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "is_correct": is_correct,
        "review_status": review_status,
        "flag_reason": flag_reason,
        "keyword_scored": keyword_scored,
        "transcript_text": transcript_text,
        "target_language": (participant.target_language or "eng").strip() or "eng",
    }
    if is_choice_scored_item(qa_item):
        result["response_text"] = choice_response_letter(qa_item, analysis_text)
    return result


def apply_scores_to_response(response, scores):
    if "response_text" in scores:
        response.response_text = scores.get("response_text")
    if scores.get("transcript_text") is not None:
        response.transcript_text = scores.get("transcript_text")
    response.normalized_text = scores.get("normalized_text")
    response.correctness_score = scores.get("correctness_score")
    response.matched_keywords = scores.get("matched_keywords") or []
    response.missing_keywords = scores.get("missing_keywords") or []
    response.is_correct = scores.get("is_correct", "pending")
    response.review_status = scores.get("review_status", ReviewStatus.PENDING.value)
    response.flag_reason = scores.get("flag_reason")


def print_result(response, scores):
    participant = response.participant
    qa_item = response.qa_item
    label = participant.display_name if participant else response.participant_id
    passage = (qa_item.passage_reference or qa_item.passage_id) if qa_item else "?"

    print("-" * 72)
    print(f"Response ID:     {response.id}")
    print(f"Participant:     {label}")
    print(f"Passage:         {passage}")
    print(f"Type:            {response.response_type}")
    if scores.get("target_language"):
        print(f"target_language: {scores['target_language']}")
    print(f"media_url:       {response.media_url or '—'}")
    if scores.get("error"):
        print(f"ERROR:           {scores['error']}")
        return

    print(f"Keyword scored:  {scores.get('keyword_scored')}")
    print(f"correctness_score: {scores.get('correctness_score')}")
    print(f"is_correct:      {scores.get('is_correct')}")
    print(f"matched_keywords: {scores.get('matched_keywords')}")
    print(f"missing_keywords: {scores.get('missing_keywords')}")
    print(f"flag_reason:     {scores.get('flag_reason') or '—'}")


def main():
    parser = argparse.ArgumentParser(
        description="Re-score participant_responses with per-language keywords."
    )
    parser.add_argument(
        "response_ids",
        nargs="*",
        help="One or more participant_responses.id values",
    )
    parser.add_argument("--qa-item-id", help="Score all responses for this QA item")
    parser.add_argument(
        "--participant",
        help="Filter by participant display_name or wa_id (substring match)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Write scores back to the database",
    )
    parser.add_argument(
        "--retranscribe",
        action="store_true",
        help="Re-run Whisper STT on audio before keyword scoring",
    )
    args = parser.parse_args()

    if not args.response_ids and not args.qa_item_id and not args.participant:
        parser.error("Provide response ID(s), --qa-item-id, or --participant")

    app = create_app()
    with app.app_context():
        factory = get_session_factory()
        with factory() as db:
            responses = load_responses(
                db,
                args.response_ids,
                args.qa_item_id,
                args.participant,
            )
            if not responses:
                print("No matching responses found.")
                sys.exit(1)

            print(f"Scoring {len(responses)} response(s)...\n")

            for response in responses:
                scores = score_response_row(db, response, args.retranscribe)
                print_result(response, scores)
                if not scores.get("error") and args.commit:
                    apply_scores_to_response(response, scores)

            if args.commit:
                db.commit()
                print("\nCommitted updates to the database.")
            else:
                print("\nDry run only (no DB changes). Re-run with --commit to save.")


if __name__ == "__main__":
    main()
