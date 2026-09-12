CREATE TABLE subscriptions (
  id BIGSERIAL PRIMARY KEY,
  account_id BIGINT NOT NULL,
  status TEXT NOT NULL,
  plan TEXT NOT NULL
);

CREATE TABLE invoices (
  id BIGSERIAL PRIMARY KEY,
  subscription_id BIGINT NOT NULL REFERENCES subscriptions(id),
  amount INTEGER NOT NULL,
  processing BOOLEAN NOT NULL DEFAULT FALSE,
  idempotency_key TEXT UNIQUE,
  UNIQUE(subscription_id)
);
