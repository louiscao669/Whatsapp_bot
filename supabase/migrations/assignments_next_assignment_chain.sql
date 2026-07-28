ALTER TABLE assignments
ADD COLUMN IF NOT EXISTS next_assignment_id varchar(36)
REFERENCES assignments(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_assignments_next_assignment_id
ON assignments(next_assignment_id);

WITH ordered AS (
    SELECT id,
           lead(id) OVER (
               PARTITION BY participant_id ORDER BY assigned_at, id
           ) AS next_id
    FROM assignments
)
UPDATE assignments AS assignment
SET next_assignment_id = ordered.next_id
FROM ordered
WHERE assignment.id = ordered.id
  AND assignment.next_assignment_id IS NULL
  AND ordered.next_id IS NOT NULL;
