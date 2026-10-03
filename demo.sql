-- Synthetic retail dataset. Safe to re-run: existing rows are retained.
BEGIN;
CREATE TABLE IF NOT EXISTS customer (
  id integer PRIMARY KEY, name text NOT NULL, email text NOT NULL UNIQUE,
  city text NOT NULL, created_at date NOT NULL
);
INSERT INTO customer
SELECT n, 'Customer ' || n, 'customer' || n || '@example.test',
  (ARRAY['Mumbai', 'Delhi', 'Bengaluru', 'Chennai', 'Pune'])[1 + n % 5],
  DATE '2023-01-01' + (n % 730)
FROM generate_series(0, 9999) n ON CONFLICT DO NOTHING;
UPDATE customer SET
  name = (ARRAY['Aarav','Diya','Rohan','Ananya','Kabir','Meera','Arjun','Isha','Vikram','Priya'])[1 + id % 10]
    || ' ' || (ARRAY['Sharma','Patel','Rao','Singh','Iyer','Mehta','Das','Nair','Joshi','Kapoor'])[1 + (id / 10) % 10],
  email = 'customer' || id || '@example.test',
  city = (ARRAY['Mumbai','Delhi','Bengaluru','Chennai','Pune','Hyderabad','Kolkata','Jaipur'])[1 + (id / 7) % 8];

CREATE TABLE IF NOT EXISTS product (
  id integer PRIMARY KEY, name text NOT NULL, category text NOT NULL,
  price numeric(10,2) NOT NULL CHECK (price > 0),
  stock integer NOT NULL CHECK (stock >= 0)
);
INSERT INTO product
SELECT n, 'Product ' || n,
  (ARRAY['Electronics', 'Clothing', 'Home', 'Books', 'Sports'])[1 + n % 5],
  50 + (n % 2000) * 2.5, 20 + n % 500
FROM generate_series(1, 5000) n ON CONFLICT DO NOTHING;
UPDATE product SET name =
  CASE category
    WHEN 'Electronics' THEN (ARRAY['Wireless Headphones','Smart Watch','Bluetooth Speaker','USB-C Charger','Tablet'])[1 + (id / 5) % 5]
    WHEN 'Clothing' THEN (ARRAY['Cotton Shirt','Denim Jeans','Running Jacket','Summer Dress','Polo T-Shirt'])[1 + (id / 5) % 5]
    WHEN 'Home' THEN (ARRAY['Desk Lamp','Coffee Maker','Storage Box','Bed Sheet','Office Chair'])[1 + (id / 5) % 5]
    WHEN 'Books' THEN (ARRAY['SQL Handbook','Python Guide','Business Basics','Travel Atlas','Science Stories'])[1 + (id / 5) % 5]
    ELSE (ARRAY['Yoga Mat','Football','Running Shoes','Tennis Racket','Gym Bag'])[1 + (id / 5) % 5]
  END || ' - Model ' || id;

-- Upgrade the previous orders table without discarding its rows or amounts.
CREATE TABLE IF NOT EXISTS orders (
  id integer PRIMARY KEY, customer_id integer, amount numeric(10,2), status text
);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_id integer;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS quantity integer;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_date date;
UPDATE orders SET product_id = 1 + (id % 5000), quantity = 1,
  order_date = DATE '2024-01-01' + (id % 730)
WHERE product_id IS NULL OR quantity IS NULL OR order_date IS NULL;
INSERT INTO orders (id, customer_id, product_id, quantity, amount, status, order_date)
SELECT n, n % 10000, p.id, 1 + n % 5, p.price * (1 + n % 5),
  CASE WHEN n % 4 = 0 THEN 'completed' ELSE 'pending' END,
  DATE '2024-01-01' + (n % 730)
FROM generate_series(1, 200000) n
JOIN product p ON p.id = 1 + n % 5000 ON CONFLICT DO NOTHING;
ALTER TABLE orders ALTER COLUMN customer_id SET NOT NULL;
ALTER TABLE orders ALTER COLUMN product_id SET NOT NULL;
ALTER TABLE orders ALTER COLUMN quantity SET NOT NULL;
ALTER TABLE orders ALTER COLUMN order_date SET NOT NULL;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'orders'::regclass AND conname = 'orders_customer_fk') THEN
    ALTER TABLE orders ADD CONSTRAINT orders_customer_fk FOREIGN KEY (customer_id) REFERENCES customer(id);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'orders'::regclass AND conname = 'orders_product_fk') THEN
    ALTER TABLE orders ADD CONSTRAINT orders_product_fk FOREIGN KEY (product_id) REFERENCES product(id);
  END IF;
END $$;

-- Use quotes when querying this table because transaction is an SQL keyword.
CREATE TABLE IF NOT EXISTS "transaction" (
  id integer PRIMARY KEY, order_id integer NOT NULL UNIQUE REFERENCES orders(id),
  amount numeric(10,2) NOT NULL, payment_method text NOT NULL,
  status text NOT NULL, transaction_date date NOT NULL
);
INSERT INTO "transaction"
SELECT id, id, amount,
  (ARRAY['UPI', 'card', 'net_banking', 'cash'])[1 + id % 4],
  CASE WHEN status = 'completed' THEN 'paid' ELSE 'pending' END, order_date
FROM orders ON CONFLICT DO NOTHING;
-- Independently mixed synthetic dimensions create useful reporting variation.
UPDATE orders SET
  customer_id = (('x' || substr(md5(id::text || 'customer'), 1, 7))::bit(28)::integer) % 10000,
  product_id = 1 + (('x' || substr(md5(id::text || 'product'), 1, 7))::bit(28)::integer) % 5000,
  quantity = 1 + (('x' || substr(md5(id::text || 'quantity'), 1, 7))::bit(28)::integer) % 5,
  order_date = DATE '2024-01-01' + ((('x' || substr(md5(id::text || 'date'), 1, 7))::bit(28)::integer) % 730);
UPDATE orders o SET amount = round(p.price * o.quantity *
  (1 - ((('x' || substr(md5(o.id::text || 'discount'), 1, 7))::bit(28)::integer) % 4) * 0.05), 2)
FROM product p WHERE p.id = o.product_id;
UPDATE "transaction" t SET amount = o.amount, transaction_date = o.order_date,
  payment_method = (ARRAY['UPI','card','net_banking','cash'])[1 +
    ((('x' || substr(md5(o.id::text || 'payment'), 1, 7))::bit(28)::integer) % 4)],
  status = CASE WHEN o.status = 'completed' THEN 'paid' ELSE 'pending' END
FROM orders o WHERE o.id = t.order_id;
CREATE INDEX IF NOT EXISTS orders_status_idx ON orders(status);
CREATE INDEX IF NOT EXISTS orders_customer_idx ON orders(customer_id);
CREATE INDEX IF NOT EXISTS orders_product_idx ON orders(product_id);
CREATE INDEX IF NOT EXISTS orders_date_idx ON orders(order_date);
CREATE INDEX IF NOT EXISTS orders_status_date_idx ON orders(status, order_date);
CREATE INDEX IF NOT EXISTS product_category_idx ON product(category);
CREATE INDEX IF NOT EXISTS transaction_status_idx ON "transaction"(status);
ANALYZE customer;
ANALYZE product;
ANALYZE orders;
ANALYZE "transaction";
COMMIT;
