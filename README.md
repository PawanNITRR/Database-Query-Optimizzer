# QueryLab

**A local PostgreSQL query optimizer with private AI analysis, historical-workload diagnosis, and a data-growth prediction layer.**

QueryLab accepts a SELECT query, masks sensitive SQL names and values, analyzes its execution plan with a prototype GNN, selects a rewrite strategy with RL, and verifies the result using real PostgreSQL execution. A simple dark interface separates query comparisons, historical diagnosis, and predictions into horizontal tabs.

Built as a hackathon prototype. The application runs locally; it does not apply structural changes to the source database.

## Objectives

- Keep raw SQL identifiers, literal values, and database result rows out of AI requests.
- Identify potentially expensive operations using an execution-plan graph.
- Select supported SQL rewrites using measured feedback rather than assuming every rewrite is faster.
- Verify equivalent results and compare original versus selected query runtimes.
- Diagnose relevant past queries using a user statement and an uploaded history file.
- Explore index and partition recommendations in a separate synthetic database.
- Explain possible data-growth effects with a clearly labeled scale estimate.

## Project flows

The overview below is extracted from the supplied **Codeutsava presentation**. The diagrams that follow expand it to show the implemented validation and measurement steps.

![QueryLab pipeline, Prediction Layer, and Performance Layer from the presentation](docs/images/presentation-slide-1.png)

### 1. Query optimization

```mermaid
flowchart LR
    A[Input SELECT SQL] --> B[Parse and validate]
    B --> C[Mask names and literal values]
    B --> D[Local PostgreSQL EXPLAIN]
    D --> E[GNN scores plan operators]
    C --> F[RL selects an eligible strategy]
    E --> F
    F --> G[Local rewrite or local AI candidate selection]
    G --> H[Restore SQL using the local mapping]
    H --> I[Check equivalent result rows]
    I --> J[Benchmark original and selected SQL]
    J --> K[Show SQL, timings and GNN graph]
    J --> L[Update RL reward and local execution history]
```

The GNN consumes a graph of plan operators and numeric features. RL chooses an eligible action. When AI is enabled **and selected by RL**, Ollama chooses among constrained masked rewrite candidates. The original SQL mapping stays inside the application.

The result tabs are **Overview**, **Optimized SQL**, **GNN graph**, **AI privacy**, and **Runtime details**. SQL inputs and outputs have syntax highlighting. The privacy tab labels its two queries **Input hashed query** and **Hashed output query received from AI**; when RL uses local rules, the output is produced locally and the engine label identifies that path.

### 2. Ask about performance

```mermaid
flowchart LR
    A[User diagnosis statement] --> C[Match relevant historical queries locally]
    B[Upload multiple queries as SQL or JSON] --> C
    C --> D[Analyze uploaded plans or fresh EXPLAIN plans]
    D --> E[Select safe SQL rewrites]
    E --> F[Check results and measure local runtimes]
    F --> G[Improvements with highlighted gains and comparison bars]
    D --> H[Suggest structural changes]
    H --> I[Separate synthetic strategy benchmarks]
    I --> G
```

Enter a statement such as **“Why is the sales report slow? Check its joins.”** and upload a history file. Matching uses supported report topics, explicit table names, and operations such as joins, sorting, or aggregation. It is a small local matching system, not an unrestricted chatbot.

Only matching queries are measured. Original query numbers remain visible, and the output contains only **Improvements**: point-wise suggestions, highlighted measured gains, SQL, and baseline/proposed bars. An unmatched statement produces a message instead of analyzing unrelated queries.

Historical durations are supplied context. Improvement percentages use fresh measurements on the local test database. SQL-only files have no historical execution-plan evidence, so fresh EXPLAIN plans are obtained. Generic structural sandbox gains are labeled separately and are never added to SQL gains.

### 3. Prediction Layer

```mermaid
flowchart LR
    A[Current SQL in the editor] --> B[EXPLAIN, GNN and schema metadata]
    B --> C[Index and partition suggestions]
    C --> D[RL selects one structural strategy]
    D --> E[Benchmark in a separate synthetic database]
    E --> F[Measured baseline and proposed read times]
    F --> G[Move the data-scale slider from 1x to 100x]
    G --> H[Estimated runtimes and time saved]
```

Open **Prediction Layer** after entering SQL. Analysis runs automatically. The tab shows detailed suggestions and a slider with **0.1× increments**, with labeled markers at 1×, 10×, 20×, …, 100×. It prominently displays time saved in milliseconds, baseline time, proposed time, and scaled synthetic row count. It does not display an improvement percentage.

The measured baseline is a separate **50,000-row synthetic scenario**. At 1×, the times are measured; larger scales use linear extrapolation:

```text
Estimated baseline time = measured baseline time × scale
Estimated proposed time = measured proposed time × scale
Estimated time saved   = estimated baseline time − estimated proposed time
Synthetic row count    = 50,000 × scale
```

This assumes unchanged plan and selectivity. It does not simulate a real 100× source database, memory pressure, different plans, or distributed network behavior. The selected strategy is evaluated separately; the app does not measure the combined effect of all suggestions.

## Demo database

**Database:** `querylab` · **Total:** 415,000 synthetic records · **PostgreSQL:** 17

| Table | Attributes | Records |
| --- | --- | ---: |
| `customer` | id, name, email, city, created_at | 10,000 (10k) |
| `product` | id, name, category, price, stock | 5,000 (5k) |
| `orders` | id, customer_id, product_id, quantity, amount, status, order_date | 200,000 (200k) |
| `transaction` | id, order_id, amount, payment_method, status, transaction_date | 200,000 (200k) |

![Database schema from the presentation](docs/images/presentation-slide-2.png)

The presentation uses simplified `VARCHAR`, `DECIMAL`, and `TIMESTAMP` labels. The actual seed uses `TEXT`, `NUMERIC(10,2)`, and `DATE`, as shown below. The seed defines the exact record counts listed above.

```mermaid
erDiagram
    customer ||--o{ orders : places
    product ||--o{ orders : included_in
    orders ||--o| transaction : has_payment
    customer {
        integer id PK
        text name
        text email UK
        text city
        date created_at
    }
    product {
        integer id PK
        text name
        text category
        numeric price
        integer stock
    }
    orders {
        integer id PK
        integer customer_id FK
        integer product_id FK
        integer quantity
        numeric amount
        text status
        date order_date
    }
    transaction {
        integer id PK
        integer order_id FK,UK
        numeric amount
        text payment_method
        text status
        date transaction_date
    }
```

One order contains one product to keep the schema simple. `order_id` is unique in `transaction`; every seeded order has a transaction. Names, contact details, cities, prices, quantities, payment methods, and discounts are synthetic. Order dates span 2024–2025.

Use double quotes when querying the transaction table:

```sql
SELECT id, amount, payment_method
FROM "transaction"
LIMIT 10;
```

## Technology stack

| Component | Technology / role |
| --- | --- |
| Backend | Python 3.11+, Flask |
| SQL parsing and masking | SQLGlot, per-request HMAC pseudonyms, literal placeholders |
| Database access | Psycopg 3, local PostgreSQL 17 |
| GNN | NumPy; two message-passing layers and a trained readout |
| RL | Contextual UCB bandit with local SQLite state |
| Optional AI | Ollama, default `qwen2.5-coder:0.5b` |
| Structural experiments | Separate PostgreSQL instance with HypoPG and synthetic tables |
| Local history | SQLite, scrubbed plan metadata, Fernet-encrypted replay SQL |
| UI | HTML, CSS, JavaScript, SVG GNN graphs, syntax highlighting and tabs |
| Services and testing | Docker Compose, pytest |

## Setup

### Requirements

- Python **3.11 or newer**.
- Docker Desktop installed and running, with Docker Compose available.
- Internet access for the first package installation and Docker image build.
- Optional: Ollama running locally with the default model downloaded.
- Free local ports **5000**, **55432**, and **55433**.

### Start on Windows

Open PowerShell in the project directory, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d --build --wait
.\.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:5000/**. Keep the Flask terminal running. No environment file or account is required for the default demo.

The first Docker startup creates and seeds both databases. Later startups reuse their saved volumes.

### Start on macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
docker compose up -d --build --wait
.venv/bin/python app.py
```

### Enable local AI

With native Ollama installed and running:

```powershell
ollama pull qwen2.5-coder:0.5b
```

The default endpoint is `http://127.0.0.1:11434`. Reload the page after the model is available. **Use local AI** makes the model eligible for RL selection; it does not force every query through the model. When AI is unavailable, uncheck the option to use local rewrite rules with GNN and RL. If a selected AI request fails, the app reports the failure rather than silently calling it an AI result.

Alternatively, use the optional Docker AI service:

```powershell
docker compose --profile ai up -d ai
docker compose exec ai ollama pull qwen2.5-coder:0.5b
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:11435'
.\.venv\Scripts\python.exe app.py
```

Use native Ollama or the container endpoint as appropriate. Only local HTTP Ollama endpoints are accepted.

### Configuration

Set environment variables in the terminal before starting Flask:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Local `querylab` connection on port 55432 | Source/test PostgreSQL connection |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Local Ollama endpoint |
| `OLLAMA_MODEL` | `qwen2.5-coder:0.5b` | Model used for candidate selection |
| `RL_STATE_PATH` | `data/rl.sqlite3` | RL policy file |
| `ALLOW_TEST_DATABASE_BENCHMARK` | Unset | Set to `1` only for an explicitly designated alternative test database |

Runtime comparisons normally run only on the synthetic demo database. For a separate local test database, use a SELECT-only role and explicitly enable benchmarking:

```powershell
$env:DATABASE_URL = 'postgresql://username:password@127.0.0.1:5432/test_database'
$env:ALLOW_TEST_DATABASE_BENCHMARK = '1'
.\.venv\Scripts\python.exe app.py
```

Keep these settings for local test environments. The simulator remains a separate fixed local database on port 55433.

## Using the application

### Query comparison

1. Click **Monthly sales**, **Product report**, or **Payment report**, or enter a deterministic SELECT query.
2. Choose whether local AI is eligible.
3. Click **Optimize & compare**.
4. Use the result tabs to inspect timings, selected SQL, the interactive GNN graph, AI privacy, and runtime details.

The examples deliberately contain an unnecessary full-table materialized CTE to demonstrate a supported optimization. Their speedups do not represent every SQL workload.

### Historical diagnosis

1. Open **Ask about performance**.
2. Enter a statement such as **“Why is the sales report slow? Check its joins.”**
3. Choose a `.sql` or `.json` history file containing **2–10 SELECT queries**, under **200 KB**. Each query is limited to 20,000 characters.
4. Click **Analyze history file**.
5. Read **Improvements**. The summary shows matched query numbers, successful measurements, and the combined fresh SQL runtime change for those queries.

A sample three-report file is provided at [static/historic-queries.json](static/historic-queries.json) and through **Download sample history file** in the UI.

SQL files contain semicolon-separated statements:

```sql
SELECT id, amount FROM orders WHERE status = 'completed';
SELECT category, COUNT(*) FROM product GROUP BY category;
```

JSON files contain SQL strings or objects. `plan` and `duration_ms` are optional:

```json
[
  {
    "query": "SELECT id, amount FROM orders WHERE status = 'completed'",
    "duration_ms": 120,
    "plan": {
      "Plan": {
        "Node Type": "Seq Scan",
        "Plan Rows": 50000,
        "Total Cost": 6000
      }
    }
  },
  {
    "query": "SELECT category, COUNT(*) FROM product GROUP BY category"
  }
]
```

These durations and plans are user-supplied evidence, not trusted measurements. Sensitive plan fields are scrubbed. The application obtains fresh measurements to establish runtime gains. Uploaded queries must reference tables present in the configured test database.

**“Improve overall query performance”** analyzes the entire file. Specific topics or operations filter it. Matching is local and limited; the diagnosis statement is not sent to the model. Query histories from pgAdmin or other tools are not captured automatically—you must supply a file or run queries through QueryLab.

### Prediction Layer

1. Enter SQL in the main editor.
2. Open **Prediction Layer**; analysis and the selected synthetic experiment run automatically.
3. Read the suggested changes and their tradeoffs.
4. Move the smooth **1×–100×** slider to see estimated runtimes and time saved.

No source DDL is applied. This tab contains only suggestions/improvements and the scale display; the previous simulation/download buttons and extra panels have been removed.

## Measurement, GNN and RL

- **Result check:** PostgreSQL compares both result multisets with bidirectional `EXCEPT ALL` in a read-only, repeatable-read transaction. Result rows stay inside PostgreSQL.
- **Timings:** both queries are warmed, then run four times in alternating order. The displayed execution time is the median. Planning time and buffer statistics are also available.
- **Limits:** each statement has a 10-second timeout and a 2-second lock timeout. `ORDER BY`, `LIMIT`, and `OFFSET` queries are kept unchanged because multiset comparison cannot verify ordering semantics.
- **Supported rewrites:** deduplicate IN values and inline eligible single-use plain-table `SELECT *` CTEs by replacing `MATERIALIZED` with `NOT MATERIALIZED`. Complex or reused CTEs are kept unchanged.
- **GNN:** a small network trained end to end on synthetic graphs. It scores operators using graph connections and numeric plan features. Scores are prototype signals, not calibrated bottleneck probabilities.
- **RL:** a contextual UCB bandit chooses an action using structural query context. It explores untested actions and then balances learned mean reward with exploration. This is a one-step adaptive policy, not a multi-step production tuning agent.
- **Rewrite reward:** fractional median runtime gain, clipped to `[-1, 1]`; unchanged queries get zero. Differences below 3% or 0.05 ms get zero to reduce noise. Failed/invalid proposals receive `-1`.
- **Structural experiments:** a separate 50,000-row PostgreSQL sandbox has baseline, indexed, monthly-partitioned, and hash-partitioned variants. HypoPG can estimate index planner cost and size. Synthetic inserts are rolled back. Structural RL reward includes read gain and write/storage penalties.

No universal speedup is promised. Measurements may fluctuate with caches and machine load, and regressions are shown. PostgreSQL execution times exclude network transfer and browser rendering.

## Privacy and local storage

The AI privacy layer performs **reversible pseudonymization, not ciphertext encryption**. Fresh HMAC-based tokens replace identifiers; placeholders replace literals; comments are removed from the AI input. SQL structure remains visible. The reverse mapping exists only for the current request.

Only masked SQL, eligible candidate labels, allowlisted plan operators, numeric features and GNN evidence go to local Ollama. Raw identifiers, literals, result rows, and uploaded diagnosis statements are excluded.

Successfully benchmarked queries are saved for local history with scrubbed execution plans and durations. Replay SQL is separately encrypted with Fernet. Its local key is stored beside the history file; both are excluded from Git. This storage encryption does not replace or change the AI masking path.

| Local file | Contents |
| --- | --- |
| `data/rl.sqlite3` | Structural contexts, action counts and learned rewards; no raw SQL |
| `data/history.sqlite3` | Masked history, numeric/operator metadata, durations and encrypted replay SQL |
| `data/history.key` | Local Fernet key needed to decrypt replay history |

The key resides on the same machine, so this is local storage protection, not an isolated key-management service. Back up the history and key together if you need replay history after moving the project.

## Directory structure

```text
QueryLab/
├── app.py                       # Flask application and API routes
├── database.py                  # Connections, EXPLAIN and runtime comparison
├── privacy.py                   # SELECT validation, masking and restoration
├── gnn.py                       # Synthetic-trained plan GNN
├── rl.py                        # Contextual UCB policy and rewards
├── optimizer.py                 # Local rewrites and optional Ollama selection
├── recommendations.py           # Catalog-based index/partition suggestions
├── simulation.py                # Separate PostgreSQL strategy benchmarks
├── workload_upload.py           # Multi-query upload parsing and diagnosis matching
├── history.py                   # Masked plans and encrypted replay history
├── workloads.py                 # Supported demo natural-language report templates
├── diagnosis.py                 # Legacy single-history diagnosis API helper
├── demo.sql                     # 415,000-row retail seed and indexes
├── sandbox.sql                  # Synthetic experiment tables and HypoPG setup
├── compose.yaml                 # PostgreSQL services and optional Ollama service
├── Dockerfile.sandbox            # PostgreSQL image with HypoPG
├── requirements.txt             # Pinned Python dependencies
├── pytest.ini                   # Test configuration
├── templates/
│   └── index.html               # Main page
├── static/
│   ├── style.css                # Dark theme and responsive layouts
│   ├── app.js                   # Main SQL comparison behavior
│   ├── extended.js              # History upload, prediction slider and visuals
│   ├── tabs.js                  # Horizontal accessible tab navigation
│   ├── sql-editor.js            # Local SQL syntax highlighting
│   ├── gnn-graph.js             # Interactive SVG execution-plan graph
│   ├── examples.js              # Sales, product and payment SQL examples
│   └── historic-queries.json    # Sample three-query upload
├── docs/
│   └── images/
│       ├── presentation-slide-1.png  # Flow image extracted from the supplied PPTX
│       └── presentation-slide-2.png  # Schema image extracted from the supplied PPTX
├── tests/                       # Privacy, rewrite, RL and PostgreSQL integration checks
├── data/                        # Runtime SQLite state and history key; ignored by Git
├── evaluate.py                  # Held-out workload and simulation evaluation
├── evaluate_ai.py               # Real local AI pipeline evaluation
├── EVALUATION.json              # Saved evaluation evidence
├── AI_EVALUATION.json           # Saved local AI evaluation evidence
├── DEMO.md                      # Earlier demo notes and results
├── REQUIREMENTS.md              # Problem-statement implementation notes
└── README.md                    # Current setup and usage guide
```

The source PowerPoint is not needed at runtime. Its two embedded images are copied into `docs/images` so the README is portable. Mermaid diagrams render on GitHub and other compatible Markdown viewers.

## Viewing the data in pgAdmin

For pgAdmin running on your computer, register a PostgreSQL server with:

| Setting | Value |
| --- | --- |
| Host | `127.0.0.1` |
| Port | `55432` |
| Database / maintenance database | `querylab` |
| Username | `querylab` |
| Password | `querylab_local` |

These are local demo credentials from `compose.yaml`. Open **Databases → querylab → Schemas → public → Tables**, then right-click a table and select **View/Edit Data**. Docker Desktop shows the containers; pgAdmin is the table browser. If pgAdmin runs inside another container on the Compose network, use service hostname `db` and port `5432` instead of host loopback.

## Tests and evaluation

Start both PostgreSQL services, then run:

```powershell
docker compose up -d --build --wait
.\.venv\Scripts\python.exe -m pytest -q
```

The suite includes database integration checks; run it with the local databases available. Tests isolate their RL policy and history state. The latest full verification during development passed **52 tests**.

Optional evaluation scripts:

```powershell
.\.venv\Scripts\python.exe evaluate.py
.\.venv\Scripts\python.exe evaluate_ai.py
```

The AI evaluation requires the configured local model. Saved JSON reports are evidence from a particular run, not fixed performance guarantees or a claim of production calibration.

## Troubleshooting and service management

| Issue | What to check |
| --- | --- |
| PostgreSQL not connected | Docker Desktop is running; `docker compose ps` shows healthy `db` and `sandbox` services |
| Tables missing after an older installation | Re-run `demo.sql` using the command below |
| AI model unavailable | Ollama is running, the configured model is downloaded, and the endpoint matches native port 11434 or container port 11435 |
| History diagnosis has no matches | Adjust the statement or include matching report/table/operation queries in the file |
| Sandbox unavailable | Run `docker compose up -d --build --wait`; check `docker compose logs sandbox` |
| No rewrite or slower result | The query may have no eligible rule, RL may explore keeping it, or the measured change may be a regression |
| UI changes not visible | Refresh the browser; restart Flask after template changes |
| Port already used | Stop the conflicting local process or inspect the configured services before changing ports |

Re-run the deterministic demo seed on an existing volume:

```powershell
Get-Content -Raw demo.sql | docker compose exec -T db psql -U querylab -d querylab -v ON_ERROR_STOP=1
```

The seed avoids duplicate IDs and refreshes synthetic purchase details. It is a setup operation that writes demo records; the application does not reseed data during query analysis.

Stop Flask with **Ctrl+C**. Stop containers while keeping saved database volumes:

```powershell
docker compose stop
```

Restart services with `docker compose up -d --build --wait`. Avoid removing the volumes if you want to keep database contents.

## Prototype boundaries

- The SQL gate supports deterministic read-only SELECT workloads, not arbitrary SQL or user-defined functions. It is not a production security sandbox.
- GNN training uses synthetic graphs; RL is a contextual bandit; neither guarantees an optimal query plan.
- Historical matching uses local rules, not unrestricted natural-language understanding or automatic dashboard discovery.
- Result equality checks can be expensive and require result types supported by `EXCEPT ALL`.
- Structural recommendations are not automatically applied. Local hash partitions do not establish distributed sharding performance.
- Scaled predictions are linear estimates from a generic synthetic scenario, not production-capacity forecasts.
- This project does not claim zero information leakage, formal privacy certification, or guaranteed improvement percentages.
