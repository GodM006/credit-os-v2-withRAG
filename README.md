# Credit Decisioning OS — Layers 1–3

An agentic credit underwriting system, built layer by layer per the architecture
diagram. This drop implements **Layer 1** (Data Acquisition Agents),
**Layer 2** (Context Graph), and **Layer 3** (Triangulation Engine) end to end.

```
backend/   FastAPI + LangGraph + Pydantic + Groq (Llama 3.3) + Neo4j
frontend/  React (Vite) console for triggering runs and inspecting agent/graph/triangulation output
```

## What's built

### Layer 1 — Data Acquisition Agents
- **6 agents** (banking, GST, bureau, financials, ledger, KYC), each a thin
  wrapper around a shared extraction engine (`app/agents/base_agent.py`).
- **Groq-hosted Llama** does the extraction (no paid APIs). Each agent gets a
  raw text "document" + a strict Pydantic schema, and must return JSON that
  validates against it, with retries on validation failure.
- **Business-rule checks** on top of schema validation (`app/validation/rules.py`)
  — a stand-in for the diagram's Great Expectations layer.
- **Synthetic data generator** (`app/synthetic/generator.py`): `clean`, `noisy`,
  and `fraud_risk` scenarios, plus a `generate_linked_pair()` helper that
  deliberately shares a director between two cases (see Layer 2 below).

### Layer 2 — Context Graph (Neo4j)
- **Graph writer** (`app/graphdb/writer.py`) projects each case's `source_jsons`
  into Neo4j: `Company`, `Director`, `GSTEntity`, `BankAccount`, `BureauProfile`,
  `FinancialsSnapshot`, `LedgerSnapshot` nodes, joined by `HAS_DIRECTOR`,
  `FILED_GST`, `HOLDS_ACCOUNT`, `HAS_BUREAU_PROFILE`, `REPORTED_FINANCIALS`,
  `REPORTED_LEDGER`.
- **Trust-weight calculator** (`app/layer2/trust_weights.py`) — pure Python,
  no DB dependency — computes pairwise variance between independently-sourced
  turnover figures (GST vs Bank, Bank vs Financials, GST vs Ledger) and maps
  variance to a 0–1 trust weight.
- **Related-party detection** (`app/graphdb/queries.py::find_related_parties`)
  — a one-hop Cypher query that finds other companies sharing a director.
  This is the concrete payoff of using a graph DB: the same lookup would be a
  much uglier multi-join in a relational schema.
- Both jobs run as parallel LangGraph nodes (`app/graph/layer2_graph.py`),
  writing into the same shared `AppState.trust_weights` / `AppState.evidence_map`.

**Honest scope limitation**: Layer 1's bureau/financials/ledger agents return
case-level *aggregates*, not itemized loans/invoices/counterparties. So the
diagram's `Loan`/`Invoice`/`Supplier`/`Customer` node types and `OWES_DEBT` /
`SUPPLIES_TO` relationships aren't populated yet — `BureauProfile` /
`FinancialsSnapshot` / `LedgerSnapshot` stand in for them. Extending Layer 1
to itemized extraction (per-invoice, per-loan) is the natural way to unlock
those later. `RELATED_PARTY` *is* real today, derived from shared directors.

### Layer 3 — Triangulation Engine ("the brain")
- **Trust aggregation** (`app/layer3/trust_aggregation.py`) collapses Layer 2's
  three pairwise comparisons into one trust weight per turnover-bearing
  source (`{gst: 0.9, bank: 0.88, financials: ..., ledger: ...}`) — exactly
  the `trust_weights` shape in the diagram's Layer 3 output example.
- **Effective metrics** (`app/layer3/effective_metrics.py`) computes:
  - `effective_turnover` — a confidence-weighted average of the four
    turnover claims (GST/bank/financials/ledger), weighted by the
    aggregated trust weights above.
  - `confidence` — mean trust weight across all pairwise comparisons.
  - `working_capital_gap` — the lower of two named methods: the **Nayak
    Committee turnover method** (20% of effective turnover, the standard
    simplified Indian-bank approach for SME WC limits) and an **operating
    cycle cross-check** ((debtor_days/365)×turnover − (creditor_days/365)×purchases).
    We don't have a current-asset/liability breakup yet, so the
    Tandon/MPBF method isn't used — this is flagged in code, not hidden.
  - `repayment_capacity` and `current_dscr` — derived from EBITDA against
    an estimated existing debt-service load (bureau exposure × an assumed
    annual service rate, since itemized loan tenor/rate isn't extracted yet).
- **Fraud + contradiction detection** (`app/layer3/fraud_signals.py`):
  - *Contradictions* — any Layer 2 pairwise variance above 15%, reported
    as plain numeric disagreements (no intent implied).
  - *Fraud signals* — pattern-based flags with severity: high cash deposits,
    excessive cheque bounces, bank-turnover-inflation-vs-GST, GST compliance
    status, bureau write-offs/severe DPD, anchor concentration, **plus two
    Neo4j graph traversals** — shared directorship (`find_related_parties`,
    reused from Layer 2) and shared bank account across two "independent"
    applicants (`find_shared_bank_accounts`, new) — the literal "Fraud:
    Neo4j traversal" line from the diagram.
  - `fraud_risk` (`low`/`medium`/`high`) is a simple roll-up: any high
    severity signal → high; any medium → medium; else low.
- Implemented as a LangGraph with one **sequential** branch (trust
  aggregation → effective metrics, since the second needs the first's
  output) running in parallel with an **independent** fraud-detection node.

`generate_linked_pair()` now optionally forces a shared bank account too (on
by default), so the demo case pair lights up *both* graph-traversal fraud
signals, not just related-party.

### Frontend
- Six agents rendered as a literal pipeline rail, per-agent result cards,
  raw-document viewer, audit trail (Layer 1).
- Trust-weight cards, a radial graph visualization of a company's Neo4j
  neighbourhood, and a related-parties panel (Layer 2).
- Effective-metrics stat cards (turnover, confidence, WC gap, repayment
  capacity, DSCR, fraud risk) and a fraud-signals/contradictions panel (Layer 3).
- A case selector to reload any previously generated/processed case, and a
  "Generate linked pair" button that creates two cases sharing a director
  (and, by default, a bank account) so you can see both related-party
  detection and the shared-banking-instrument fraud signal fire together.

## Why these tools, specifically

- **Groq + Llama 3.3 70B** (configurable): free, fast, no card required.
  `GROQ_MODEL` / `GROQ_FALLBACK_MODEL` are env vars — swap if Groq deprecates
  a model name. No Claude/OpenAI/Gemini calls anywhere.
- **LangGraph over plain function calls**: Layer 1's agents are independent;
  Layer 2's two jobs are independent of each other too — but Layer 3 *will*
  depend on both, so building on `StateGraph` from day one means no rewrite
  later.
- **Neo4j** for the context graph: relationships (shared directors, shared
  bank accounts across companies, etc.) are first-class and queryable in one
  hop, which is the whole point of Layer 2.
- **In-memory case store** (`app/store.py`) — swap-in point for Redis/Postgres
  is isolated to that one file. Neo4j itself is already a real, persistent
  store for the graph; only the *case scratch state* is in-memory.

## Setup

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: paste your free Groq key (https://console.groq.com) and your
# Neo4j URI/user/password (whatever you already have running)
uvicorn app.main:app --reload --port 8000
```

On startup the app calls `ensure_constraints()` (idempotent) to set up Neo4j
uniqueness constraints. If Neo4j isn't reachable yet, it logs a warning
instead of crashing — check `GET /api/layer2/health` to confirm connectivity.

Smoke test:

```bash
curl -X POST localhost:8000/api/layer1/cases -H "Content-Type: application/json" -d '{"scenario":"clean"}'
# copy the returned case_id, then:
curl -X POST localhost:8000/api/layer1/cases/<case_id>/run
curl -X POST localhost:8000/api/layer2/cases/<case_id>/run
curl localhost:8000/api/layer2/cases/<case_id>/graph
curl -X POST localhost:8000/api/layer3/cases/<case_id>/run
```

Related-party + shared-bank-account demo:

```bash
curl -X POST localhost:8000/api/layer1/cases/linked-pair -H "Content-Type: application/json" -d '{"scenario":"clean"}'
# run Layer 1 + 2 + 3 on BOTH returned case_ids, then:
curl localhost:8000/api/layer2/cases/<either_case_id>/related-parties
curl -X POST localhost:8000/api/layer3/cases/<either_case_id>/run   # fraud_signals should include
                                                                      # related_party_exposure AND
                                                                      # shared_banking_instrument
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env   # only needed if your backend isn't on localhost:8000
npm run dev
```

Open the printed localhost URL (default `http://localhost:5173`).

> I built and syntax-checked every file in this sandbox, but couldn't actually
> `pip install` / `npm install` / run the servers or hit a real Neo4j/Groq
> endpoint here — this environment has no network access. Run the smoke
> tests above after `pip install` to confirm everything wires up correctly
> on your machine, especially the Cypher queries against your actual Neo4j
> version.

## API reference

### Layer 1
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/layer1/cases` | Generate a synthetic applicant case (`{"scenario": "clean"\|"noisy"\|"fraud_risk"}`) |
| POST | `/api/layer1/cases/linked-pair` | Generate two cases sharing one director (related-party demo) |
| GET | `/api/layer1/cases` | List stored cases |
| GET | `/api/layer1/cases/{case_id}` | Fetch a case's current state |
| POST | `/api/layer1/cases/{case_id}/run` | Run all 6 agents, return updated `AppState` |

### Layer 2
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/layer2/health` | Check Neo4j connectivity |
| POST | `/api/layer2/cases/{case_id}/run` | Write source_jsons into Neo4j + compute trust weights |
| GET | `/api/layer2/cases/{case_id}/graph` | One-hop graph neighbourhood of the case's Company node |
| GET | `/api/layer2/cases/{case_id}/related-parties` | Other companies sharing a director |

### Layer 3
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/layer3/cases/{case_id}/run` | Aggregate trust weights → effective metrics; run fraud/contradiction detection |

## A note on rate limits

Groq's free tier is generous but capped per-model (roughly 30 RPM / 1,000
RPD on `llama-3.3-70b-versatile` as of mid-2026). Running Layer 1 once = 6
calls; Layer 2 makes none (it's pure Python + Cypher). If you start hammering
Groq, point `GROQ_MODEL` at `llama-3.1-8b-instant` or add a small delay
between calls.

## Roadmap — next layers

1. **Layer 4 (Policy/BRE)** and **Layer 5 (ML Risk Scoring)** can be built in
   parallel — both are independent consumers of Layer 3's `effective_metrics`
   (DSCR, effective turnover, fraud_risk) and `fraud_signals`. Layer 4's hard
   rules (DSCR > 1.25, GST vintage > 12 months, anchor concentration < 70%,
   etc.) map directly onto fields we already compute. For Layer 5, your
   Amex-default-style placeholder dataset is a fine starting point — same
   row/column schema as the real model you'll swap in later.
2. **Layer 6 (Sanction/Limit)** and the **Output dashboard** close the loop.

Say go whenever you're ready for Layer 4 (and/or 5).
