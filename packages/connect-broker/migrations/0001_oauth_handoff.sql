CREATE TABLE oauth_sessions (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider IN ('slack', 'linkedin')),
  local_callback TEXT NOT NULL,
  local_state TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  redirect_uri TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  used_at INTEGER
);

CREATE INDEX oauth_sessions_expiry_idx ON oauth_sessions (expires_at);

CREATE TABLE oauth_handoffs (
  code_hash TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider IN ('slack', 'linkedin')),
  local_state TEXT NOT NULL,
  code_challenge TEXT NOT NULL,
  ciphertext TEXT NOT NULL,
  iv TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER
);

CREATE INDEX oauth_handoffs_expiry_idx ON oauth_handoffs (expires_at);

CREATE TABLE slack_installations (
  team_id TEXT PRIMARY KEY,
  relay_hash TEXT NOT NULL UNIQUE,
  approval_channel_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE slack_actions (
  id TEXT PRIMARY KEY,
  team_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  lease_hash TEXT,
  lease_until INTEGER,
  consumed_at INTEGER,
  FOREIGN KEY (team_id) REFERENCES slack_installations(team_id) ON DELETE CASCADE
);

CREATE INDEX slack_actions_poll_idx
  ON slack_actions (team_id, consumed_at, lease_until, created_at);
