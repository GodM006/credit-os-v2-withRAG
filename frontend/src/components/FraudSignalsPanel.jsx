const SEVERITY_COLOR = { high: "var(--accent-error)", medium: "var(--accent-warn)", low: "var(--accent-valid)" };

export default function FraudSignalsPanel({ fraudSignals, contradictions }) {
  const signals = fraudSignals || [];
  const conts = contradictions || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", marginBottom: 8 }}>
          Fraud signals ({signals.length})
        </div>
        {signals.length === 0 && (
          <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>None detected.</div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {signals.map((s, i) => (
            <div className="card" key={i} style={{ gap: 4 }}>
              <div className="card-header">
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 500 }}>{s.type.replace(/_/g, " ")}</span>
                <span className="badge" style={{ color: SEVERITY_COLOR[s.severity], borderColor: "currentColor", background: "transparent" }}>
                  {s.severity}
                </span>
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>{s.message}</div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase", marginBottom: 8 }}>
          Contradictions ({conts.length})
        </div>
        {conts.length === 0 && (
          <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>None above threshold.</div>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {conts.map((c, i) => (
            <div className="audit-row" key={i} style={{ flexWrap: "wrap" }}>
              <span>{c.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
