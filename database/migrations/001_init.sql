-- =====================================================================
-- AYAKA API — Migration 001 (initial schema)
-- Powered by AYAKA Sync · Owner: OLPI STORE
-- Target: Neon PostgreSQL (PostgreSQL 15+)
-- Idempotent: safe to run multiple times.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Helper: auto-update updated_at
CREATE OR REPLACE FUNCTION ayaka_touch_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------
-- 1. users
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username           VARCHAR(32)  NOT NULL,
  full_name          VARCHAR(120) NOT NULL,
  email              VARCHAR(254) NOT NULL,
  password_hash      TEXT         NOT NULL,
  status             VARCHAR(16)  NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','suspended')),
  failed_login_count INTEGER      NOT NULL DEFAULT 0,
  locked_until       TIMESTAMPTZ,
  monthly_quota      INTEGER      NOT NULL DEFAULT 10000 CHECK (monthly_quota >= 0),
  last_login_at      TIMESTAMPTZ,
  password_changed_at TIMESTAMPTZ,
  created_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ  NOT NULL DEFAULT now(),
  CONSTRAINT users_username_format CHECK (username ~ '^[a-zA-Z0-9_]{3,32}$')
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_uq    ON users (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS users_username_uq ON users (lower(username));
CREATE INDEX IF NOT EXISTS users_created_idx ON users (created_at);
DROP TRIGGER IF EXISTS users_touch ON users;
CREATE TRIGGER users_touch BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION ayaka_touch_updated_at();

-- ---------------------------------------------------------------------
-- 7. admin_users (role stored in DB — never derived from email alone)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admin_users (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  role        VARCHAR(16) NOT NULL DEFAULT 'admin' CHECK (role IN ('admin','superadmin')),
  display_name VARCHAR(80) NOT NULL DEFAULT 'Ayaka Sync',
  created_by  VARCHAR(64) NOT NULL DEFAULT 'bootstrap',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS admin_users_touch ON admin_users;
CREATE TRIGGER admin_users_touch BEFORE UPDATE ON admin_users
  FOR EACH ROW EXECUTE FUNCTION ayaka_touch_updated_at();

-- ---------------------------------------------------------------------
-- 8. user_sessions (only SHA-256 of session token is stored)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_sessions (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash   CHAR(64) NOT NULL UNIQUE,
  csrf_token   VARCHAR(64) NOT NULL,
  remember_me  BOOLEAN NOT NULL DEFAULT false,
  ip_masked    VARCHAR(64),
  user_agent   VARCHAR(300),
  expires_at   TIMESTAMPTZ NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_sessions_user_idx ON user_sessions (user_id);
CREATE INDEX IF NOT EXISTS user_sessions_exp_idx  ON user_sessions (expires_at);

-- ---------------------------------------------------------------------
-- 2. api_keys (only HMAC-SHA256(secret, pepper) is stored)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_keys (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name             VARCHAR(80)  NOT NULL,
  description      VARCHAR(300) NOT NULL DEFAULT '',
  key_prefix       VARCHAR(24)  NOT NULL,
  key_last4        CHAR(4)      NOT NULL,
  key_hash         CHAR(64)     NOT NULL UNIQUE,
  permissions      TEXT[]       NOT NULL DEFAULT ARRAY['profile:read']::TEXT[],
  rate_limit_per_minute INTEGER NOT NULL DEFAULT 60 CHECK (rate_limit_per_minute BETWEEN 1 AND 10000),
  status           VARCHAR(16)  NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
  expires_at       TIMESTAMPTZ,
  last_used_at     TIMESTAMPTZ,
  usage_count      BIGINT       NOT NULL DEFAULT 0,
  revoked_at       TIMESTAMPTZ,
  revoked_reason   VARCHAR(120),
  rotated_from     UUID REFERENCES api_keys(id) ON DELETE SET NULL,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS api_keys_owner_idx   ON api_keys (owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS api_keys_status_idx  ON api_keys (status);
CREATE INDEX IF NOT EXISTS api_keys_created_idx ON api_keys (created_at);
DROP TRIGGER IF EXISTS api_keys_touch ON api_keys;
CREATE TRIGGER api_keys_touch BEFORE UPDATE ON api_keys
  FOR EACH ROW EXECUTE FUNCTION ayaka_touch_updated_at();

-- ---------------------------------------------------------------------
-- 3. api_request_logs (never stores raw keys, passwords or tokens)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_request_logs (
  id               BIGSERIAL PRIMARY KEY,
  request_id       VARCHAR(40) NOT NULL,
  user_id          UUID REFERENCES users(id) ON DELETE SET NULL,
  api_key_id       UUID REFERENCES api_keys(id) ON DELETE SET NULL,
  auth_type        VARCHAR(16) NOT NULL DEFAULT 'none' CHECK (auth_type IN ('none','session','api_key')),
  method           VARCHAR(8)  NOT NULL,
  endpoint         VARCHAR(200) NOT NULL,
  status_code      SMALLINT    NOT NULL,
  response_time_ms INTEGER     NOT NULL,
  ip_masked        VARCHAR(64),
  user_agent       VARCHAR(300),
  error_code       VARCHAR(48),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS req_logs_user_time_idx ON api_request_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS req_logs_time_idx      ON api_request_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS req_logs_key_idx       ON api_request_logs (api_key_id);
CREATE INDEX IF NOT EXISTS req_logs_status_idx    ON api_request_logs (status_code);
CREATE UNIQUE INDEX IF NOT EXISTS req_logs_reqid_uq ON api_request_logs (request_id);

-- ---------------------------------------------------------------------
-- 5. premium_subscriptions (scoped per API owner → no cross-tenant leaks)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS premium_subscriptions (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  email          VARCHAR(254) NOT NULL,
  plan           VARCHAR(32)  NOT NULL DEFAULT 'premium',
  status         VARCHAR(16)  NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
  activated_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
  expires_at     TIMESTAMPTZ  NOT NULL,
  revoked_at     TIMESTAMPTZ,
  revoked_by     VARCHAR(80),
  revoke_reason  VARCHAR(200),
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS premium_owner_email_uq ON premium_subscriptions (owner_id, lower(email));
CREATE INDEX IF NOT EXISTS premium_status_idx ON premium_subscriptions (status, expires_at);
DROP TRIGGER IF EXISTS premium_touch ON premium_subscriptions;
CREATE TRIGGER premium_touch BEFORE UPDATE ON premium_subscriptions
  FOR EACH ROW EXECUTE FUNCTION ayaka_touch_updated_at();

-- ---------------------------------------------------------------------
-- 4. magic_link_tokens (only SHA-256 of token stored, one-time use)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS magic_link_tokens (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  api_key_id     UUID REFERENCES api_keys(id) ON DELETE SET NULL,
  email          VARCHAR(254) NOT NULL,
  plan           VARCHAR(32)  NOT NULL DEFAULT 'premium',
  duration_days  INTEGER      NOT NULL DEFAULT 30 CHECK (duration_days BETWEEN 1 AND 365),
  token_hash     CHAR(64)     NOT NULL UNIQUE,
  expires_at     TIMESTAMPTZ  NOT NULL,
  used_at        TIMESTAMPTZ,
  email_status   VARCHAR(16)  NOT NULL DEFAULT 'pending' CHECK (email_status IN ('pending','sent','failed')),
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mlt_owner_email_idx ON magic_link_tokens (owner_id, lower(email), created_at DESC);
CREATE INDEX IF NOT EXISTS mlt_exp_idx ON magic_link_tokens (expires_at);

-- ---------------------------------------------------------------------
-- 6. premium_renewal_logs (activation / renew / revoke history)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS premium_renewal_logs (
  id              BIGSERIAL PRIMARY KEY,
  subscription_id UUID NOT NULL REFERENCES premium_subscriptions(id) ON DELETE CASCADE,
  owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  action          VARCHAR(16) NOT NULL CHECK (action IN ('activate','renew','revoke')),
  duration_days   INTEGER,
  old_expires_at  TIMESTAMPTZ,
  new_expires_at  TIMESTAMPTZ,
  actor_type      VARCHAR(16) NOT NULL CHECK (actor_type IN ('magic_link','api_key','admin','session')),
  actor_id        VARCHAR(80),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS prl_sub_idx   ON premium_renewal_logs (subscription_id, created_at DESC);
CREATE INDEX IF NOT EXISTS prl_owner_idx ON premium_renewal_logs (owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS prl_action_time_idx ON premium_renewal_logs (action, created_at);

-- ---------------------------------------------------------------------
-- 9. audit_logs
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
  id          BIGSERIAL PRIMARY KEY,
  actor_type  VARCHAR(16) NOT NULL CHECK (actor_type IN ('user','admin','api_key','system')),
  actor_id    VARCHAR(80),
  user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
  action      VARCHAR(64) NOT NULL,
  target_type VARCHAR(32),
  target_id   VARCHAR(80),
  metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
  ip_masked   VARCHAR(64),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS audit_time_idx   ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS audit_user_idx   ON audit_logs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audit_action_idx ON audit_logs (action);

-- ---------------------------------------------------------------------
-- 10. visitor_analytics (anonymous daily-rotating visitor hash)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS visitor_analytics (
  id            BIGSERIAL PRIMARY KEY,
  visitor_hash  CHAR(64)   NOT NULL,
  visit_day     DATE       NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')::date,
  path          VARCHAR(200) NOT NULL,
  referrer_host VARCHAR(120),
  page_views    INTEGER    NOT NULL DEFAULT 1,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT visitor_unique_per_day UNIQUE (visitor_hash, visit_day, path)
);
CREATE INDEX IF NOT EXISTS visitor_day_idx ON visitor_analytics (visit_day);

-- ---------------------------------------------------------------------
-- 11. system_settings (key/value JSON)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_settings (
  key         VARCHAR(64) PRIMARY KEY,
  value       JSONB NOT NULL,
  updated_by  UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS settings_touch ON system_settings;
CREATE TRIGGER settings_touch BEFORE UPDATE ON system_settings
  FOR EACH ROW EXECUTE FUNCTION ayaka_touch_updated_at();

INSERT INTO system_settings (key, value) VALUES
  ('maintenance', '{"enabled": false, "message": "AYAKA API sedang dalam pemeliharaan terjadwal.", "start_at": null, "end_at": null}'::jsonb),
  ('registration', '{"open": true}'::jsonb),
  ('defaults', '{"rate_limit_per_minute": 60, "monthly_quota": 10000}'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- ---------------------------------------------------------------------
-- 12. webhook_configs (signing secret stored encrypted with Fernet)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook_configs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  url                VARCHAR(500) NOT NULL,
  events             TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  secret_encrypted   TEXT NOT NULL,
  is_active          BOOLEAN NOT NULL DEFAULT true,
  last_status_code   SMALLINT,
  last_delivery_at   TIMESTAMPTZ,
  last_error         VARCHAR(200),
  failure_count      INTEGER NOT NULL DEFAULT 0,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS webhook_owner_idx ON webhook_configs (owner_id);
DROP TRIGGER IF EXISTS webhook_touch ON webhook_configs;
CREATE TRIGGER webhook_touch BEFORE UPDATE ON webhook_configs
  FOR EACH ROW EXECUTE FUNCTION ayaka_touch_updated_at();

-- ---------------------------------------------------------------------
-- Supporting tables
-- ---------------------------------------------------------------------
-- Serverless-safe fixed-window counters (rate limit, quota, brute force)
CREATE TABLE IF NOT EXISTS rate_limit_counters (
  bucket       VARCHAR(160) NOT NULL,
  window_start TIMESTAMPTZ  NOT NULL,
  count        INTEGER      NOT NULL DEFAULT 0,
  expires_at   TIMESTAMPTZ  NOT NULL,
  PRIMARY KEY (bucket, window_start)
);
CREATE INDEX IF NOT EXISTS rlc_exp_idx ON rate_limit_counters (expires_at);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  CHAR(64) NOT NULL UNIQUE,
  expires_at  TIMESTAMPTZ NOT NULL,
  used_at     TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS prt_user_idx ON password_reset_tokens (user_id);

CREATE TABLE IF NOT EXISTS email_logs (
  id           BIGSERIAL PRIMARY KEY,
  owner_id     UUID REFERENCES users(id) ON DELETE SET NULL,
  to_email     VARCHAR(254) NOT NULL,
  template     VARCHAR(32)  NOT NULL,
  status       VARCHAR(16)  NOT NULL CHECK (status IN ('sent','failed')),
  provider_id  VARCHAR(80),
  error        VARCHAR(300),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS email_logs_owner_idx ON email_logs (owner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS email_logs_time_idx  ON email_logs (created_at DESC);

CREATE TABLE IF NOT EXISTS notifications (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind        VARCHAR(16) NOT NULL DEFAULT 'info' CHECK (kind IN ('info','success','warning','security')),
  title       VARCHAR(120) NOT NULL,
  body        VARCHAR(500) NOT NULL DEFAULT '',
  read_at     TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS notif_user_idx ON notifications (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS announcements (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title       VARCHAR(120) NOT NULL,
  body        VARCHAR(1000) NOT NULL,
  level       VARCHAR(16) NOT NULL DEFAULT 'info' CHECK (level IN ('info','warning','critical')),
  is_active   BOOLEAN NOT NULL DEFAULT true,
  created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
DROP TRIGGER IF EXISTS announcements_touch ON announcements;
CREATE TRIGGER announcements_touch BEFORE UPDATE ON announcements
  FOR EACH ROW EXECUTE FUNCTION ayaka_touch_updated_at();

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     VARCHAR(64) PRIMARY KEY,
  applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations (version) VALUES ('001_init') ON CONFLICT DO NOTHING;
