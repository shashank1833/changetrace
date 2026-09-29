CREATE TABLE IF NOT EXISTS web_sessions (
  id varchar(36) PRIMARY KEY,
  user_id varchar(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash varchar(64) NOT NULL UNIQUE,
  expires_at bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_web_sessions_user_id ON web_sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_web_sessions_token_hash ON web_sessions(token_hash);
CREATE INDEX IF NOT EXISTS ix_web_sessions_expires_at ON web_sessions(expires_at);
