-- 006_row_level_security_extended.sql: Extended RLS for users, installations, and deliveries

ALTER TABLE users ENABLE ROW LEVEL SECURITY, FORCE ROW LEVEL SECURITY;
ALTER TABLE github_installations ENABLE ROW LEVEL SECURITY, FORCE ROW LEVEL SECURITY;
ALTER TABLE github_webhook_deliveries ENABLE ROW LEVEL SECURITY, FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_users') THEN
    CREATE POLICY tenant_isolation_users ON users
      USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), ''));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_github_installations') THEN
    CREATE POLICY tenant_isolation_github_installations ON github_installations
      USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), ''));
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'tenant_isolation_github_deliveries') THEN
    CREATE POLICY tenant_isolation_github_deliveries ON github_webhook_deliveries
      USING (organization_id IS NULL OR organization_id = NULLIF(current_setting('app.current_organization_id', true), ''));
  END IF;
END $$;
