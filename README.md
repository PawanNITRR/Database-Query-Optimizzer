# QueryLab

A local SQL optimizer: enter a SELECT, mask it, analyze its execution-plan graph,
choose a rewrite with RL, restore SQL and compare PostgreSQL runtimes.
Optional collapsed panels provide structural advice, a synthetic simulation
sandbox and masked log history. No accounts or production deployment automation.

## Run on Windows

Requires Python 3.11+, Docker Desktop (running), and optionally Ollama.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d --build --wait
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000 and click **Load example**. To use AI, install Ollama and run `ollama pull qwen2.5-coder:0.5b` first. Otherwise uncheck **Use local AI** to test the pipeline with conservative local SQL rules. AI failure is reported explicitly; it is never silently presented as an AI result.

For your existing local database, set `DATABASE_URL` before starting:

```powershell
$env:DATABASE_URL = 'postgresql://username:password@127.0.0.1:5432/database_name'
$env:OLLAMA_MODEL = 'qwen2.5-coder:0.5b'
.\.venv\Scripts\python.exe app.py
```

Use a SELECT-only database role on a local test database. Runtime comparisons default to the synthetic querylab database on port 55432. For another explicitly designated test database, set ALLOW_TEST_DATABASE_BENCHMARK=1. Use Analyze structure for production metadata-only analysis. Each comparison uses a read-only repeatable-read transaction with a 10-second timeout per statement. Arbitrary user-defined functions and write statements are rejected, but this is a prototype SQL gate, not a production sandbox. Built-in volatile functions may still cause side effects or inconsistent results; use ordinary deterministic SELECT queries.

## Demo database

The synthetic retail database contains 10,000 customers, 5,000 products,
200,000 orders and 200,000 payment transactions. Orders reference customer
and product; each transaction references one order. One order contains one
product to keep the schema simple. Customer contact details are synthetic.

Names, products, cities, purchase quantities, discounts, dates and payment methods
are varied synthetic data. Orders span 2024-2025, with independently mixed
customer/product/date/payment dimensions. Amounts match the product price times
quantity, less a synthetic 0-15% discount; payment amounts match orders.

The Load example button joins all four tables. Use double quotes for
the transaction table: `SELECT * FROM "transaction" LIMIT 100;`.

Fresh Docker volumes are initialized automatically. To upgrade an existing
demo volume or safely re-run the seed without resetting data:

```powershell
Get-Content -Raw demo.sql | docker compose exec -T db psql -U querylab -d querylab -v ON_ERROR_STOP=1
```

The seed retains order IDs, fills missing records, and refreshes synthetic
names and purchase details deterministically. The complete seed is transactional
and uses conflict checks to avoid duplicate records. Seeding is a setup step;
the app never regenerates the dataset when running a query.
View the four tables in pgAdmin under querylab → Schemas → public → Tables.

## What each step does

1. SQLGlot parses one PostgreSQL SELECT.
2. A fresh per-request HMAC key masks all identifiers; literal placeholders hide values and comments are removed. The reverse mapping stays in process memory and is discarded after the request. This is reversible pseudonymization, **not encryption**: SQL structure and repeated-value patterns remain visible.
3. PostgreSQL supplies an estimated execution tree. A small NumPy graph neural network applies two message-passing layers and a readout trained end to end on synthetic graphs. It demonstrates the architecture rather than a production-quality optimizer. Only allowlisted operator labels, numeric estimates and GNN scores accompany masked SQL to Ollama. Raw plan filters, relation names, SQL values and result rows are excluded.
4. When RL selects AI, Ollama chooses among eligible masked rewrite candidates using GNN evidence. The displayed reason is grounded in the selected action and actual GNN node metadata, avoiding unverified model prose. Constrained JSON output avoids invented identifiers and lowers latency. The app restores known pseudonyms locally. The optimized SQL and both masked versions are displayed.
5. PostgreSQL checks multiset result equality using bidirectional EXCEPT ALL in one snapshot. Queries with ORDER BY, LIMIT or OFFSET remain unchanged because the multiset check cannot validate their ordering. Both queries are warmed, then run four times in alternating order using EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON). The UI shows median execution time, last-run planning time, result count and buffer statistics. No result rows are fetched into the application.

Local rules remove duplicate IN-list values and change single-use plain-table
`SELECT *` CTEs from MATERIALIZED to NOT MATERIALIZED. The latter allows
PostgreSQL to push filters down and use the existing status/date index.
Complex or reused CTEs are not inlined by this rule. All changed queries still
pass the database result check. Faster execution is not promised for arbitrary
queries; unchanged queries and regressions are shown honestly. Result comparison
can be costly and requires types supporting EXCEPT ALL. Runtime measurements
exclude client transfer time and may fluctuate with cache state and load.

## Hackathon demonstration

See [DEMO.md](DEMO.md) for the demo sequence and measured report timings.
The page has Monthly sales, Product report, and Payment report example buttons.
Each uses an intentionally inefficient full-table materialized CTE as a clear
teaching example. They are not representative of every SQL workload.

With AI unchecked, GNN analysis and RL select a deterministic rewrite, labeled
RL + local rules. Checking AI makes Ollama eligible; RL may choose another action.
The default small model is qwen2.5-coder:0.5b; OLLAMA_MODEL can select a larger one.
Only masked SQL and the top three GNN evidence nodes are sent. The model is kept
loaded for 30 minutes, with a 45-second timeout and a 256-token generation limit.
Response time is displayed separately from PostgreSQL execution time. See
AI_EVALUATION.json for the actual live AI verification result.

An optional Docker Ollama profile is included for machines without native Ollama:
`docker compose --profile ai up -d ai`, then
`docker compose exec ai ollama pull qwen2.5-coder:0.5b`.
Set OLLAMA_BASE_URL=http://127.0.0.1:11435 for this container. Native Ollama uses
port 11434. Only loopback model endpoints are allowed.

## Scope

Implements the requested five-step MVP plus a small RL action-selection loop.
Includes metadata-only index/partition/sharding-candidate advice, HypoPG planner
simulation, synthetic write-latency/storage probes, masked log ingestion and
approval/download for manual review. Actual distributed sharding and production
deployment are intentionally not executed.

## Reinforcement learning

The RL component is a contextual UCB bandit, a one-step form of reinforcement
learning. It selects among keeping the original, inlining eligible CTEs,
deduplicating IN values, combining distinct rewrites, and asking Ollama when
Use local AI is checked. That checkbox makes AI eligible; RL may select a local
action instead. Ineligible/no-op rewrite actions are removed. Ordered/limited
queries only allow keeping the original.

Context uses coarse structural features: join count, materialized CTE/IN flags,
estimated row-count magnitude and a GNN-score bucket. It never uses identifiers
or literal values. New actions are tried first, then an upper-confidence-bound
policy balances mean reward with exploration. There is no preloaded reward data.

Reward is (original median runtime - candidate median runtime) / original runtime,
clipped to [-1, 1]. Unchanged queries earn zero, and differences below 3% or
0.05 ms earn zero to reduce noise. Invalid or failed rewrite proposals earn -1.
Q(context, action) is updated by the incremental mean of observed rewards.
Each action executes once through the existing comparison pipeline; RL adds no
extra database benchmark runs. Exploration can intentionally keep the original
or try a less successful action. No universal speedup is promised.

Learned counts and Q values persist locally in `data/rl.sqlite3`, ignored by Git.
The SQLite policy stores no SQL, query hashes, row data, credentials or names.
Set RL_STATE_PATH to select another policy file. Tests use isolated temporary
policies and do not train the live app. This is a small adaptive prototype,
not a multi-step RL engine for indexes or sharding.

The structural policy has a separate context namespace. It selects composite-index,
monthly-range-partition, hash-distribution or keep strategies and learns a reward
from synthetic read-time gains minus write-latency/storage penalties. Recommendations
come from query predicates and schema catalogs. Measurements represent a generic
scenario, not an exact source-schema simulation.

## Additional problem-statement modules

Expand **Structural recommendations & sandbox**, click Analyze structure, then
Simulate proposal. Review GNN evidence, candidate DDL, read/write/storage metrics,
and HypoPG cost/size estimates. Approve & download saves a review package; it never
executes source DDL. The separate simulator database runs on port 55433 and is
automatically initialized with 50,000 generated rows, indexes, monthly range
partitions, and four hash partitions. No source rows are copied there.

Expand **Masked slow-query logs & plan history** to import a JSON array or view
history. Each record contains query, plan and optional duration_ms. Raw names,
filters, literals and other plan text are removed before persistence. Runtime
comparisons automatically add scrubbed history. Structural analysis does not
execute queries or retrieve result rows.

You can enter a natural question such as "Why is the monthly sales dashboard slow?"
in the query box. Three supported intents (sales/products/payments) use visible
demo SQL templates. This is not unrestricted natural-language SQL generation.

See [REQUIREMENTS.md](REQUIREMENTS.md) for scope and validation limits, and
[EVALUATION.json](EVALUATION.json) for actual held-out workload and simulation
measurements. In particular, no exact-production-simulation or enterprise
privacy certification is claimed.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -m 'not integration'
# With the demo container running:
.\.venv\Scripts\python.exe -m pytest
```

References: [SQLGlot AST API](https://sqlglot.com/), [PostgreSQL read-only transactions](https://www.postgresql.org/docs/17/sql-set-transaction.html), [EXPLAIN](https://www.postgresql.org/docs/17/sql-explain.html).
