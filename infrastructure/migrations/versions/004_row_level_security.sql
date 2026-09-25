-- Enable Row-Level Security for defense-in-depth multi-tenant isolation

ALTER TABLE repositories ENABLE ROW LEVEL SECURITY;
ALTER TABLE change_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE finding_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Create tenant isolation policies based on the session variable app.current_organization_id
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_repositories') THEN
    CREATE POLICY tenant_isolation_repositories ON repositories
      USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), ''));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_changes') THEN
    CREATE POLICY tenant_isolation_changes ON change_requests
      USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), ''));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_jobs') THEN
    CREATE POLICY tenant_isolation_jobs ON analysis_jobs
      USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), ''));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_runs') THEN
    CREATE POLICY tenant_isolation_runs ON analysis_runs
      USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), ''));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_feedback') THEN
    CREATE POLICY tenant_isolation_feedback ON finding_feedback
      USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), ''));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_audit') THEN
    CREATE POLICY tenant_isolation_audit ON audit_logs
      USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), ''));
  END IF;
END $$;
