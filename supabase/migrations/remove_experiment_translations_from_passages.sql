-- Experiment variants now own their verses in experiment_passage_verses.
-- Remove the obsolete Chinese copies from the regular passage catalogue.
delete from passage_translations
where language = 'zh'
  and name in (
    'Clean anchor',
    'Omission 10%',
    'Omission 20%',
    'Omission 30%',
    'Mistranslation 20%',
    'Grammar 30%',
    'Word-by-word (Google)'
  );
