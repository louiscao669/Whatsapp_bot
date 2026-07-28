alter table qa_items
    add column if not exists form_group_id varchar(128),
    add column if not exists automatic_form varchar(16);

create index if not exists ix_qa_items_form_group_id on qa_items (form_group_id);
