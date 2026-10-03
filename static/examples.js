// Business reports with deliberately unnecessary full-table materialization.
const examples = {
  sales: `WITH recent_orders AS MATERIALIZED (SELECT * FROM orders)
SELECT c.city, p.category, COUNT(*) AS order_count,
       SUM(o.amount) AS revenue
FROM recent_orders o
JOIN customer c ON c.id = o.customer_id
JOIN product p ON p.id = o.product_id
JOIN "transaction" t ON t.order_id = o.id
WHERE o.status = 'completed' AND t.status = 'paid'
  AND o.order_date >= CAST('2025-06-01' AS DATE)
  AND o.order_date < CAST('2025-07-01' AS DATE)
GROUP BY c.city, p.category;`,
  products: `WITH all_orders AS MATERIALIZED (SELECT * FROM orders)
SELECT p.category, COUNT(*) AS order_count,
       SUM(o.quantity) AS units_sold, SUM(o.amount) AS revenue
FROM all_orders o
JOIN product p ON p.id = o.product_id
WHERE o.status = 'completed'
  AND o.order_date >= CAST('2025-11-01' AS DATE)
  AND o.order_date < CAST('2025-12-01' AS DATE)
GROUP BY p.category;`,
  payments: `WITH all_orders AS MATERIALIZED (SELECT * FROM orders)
SELECT t.payment_method, COUNT(*) AS payments,
       SUM(t.amount) AS total_paid
FROM all_orders o
JOIN "transaction" t ON t.order_id = o.id
WHERE o.status = 'completed' AND t.status = 'paid'
  AND o.order_date >= CAST('2025-03-01' AS DATE)
  AND o.order_date < CAST('2025-04-01' AS DATE)
GROUP BY t.payment_method;`
};
