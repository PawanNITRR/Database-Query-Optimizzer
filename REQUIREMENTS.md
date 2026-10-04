# Problem Statement 4: implementation and evidence

The original masking/restoration implementation in privacy.py is unchanged.
It is reversible pseudonymization, not ciphertext encryption or certified anonymity.

| Requirement | Implementation | Qualification |
|---|---|---|
| Abstract query content before AI | Existing HMAC identifiers and literal placeholders; comments removed | Structure and repeated-value patterns remain visible |
| Secure masked slow-log and historical-plan ingestion | JSON import and automatic masked history; strict plan-field allowlist; structural fingerprint | Local prototype, no enterprise authentication or log-stream connector |
| RL composite indexes and partition/sharding advice | Structural-context bandit selects index, monthly range, hash distribution or keep | Candidate B-tree columns derived from catalog/query metadata; no claim of globally optimal physical design |
| Automatic SQL rewriting | SQL rules or Ollama selected by rewrite RL policy | ORDER BY/LIMIT are preserved without rewriting |
| GNN execution trees and natural-language reasons | End-to-end trained message-passing model, operator parent/depth, model score and numeric evidence explanations | Synthetic training and holdout; not production-calibrated |
| PostgreSQL hooks/extensions sandbox | HypoPG installed on separate sandbox server, hypothetical planner cost/size | HypoPG estimates indexes, not hypothetical partitioning or exact elapsed time |
| Structural read/write/storage impact | Baseline/index/range/hash synthetic tables, median read/insert probes and storage sizes | Representative 50,000-row scenario, not an exact projection of the source schema/distribution |
| No source structural changes | Only source EXPLAIN/catalog reads for advice; benchmark SELECTs for local demo; all write probes in sandbox and rolled back | Source runtime comparison is for test data; production users should use metadata-only analysis |
| Dashboard and natural issue input | Existing query UI plus collapsed advice/history panels, three natural-language report intents | Broad arbitrary natural-language SQL generation is not supported |
| Review before deployment | Simulate, then approve/download review package | No automatic deployment endpoint; generated DDL is a design sketch requiring migration review |
| Over 50% targeted improvement | Live demo metrics and held-out evaluation in EVALUATION.json | Prepared synthetic workload; regressions and no-op actions are reported |
| RL robustness | Independent evaluation policy, held-out dates and a new query shape | Small benchmark, not a guarantee for arbitrary unseen evolving workloads |
| Data exposure evidence | Mask roundtrip, scrubbed-history, AI-payload and raw-plan exclusion tests | Supported-syntax tests do not certify 100% protection for every possible PostgreSQL expression |

## Two source paths

Optimize & compare actually executes read-only SELECTs on the local demo database.
Analyze structure uses only EXPLAIN (without ANALYZE) and information_schema/pg_indexes.
It does not select source result rows. Both paths feed only masked SQL and numeric
operator data to the AI. History stores only masked query/allowlisted plan data.

## Sandbox and simulation interpretation

The sandbox runs on 127.0.0.1:55433 with a separate volume and credentials. Its
50,000 generated rows are not copied from the source database. Index simulation
uses HypoPG's planner hook and compares its estimated size against a real
synthetic index. Actual index size and estimated size may differ materially
(for example because of B-tree deduplication); the measured error is reported.
Partitioning and hash routing are measured on real synthetic tables, not
misrepresented as hypothetical-extension support. Hash routing is local, not
a distributed network sharding test. Read/write probes and storage are measured
within this scenario. They are not promised as exact production estimates.

Source schema names appear in user-facing candidate DDL locally, never in AI
payloads or persisted history. Approval does not execute source DDL.

## Run evaluation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe evaluate.py
```

EVALUATION.json contains training episodes, held-out workloads, correctness,
privacy checks, synthetic GNN holdout and structural probes. Evaluation uses
temporary policy/history files so the live policy is not seeded by tests.

References: [HypoPG](https://hypopg.readthedocs.io/en/rel1_stable/usage.html),
[PostgreSQL partitioning](https://www.postgresql.org/docs/17/ddl-partitioning.html).

The app now demonstrates each major problem-statement module at prototype scope.
It does **not** establish enterprise compliance, exact production simulation or
generalization guarantees; these remain validation limits, not completed claims.

The live local LLM path is verified in AI_EVALUATION.json. It selects among eligible
masked candidates and provides bounded natural-language evidence. This is
AI-assisted constrained rewriting, not arbitrary LLM-generated SQL. A small local
model is the default so the demo does not depend on a large CPU model's latency.
