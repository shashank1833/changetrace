-- 005_github_tenant_and_deliveries.sql: Multi-tenant GitHub App installation mapping and webhook delivery deduplication

ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS github_metadata jsonb;

CREATE TABLE IF NOT EXISTS github_installations (
    installation_id BIGINT PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    account_login VARCHAR(200) NOT NULL,
    account_id BIGINT,
    target_type VARCHAR(50) NOT NULL DEFAULT 'Organization',
    permissions_json JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_github_installations_org ON github_installations(organization_id);

CREATE TABLE IF NOT EXISTS github_webhook_deliveries (
    delivery_id VARCHAR(64) PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    installation_id BIGINT,
    organization_id VARCHAR(36),
    payload_hash VARCHAR(64) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_github_webhook_deliveries_event ON github_webhook_deliveries(event_type);
CREATE INDEX IF NOT EXISTS ix_github_webhook_deliveries_inst ON github_webhook_deliveries(installation_id);
