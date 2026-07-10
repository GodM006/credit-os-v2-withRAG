# Plan — Layer 2 Context Graph Decluttering

## Problem
The Layer 2 graph can look cluttered even for a **single** case. This is *not*
cross-case accumulation (verified: `Company:1`, one uniquely-keyed
`BankAccount`, all counterparties scoped to the case). It is legitimate data
density — a real SME's bank statement + ledger contain ~20+ distinct
counterparties, each rendered as a node — made worse by directional duplicates
and low-signal placeholder nodes.

## Root causes
1. **Directional duplicates** — each counterparty is written to Neo4j twice,
   once per transaction direction (`…:inflow` / `…:outflow`), with the same name
   and parent. Renders as duplicate labels (e.g. "muham med" ×2).
2. **Unbounded hop-2 fan-out** — every counterparty, loan facility, and enquiry
   is returned and drawn; nothing is capped.
3. **Placeholder nodes** — `NOT DISCLOSED` enquiries/facilities add noise
   without identity.

## Done
- [x] **Merge inflow/outflow duplicates** (commit `170c2c2`).
      `mergeDirectionalDuplicates()` in
      `frontend/src/components/ContextGraphView.jsx` collapses Counterparty nodes
      per `(parent_id, name)` and rewires edges. Purely visual; coverage counts
      unaffected. Verified: 22 → 17 counterparty nodes on the sample case.

## Remaining options (not yet implemented)
Pick based on how sparse the default view should be. All are view-layer changes
unless noted; none delete data, and the "Graph Data Coverage" panel keeps true
counts.

### A. Cap counterparties (top-N + "+N more")  — *recommended next*
- Render only the top ~8 counterparties per bank/ledger hub, ranked by
  transaction weight; roll the remainder into a single synthetic `+N more` node
  hanging off the same parent.
- **Where:** `ContextGraphView.jsx` (extend the existing `capNeighbors` helper),
  or push a `LIMIT` into the counterparty queries in
  `backend/app/graphdb/queries.py` (`get_bank_counterparties` /
  `get_ledger_counterparties`) if payload size matters.
- **Effort:** small. **Impact:** high — keeps hubs readable regardless of case size.

### B. Collapse counterparties behind a toggle
- Default the view to hop-0/1 (company + its direct entities: bank account,
  GST, bureau, snapshots, directors). Add an expand/collapse control per hub to
  reveal counterparties on demand.
- **Where:** `ContextGraphView.jsx` (add expansion state + a control on hub
  nodes); hop-2 nodes already carry `parent_id` for clustering.
- **Effort:** medium. **Impact:** highest — sparse by default, detail on demand.

### C. Hide `NOT DISCLOSED` placeholder nodes
- Filter out enquiry/facility nodes whose identity is a placeholder
  (`NOT DISCLOSED`, empty) before drawing.
- **Where:** `ContextGraphView.jsx` node filter, or skip them in
  `backend/app/graphdb/queries.py`.
- **Effort:** small. **Impact:** low–medium — removes noise, not core density.

## Notes / non-goals
- Do **not** address density by clearing Neo4j — the `⟲ Reset graph` button /
  `POST /api/admin/reset-graph` is for cross-case accumulation, a different
  concern.
- The `:inflow`/`:outflow` split is a *modeling* choice in
  `backend/app/graphdb/writer.py`; the frontend merge (done) papers over it for
  display. If we ever want one node at the data layer, dedupe at write time
  instead — but that loses per-direction amounts, so keep it view-only for now.
