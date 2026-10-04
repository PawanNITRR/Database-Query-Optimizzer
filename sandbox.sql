CREATE EXTENSION IF NOT EXISTS hypopg;
-- Only synthetic generated data, never copies of source database rows.
CREATE TABLE baseline (id integer, customer_id integer, status text, order_date date, amount numeric);
INSERT INTO baseline SELECT n, (n * 7919) % 10000,
 CASE WHEN n % 4=0 THEN 'completed' ELSE 'pending' END,
 DATE '2024-01-01' + ((n * 97) % 730), (n % 10000)::numeric / 10
FROM generate_series(1, 50000) n;
CREATE TABLE indexed (LIKE baseline);
INSERT INTO indexed SELECT * FROM baseline;
CREATE INDEX ON indexed(status, order_date);
CREATE TABLE partitioned (LIKE baseline) PARTITION BY RANGE(order_date);
DO $$ DECLARE d date; next_d date; BEGIN
 FOR i IN 0..23 LOOP
  d := (DATE '2024-01-01' + make_interval(months=>i))::date;
  next_d := (d + INTERVAL '1 month')::date;
  EXECUTE format('CREATE TABLE partitioned_%s PARTITION OF partitioned FOR VALUES FROM (%L) TO (%L)', i, d, next_d);
 END LOOP;
END $$;
CREATE TABLE partitioned_default PARTITION OF partitioned DEFAULT;
INSERT INTO partitioned SELECT * FROM baseline;
CREATE TABLE hashed (LIKE baseline) PARTITION BY HASH(customer_id);
DO $$ BEGIN
 FOR i IN 0..3 LOOP
  EXECUTE format('CREATE TABLE hashed_%s PARTITION OF hashed FOR VALUES WITH (MODULUS 4, REMAINDER %s)', i, i);
 END LOOP;
END $$;
INSERT INTO hashed SELECT * FROM baseline;
ANALYZE;
