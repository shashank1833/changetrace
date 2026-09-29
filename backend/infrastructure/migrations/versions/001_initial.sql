CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Runtime SQLAlchemy models create the same MVP schema for local setup. Production
-- migration runners should apply this version before starting API/worker processes.
CREATE TABLE IF NOT EXISTS organizations (
  id varchar(36) PRIMARY KEY, name varchar(200) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS users (
  id varchar(36) PRIMARY KEY, organization_id varchar(36) NOT NULL REFERENCES organizations(id),
  github_user_id varchar(100) UNIQUE, email varchar(320) NOT NULL, role varchar(30) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS repositories (
  id varchar(36) PRIMARY KEY, organization_id varchar(36) NOT NULL REFERENCES organizations(id),
  name varchar(200) NOT NULL, source_path text, github_url text, default_branch varchar(200) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_repositories_org ON repositories(organization_id);
CREATE TABLE IF NOT EXISTS repository_snapshots (
  id varchar(80) PRIMARY KEY, repository_id varchar(36) NOT NULL REFERENCES repositories(id),
  commit_sha varchar(64) NOT NULL, version varchar(30) NOT NULL, status varchar(30) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS change_requests (
  id varchar(36) PRIMARY KEY, organization_id varchar(36) NOT NULL REFERENCES organizations(id),
  repository_id varchar(36) NOT NULL REFERENCES repositories(id), description text NOT NULL,
  status varchar(30) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS analysis_jobs (
  id varchar(36) PRIMARY KEY, organization_id varchar(36) NOT NULL REFERENCES organizations(id),
  change_request_id varchar(36) NOT NULL REFERENCES change_requests(id), status varchar(40) NOT NULL,
  progress varchar(3) NOT NULL DEFAULT '0', analysis_id varchar(36), error text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_analysis_jobs_org_status ON analysis_jobs(organization_id, status);
CREATE TABLE IF NOT EXISTS analysis_runs (
  id varchar(36) PRIMARY KEY, organization_id varchar(36) NOT NULL REFERENCES organizations(id),
  change_request_id varchar(36) NOT NULL REFERENCES change_requests(id), snapshot_id varchar(80) NOT NULL,
  commit_sha varchar(64) NOT NULL, analyzer_version varchar(30) NOT NULL, model_version varchar(100) NOT NULL,
  result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS evidence (
  id varchar(80) PRIMARY KEY, repository_snapshot_id varchar(80) NOT NULL, type varchar(40) NOT NULL,
  file text NOT NULL, line_start varchar(10) NOT NULL, line_end varchar(10) NOT NULL,
  content_hash varchar(64) NOT NULL, payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS analysis_artifacts (
  id varchar(80) PRIMARY KEY, analysis_id varchar(36) NOT NULL REFERENCES analysis_runs(id) ON DELETE CASCADE,
  repository_snapshot_id varchar(80) NOT NULL, kind varchar(40) NOT NULL, severity varchar(20), confidence varchar(20),
  content_hash varchar(64), payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_artifacts_analysis_kind ON analysis_artifacts(analysis_id, kind);
CREATE TABLE IF NOT EXISTS audit_logs (
  id varchar(36) PRIMARY KEY, organization_id varchar(36) NOT NULL, actor_id varchar(36) NOT NULL,
  action varchar(100) NOT NULL, resource_type varchar(100) NOT NULL, resource_id varchar(80) NOT NULL,
  metadata_json jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_logs_org_created ON audit_logs(organization_id, created_at DESC);
