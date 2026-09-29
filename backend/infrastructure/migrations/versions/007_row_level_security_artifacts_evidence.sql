-- 007_row_level_security_artifacts_evidence.sql: Row-Level Security for snapshots, evidence, and artifacts

ALTER TABLE repository_snapshots ENABLE ROW LEVEL SECURITY, FORCE ROW LEVEL SECURITY;
ALTER TABLE evidence ENABLE ROW LEVEL SECURITY, FORCE ROW LEVEL SECURITY;
ALTER TABLE analysis_artifacts ENABLE ROW LEVEL SECURITY, FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_snapshots') THEN
    CREATE POLICY tenant_isolation_snapshots ON repository_snapshots
      USING (EXISTS (
        SELECT 1 FROM repositories r
        WHERE r.id = repository_snapshots.repository_id
          AND r.organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
      ));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_evidence') THEN
    CREATE POLICY tenant_isolation_evidence ON evidence
      USING (EXISTS (
        SELECT 1 FROM repository_snapshots s
        JOIN repositories r ON r.id = s.repository_id
        WHERE s.id = evidence.repository_snapshot_id
          AND r.organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
      ));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_analysis_artifacts') THEN
    CREATE POLICY tenant_isolation_analysis_artifacts ON analysis_artifacts
      USING (EXISTS (
        SELECT 1 FROM analysis_runs a
        WHERE a.id = analysis_artifacts.analysis_id
          AND a.organization_id = NULLIF(current_setting('app.current_organization_id', true), '')
      ));
  END IF;
END $$;
