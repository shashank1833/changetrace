ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS proposed_diff text;
ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS base_ref varchar(200);
ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS target_ref varchar(200);

CREATE TABLE IF NOT EXISTS finding_feedback (
  id varchar(36) PRIMARY KEY,
  organization_id varchar(36) NOT NULL REFERENCES organizations(id),
  analysis_id varchar(36) NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
  finding_id varchar(80) NOT NULL,
  user_id varchar(36) NOT NULL,
  decision varchar(20) NOT NULL CHECK (decision IN ('CONFIRM', 'REJECT', 'NOT_RELEVANT')),
  reason text,
  analyzer_version varchar(30) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_feedback_org_analysis ON finding_feedback(organization_id, analysis_id);
CREATE INDEX IF NOT EXISTS ix_feedback_finding ON finding_feedback(finding_id);
