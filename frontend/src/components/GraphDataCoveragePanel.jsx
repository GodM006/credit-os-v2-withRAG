/**
 * GraphDataCoveragePanel — displays per-branch data availability from
 * evidence_map.graph_write.data_availability so the underwriter knows
 * *why* certain branches are absent from the graph, rather than seeing
 * a sparse graph with no explanation.
 */

const BRANCH_LABELS = {
  ledger_counterparties: "Ledger counterparties",
  bank_counterparties:   "Bank counterparties",
  loan_facilities:       "Loan facilities",
  personal_bureau:       "Personal CIBIL (Directors)",
};

const BRANCH_ORDER = [
  "ledger_counterparties",
  "bank_counterparties",
  "loan_facilities",
  "personal_bureau",
];

export default function GraphDataCoveragePanel({ graphWrite }) {
  const availability = graphWrite?.data_availability;
  if (!availability || Object.keys(availability).length === 0) return null;

  return (
    <div style={{
      marginTop: 12,
      padding: "10px 14px",
      background: "var(--panel)",
      border: "1px solid var(--border)",
      borderRadius: 6,
      fontFamily: "var(--font-mono)",
      fontSize: 11,
    }}>
      <div style={{
        color: "var(--text-faint)",
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        fontSize: 10,
        marginBottom: 8,
      }}>
        Graph data coverage
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {BRANCH_ORDER.filter((key) => availability[key] !== undefined).map((key) => {
          const branch = availability[key];
          const ok = branch.available;
          return (
            <div
              key={key}
              title={!ok && branch.reason ? branch.reason : `${branch.count ?? 0} node(s) written`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                padding: "3px 9px",
                borderRadius: 12,
                background: ok ? "rgba(79,209,197,0.10)" : "rgba(255,255,255,0.04)",
                border: `1px solid ${ok ? "var(--accent-valid)" : "var(--border)"}`,
                color: ok ? "var(--accent-valid)" : "var(--text-faint)",
                fontSize: 10,
                cursor: "default",
                userSelect: "none",
              }}
            >
              <span style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: ok ? "var(--accent-valid)" : "var(--border)",
                display: "inline-block",
                flexShrink: 0,
              }} />
              <span>{BRANCH_LABELS[key] || key}</span>
              {ok && branch.count !== undefined && (
                <span style={{ opacity: 0.7 }}>({branch.count})</span>
              )}
              {!ok && (
                <span style={{ opacity: 0.5 }}>— n/a</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
