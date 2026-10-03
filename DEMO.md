# Hackathon demo

## Start

Start Docker Desktop, then run:

```powershell
docker compose up -d --wait
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000 and refresh the page.

## Show the dataset

In pgAdmin, refresh querylab → Schemas → public → Tables.
There are 415,000 generated records across four related tables:
10,000 customer, 5,000 product, 200,000 orders and 200,000 transaction.
All contact details and purchases are synthetic.

```sql
SELECT c.name, c.city, p.name AS product, p.category,
       o.quantity, o.amount, o.order_date, t.payment_method, t.status
FROM orders o
JOIN customer c ON c.id = o.customer_id
JOIN product p ON p.id = o.product_id
JOIN "transaction" t ON t.order_id = o.id
LIMIT 20;
```

## Run the optimizer

1. Click Monthly sales (the default Load example).
2. Leave Use local AI unchecked for the measured quick demo.
3. Click Optimize & compare.
4. Explain that an unnecessary MATERIALIZED CTE processes all orders before
   filtering. The rewrite allows PostgreSQL to filter by status/date using
   an existing composite index, before joining customers, products and payments.
5. Show both measured runtimes and the result-row equivalence check.
6. Expand See what the AI receives to show pseudonyms and hidden literals.
7. Expand Plan analysis to show the prototype GNN's operator scores.
8. Repeat with Product report or Payment report.

## Observed performance

Measured on this machine after loading the enriched dataset. Each response
includes a result check, warm-up runs and four alternating timed runs per query.

| Report | Original median | Optimized median | Improvement | Entire response |
|---|---:|---:|---:|---:|
| Monthly sales | 52.293 ms | 19.831 ms | 62.08% | 0.615 s |
| Product report | 34.440 ms | 3.351 ms | 90.27% | 0.314 s |
| Payment report | 45.935 ms | 13.485 ms | 70.64% | 0.454 s |

These are observations, not guaranteed future results. The original examples
deliberately include an optimization opportunity. The app always measures live
timings; these numbers are never injected into results.

## AI demonstration

For actual LLM rewriting, have Ollama running with the configured model already
downloaded, check Use local AI, and run a sample before the judging session to
warm the model. The default is qwen2.5-coder:7b. CPU inference may take much longer
than database execution; no AI latency claim has been verified here.
Do not describe Local rules mode as LLM optimization.

The GNN uses message passing with a readout trained on synthetic graphs; it is
a prototype analysis component, not a model trained on real workload history.
Masking is reversible pseudonymization, not ciphertext encryption. All result
comparison stays in PostgreSQL and raw rows are never sent to the model.
