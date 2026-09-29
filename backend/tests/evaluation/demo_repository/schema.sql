CREATE TABLE orders (
  id BIGSERIAL PRIMARY KEY,
  customer_id BIGINT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('CREATED', 'PAID', 'SHIPPED', 'CANCELLED')),
  inspection_passed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE refunds (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id),
  status TEXT NOT NULL,
  UNIQUE(order_id)
);
