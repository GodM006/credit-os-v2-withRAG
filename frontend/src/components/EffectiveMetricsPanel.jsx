function fmtInr(n) {
  if (n === null || n === undefined) return "—";
  return `₹${n.toLocaleString("en-IN")}`;
}

const RISK_COLOR = {
  low: "var(--accent-valid)",
  medium: "var(--accent-warn)",
  high: "var(--accent-error)",
};

const STATS = [
  { key: "effective_turnover", label: "Effective turnover", fmt: fmtInr },
  { key: "confidence", label: "Confidence", fmt: (v) => (v === null ? "—" : `${Math.round(v * 100)}%`) },
  { key: "working_capital_gap", label: "Working capital gap", fmt: fmtInr },
  { key: "repayment_capacity", label: "Repayment capacity", fmt: fmtInr },
  { key: "current_dscr", label: "Current DSCR", fmt: (v) => (v === null || v === undefined ? "n/a (no existing debt)" : `${v}x`) },
];

export default function EffectiveMetricsPanel({ metrics }) {
  if (!metrics) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No effective metrics yet — run Layer 3.
      </div>
    );
  }

  return (
    <div>
      <div className="agent-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        {STATS.map((s) => (
          <div className="card" key={s.key} style={{ gap: 4 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
              {s.label}
            </div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: 18 }}>
              {s.fmt(metrics[s.key])}
            </div>
          </div>
        ))}
        <div className="card" style={{ gap: 4 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--text-faint)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Fraud risk
          </div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 18, color: RISK_COLOR[metrics.fraud_risk] || "var(--text)" }}>
            {(metrics.fraud_risk || "—").toUpperCase()}
          </div>
        </div>
      </div>

      {metrics.notes?.length > 0 && (
        <div className="issues-list" style={{ marginTop: 12, borderTop: "none", paddingTop: 0 }}>
          {metrics.notes.map((n, i) => (
            <div className="issue-row" key={i}>
              <span className="issue-dot warning" />
              <span>{n}</span>
            </div>
          ))}
        </div>
      )}

      {metrics.working_capital_gap_methods && (
        <div className="case-pill" style={{ marginTop: 10, display: "inline-block" }}>
          WC methods — turnover (20%): {fmtInr(metrics.working_capital_gap_methods.turnover_method_20pct)} · operating cycle: {fmtInr(metrics.working_capital_gap_methods.operating_cycle)}
        </div>
      )}
    </div>
  );
}
