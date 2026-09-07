ALTER TABLE oauth_sessions RENAME TO oauth_sessions_legacy;

CREATE TABLE oauth_sessions (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider IN ('slack', 'linkedin', 'gmail')),
  local_callback TEXT NOT NULL,
  local_state TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER
);

INSERT INTO oauth_sessions SELECT * FROM oauth_sessions_legacy;
DROP TABLE oauth_sessions_legacy;
CREATE INDEX oauth_sessions_expiry_idx ON oauth_sessions (expires_at);

ALTER TABLE oauth_handoffs RENAME TO oauth_handoffs_legacy;

CREATE TABLE oauth_handoffs (
  code_hash TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider IN ('slack', 'linkedin', 'gmail')),
  local_state TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  ciphertext TEXT NOT NULL,
  iv TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER
);

INSERT INTO oauth_handoffs SELECT * FROM oauth_handoffs_legacy;
DROP TABLE oauth_handoffs_legacy;
CREATE INDEX oauth_handoffs_expiry_idx ON oauth_handoffs (expires_at);
