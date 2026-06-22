function fmtInr(n) {
  if (n === null || n === undefined || n === 0) return n === 0 ? "Rs 0" : "—";
  if (n >= 10_000_000) return `Rs ${(n / 10_000_000).toFixed(2)} Cr`;
  if (n >= 100_000) return `Rs ${(n / 100_000).toFixed(2)} L`;
  return `Rs ${n.toLocaleString("en-IN")}`;
}

const CONSTRAINT_LABELS = {
  C1_policy_cap_20pct_turnover: { label: "C1 — Policy cap (20% of turnover)", color: "var(--accent-running)" },
  C2_working_capital_need:      { label: "C2 — Working capital need",           color: "#5fb0e8" },
  C3_repayment_capacity:        { label: "C3 — Repayment capacity",             color: "var(--accent-valid)" },
  C4_risk_appetite_adjusted:    { label: "C4 — Risk appetite adjusted",         color: "var(--accent-warn)" },
  C5_exposure_headroom:         { label: "C5 — Exposure headroom",              color: "#b783f0" },
};

export default function SanctionPanel({ recommendedLimit, limitOptimizerResult, policyDecision }) {
  if (recommendedLimit === null || recommendedLimit === undefined) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No sanction computed yet — run Layer 6.
      </div>
    );
  }

  const constraints = limitOptimizerResult?.constraints || {};
  const binding = limitOptimizerResult?.binding_constraint;
  const maxConstraint = Math.max(...Object.values(constraints).filter(Boolean), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Big number */}
      <div style={{
        padding: "20px 24px",
        borderRadius: 10,
        background: recommendedLimit > 0 ? "rgba(79,209,197,0.07)" : "rgba(242,84,91,0.07)",
        border: `1px solid ${recommendedLimit > 0 ? "rgba(79,209,197,0.3)" : "rgba(242,84,91,0.3)"}`,
      }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", marginBottom: 6 }}>
          Recommended Sanction Limit
        </div>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 32,
          color: recommendedLimit > 0 ? "var(--accent-valid)" : "var(--accent-error)" }}>
          {fmtInr(recommendedLimit)}
        </div>
        {limitOptimizerResult?.note && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--text-muted)", marginTop: 8 }}>
            {limitOptimizerResult.note}
          </div>
        )}
        {limitOptimizerResult?.risk_multiplier !== undefined && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)", marginTop: 4 }}>
            Risk multiplier applied: {(limitOptimizerResult.risk_multiplier * 100).toFixed(0)}%
          </div>
        )}
      </div>

      {/* Constraint waterfall */}
      {Object.keys(constraints).length > 0 && (
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", marginBottom: 10 }}>
            Constraint waterfall
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {Object.entries(constraints).map(([key, val]) => {
              const cfg = CONSTRAINT_LABELS[key] || { label: key, color: "var(--text-faint)" };
              const isBinding = key === binding;
              const barPct = maxConstraint > 0 ? Math.round((val / maxConstraint) * 100) : 0;
              return (
                <div key={key} style={{
                  padding: "8px 12px",
                  borderRadius: 7,
                  background: isBinding ? "rgba(124,140,248,0.06)" : "var(--panel)",
                  border: `1px solid ${isBinding ? "rgba(124,140,248,0.35)" : "var(--border)"}`,
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5, fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
                    <span style={{ color: isBinding ? "var(--accent-running)" : "var(--text-muted)" }}>
                      {cfg.label} {isBinding && "← binding"}
                    </span>
                    <span style={{ color: "var(--text)" }}>{fmtInr(val)}</span>
                  </div>
                  <div style={{ height: 3, borderRadius: 2, background: "var(--border-soft)", overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${barPct}%`, background: isBinding ? "var(--accent-running)" : cfg.color, borderRadius: 2 }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
