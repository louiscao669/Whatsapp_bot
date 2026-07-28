CREATE TABLE IF NOT EXISTS assignment_deliveries (
    id varchar(36) PRIMARY KEY,
    participant_id varchar(36) NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    assignment_id varchar(36) NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    provider varchar(32) NOT NULL,
    provider_message_id varchar(128) NOT NULL,
    delivered_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_assignment_delivery_message
        UNIQUE(participant_id, provider, provider_message_id)
);

CREATE TABLE IF NOT EXISTS answer_receipts (
    id varchar(36) PRIMARY KEY,
    participant_id varchar(36) NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    assignment_id varchar(36) NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    qa_item_id varchar(36) NOT NULL REFERENCES qa_items(id) ON DELETE CASCADE,
    provider varchar(32) NOT NULL,
    provider_update_id varchar(128) NOT NULL,
    provider_question_message_id varchar(128),
    response_type varchar(32) NOT NULL,
    raw_answer text NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'pending',
    response_id varchar(36) REFERENCES participant_responses(id) ON DELETE SET NULL,
    failure_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    CONSTRAINT uq_answer_receipts_assignment UNIQUE(assignment_id),
    CONSTRAINT uq_answer_receipts_provider_update
        UNIQUE(participant_id, provider, provider_update_id)
);

CREATE INDEX IF NOT EXISTS ix_assignment_deliveries_participant_id
ON assignment_deliveries(participant_id);
CREATE INDEX IF NOT EXISTS ix_assignment_deliveries_assignment_id
ON assignment_deliveries(assignment_id);
CREATE INDEX IF NOT EXISTS ix_answer_receipts_status ON answer_receipts(status);
CREATE INDEX IF NOT EXISTS ix_answer_receipts_participant_id ON answer_receipts(participant_id);
CREATE INDEX IF NOT EXISTS ix_answer_receipts_assignment_id ON answer_receipts(assignment_id);
