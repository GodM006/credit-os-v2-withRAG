const DECISION_CONFIG = {
  clear: {
    label: "POLICY CLEAR",
    color: "var(--accent-valid)",
    bg: "rgba(79,209,197,0.08)",
    border: "rgba(79,209,197,0.3)",
    note: "All hard eligibility rules passed. Case proceeds to risk scoring.",
  },
  deviation_required: {
    label: "DEVIATION REQUIRED",
    color: "var(--accent-warn)",
    bg: "rgba(245,166,35,0.08)",
    border: "rgba(245,166,35,0.3)",
    note: "1–2 rules failed. Escalate for credit committee / human override before proceeding.",
  },
  policy_reject: {
    label: "POLICY REJECT",
    color: "var(--accent-error)",
    bg: "rgba(242,84,91,0.08)",
    border: "rgba(242,84,91,0.3)",
    note: "3+ rules failed. Case does not qualify for standard credit — decline or refer to special programme.",
  },
};

function fmtValue(v, threshold) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number" && threshold !== undefined && typeof threshold === "number") {
    if (threshold < 5) return v.toFixed(2);
    return v.toLocaleString("en-IN");
  }
  return String(v);
}

function fmtThreshold(threshold, ruleId) {
  if (threshold === null || threshold === undefined) return "—";
  if (ruleId === "anchor_concentration_max") return `< ${threshold}%`;
  if (ruleId === "max_dpd_30") return `= ${threshold}`;
  if (typeof threshold === "number" && threshold < 5) return `> ${threshold}`;
  if (typeof threshold === "number") return `> ${threshold.toLocaleString("en-IN")}`;
  return String(threshold);
}

export default function PolicyDecisionPanel({ policySummary }) {
  if (!policySummary || !policySummary.policy_decision) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No policy evaluation yet — run Layer 4.
      </div>
    );
  }

  const cfg = DECISION_CONFIG[policySummary.policy_decision] || DECISION_CONFIG.policy_reject;
  const rules = policySummary.rule_results || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Decision banner */}
      <div style={{
        padding: "18px 20px",
        borderRadius: 10,
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 12,
      }}>
        <div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: 20, color: cfg.color }}>
            {cfg.label}
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
            {cfg.note}
          </div>
        </div>
        <div style={{ display: "flex", gap: 20, fontFamily: "var(--font-mono)", fontSize: 12 }}>
          <div style={{ textAlign: "center" }}>
            <div style={{ color: "var(--accent-valid)", fontWeight: 600, fontSize: 24 }}>
              {policySummary.passed_rules}
            </div>
            <div style={{ color: "var(--text-faint)" }}>passed</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ color: "var(--accent-error)", fontWeight: 600, fontSize: 24 }}>
              {policySummary.total_rules - policySummary.passed_rules}
            </div>
            <div style={{ color: "var(--text-faint)" }}>failed</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={{ color: cfg.color, fontWeight: 600, fontSize: 24 }}>
              {policySummary.rule_pass_rate}%
            </div>
            <div style={{ color: "var(--text-faint)" }}>pass rate</div>
          </div>
        </div>
      </div>

      {/* Per-rule breakdown */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {rules.map((rule) => (
          <div
            key={rule.rule_id}
            style={{
              display: "grid",
              gridTemplateColumns: "24px 1fr auto auto",
              gap: "0 12px",
              alignItems: "center",
              padding: "10px 14px",
              borderRadius: 8,
              background: "var(--panel)",
              border: `1px solid ${rule.passed ? "var(--border)" : "rgba(242,84,91,0.25)"}`,
              fontFamily: "var(--font-mono)",
              fontSize: 12,
            }}
          >
            <span style={{ fontSize: 14, textAlign: "center" }}>{rule.passed ? "✓" : "✗"}</span>
            <div>
              <div style={{ color: rule.passed ? "var(--text-muted)" : "var(--text)", fontWeight: rule.passed ? 400 : 500 }}>
                {rule.label}
              </div>
              {rule.note && (
                <div style={{ color: "var(--text-faint)", fontSize: 11, marginTop: 2 }}>{rule.note}</div>
              )}
            </div>
            <div style={{ color: "var(--text-faint)", whiteSpace: "nowrap" }}>
              actual: <span style={{ color: rule.passed ? "var(--accent-valid)" : "var(--accent-error)" }}>
                {fmtValue(rule.value, rule.threshold)}
              </span>
            </div>
            <div style={{ color: "var(--text-faint)", whiteSpace: "nowrap" }}>
              required: {fmtThreshold(rule.threshold, rule.rule_id)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
