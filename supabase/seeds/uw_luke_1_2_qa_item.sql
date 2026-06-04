-- UW translation question: Luke 1:2 (content_id 174314)
-- Source: uw-translation-questions-eng-luke.json

insert into qa_items (
  passage_id,
  passage_reference,
  passage_text,
  audio_url,
  question_text,
  expected_answer,
  required_keywords,
  optional_keywords,
  min_responses_required,
  active,
  review_priority
)
values (
  'uw-174314',
  'Luke 1:2',
  'even as those who from the beginning were eyewitnesses and servants of the word delivered them to us,',
  null,
  'Who were the "eyewitnesses" that Luke mentions?',
  'The "eyewitnesses" were the ones who were with the apostles from the beginning of Jesus'' ministry.',
  '["eyewitnesses", "apostles", "beginning", "ministry", "jesus"]'::jsonb,
  '[]'::jsonb,
  3,
  true,
  10
);

-- To replace an older test row:
-- delete from qa_items where passage_id in ('luke-1-1', 'uw-174314');

select id, passage_id, passage_reference, question_text, active
from qa_items
where passage_id = 'uw-174314'
order by created_at desc;
