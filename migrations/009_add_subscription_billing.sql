-- ===========================================================
-- Migration 009: Stripe subscription tiers and usage tracking
-- ===========================================================

-- 1. Add subscription fields to users table
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS stripe_customer_id     VARCHAR(255) UNIQUE,
  ADD COLUMN IF NOT EXISTS subscription_tier      VARCHAR(50)  NOT NULL DEFAULT 'free',
  ADD COLUMN IF NOT EXISTS subscription_status    VARCHAR(50)  NOT NULL DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255),
  ADD COLUMN IF NOT EXISTS subscription_period_end TIMESTAMPTZ;

-- 2. Add message_count to chat_history
--    Tracks user-sent messages only (not AI responses) for fast limit checking.
ALTER TABLE chat_history
  ADD COLUMN IF NOT EXISTS message_count INTEGER NOT NULL DEFAULT 0;

-- 3. Backfill message_count for existing chats from stored JSON
UPDATE chat_history
SET message_count = (
  SELECT COUNT(*)
  FROM json_array_elements(message::json) AS msg
  WHERE msg->>'role' = 'user'
)
WHERE message IS NOT NULL
  AND message != ''
  AND message != '[]';

-- 4. Create UsageTracking table (one row per user per billing period)
CREATE TABLE IF NOT EXISTS usage_tracking (
  id                        SERIAL PRIMARY KEY,
  user_id                   VARCHAR NOT NULL REFERENCES users(user_id),
  period_start              TIMESTAMPTZ NOT NULL,
  period_end                TIMESTAMPTZ NOT NULL,
  report_regenerations_used INTEGER NOT NULL DEFAULT 0,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                TIMESTAMPTZ
);

-- 5. Indexes
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer_id
  ON users(stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_subscription_tier
  ON users(subscription_tier);

CREATE INDEX IF NOT EXISTS idx_usage_tracking_user_period
  ON usage_tracking(user_id, period_start, period_end);

CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_tracking_user_period_unique
  ON usage_tracking(user_id, period_start);
