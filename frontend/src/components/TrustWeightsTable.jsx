const PAIR_LABELS = {
  gst_vs_bank: "GST vs Bank",
  bank_vs_financials: "Bank vs Financials",
  gst_vs_ledger: "GST vs Ledger",
};

function fmt(n) {
  return typeof n === "number" ? n.toLocaleString("en-IN") : n;
}

export default function TrustWeightsTable({ trustWeights }) {
  const pairwise = trustWeights?.pairwise || {};
  const entries = Object.entries(pairwise);

  if (entries.length === 0) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No pairwise comparisons available — at least two of GST/Bank/Financials/Ledger
        extractions failed or are missing.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {entries.map(([key, p]) => (
        <div key={key} className="card" style={{ gap: 8 }}>
          <div className="card-header">
            <div className="card-title" style={{ textTransform: "none" }}>{PAIR_LABELS[key] || key}</div>
            <span
              className="badge"
              style={{
                color: p.trust_weight >= 0.85 ? "var(--accent-valid)" : p.trust_weight >= 0.6 ? "var(--accent-warn)" : "var(--accent-error)",
                borderColor: "currentColor",
                background: "transparent",
              }}
            >
              trust {p.trust_weight}
            </span>
          </div>
          <div className="kv-list">
            <div className="kv-row"><span className="kv-key">{p.label_a}</span><span className="kv-val">₹{fmt(p.value_a)}</span></div>
            <div className="kv-row"><span className="kv-key">{p.label_b}</span><span className="kv-val">₹{fmt(p.value_b)}</span></div>
            <div className="kv-row"><span className="kv-key">variance</span><span className="kv-val">{(p.variance_pct * 100).toFixed(1)}%</span></div>
          </div>
          <div className="confidence-bar">
            <div
              className="confidence-fill"
              style={{
                width: `${Math.round(p.trust_weight * 100)}%`,
                background: p.trust_weight >= 0.85 ? "var(--accent-valid)" : p.trust_weight >= 0.6 ? "var(--accent-warn)" : "var(--accent-error)",
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
