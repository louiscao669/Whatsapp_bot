alter table passage_translations
    drop constraint if exists uq_passage_translations_language_name;

drop index if exists uq_passage_translations_unnamed_language;
