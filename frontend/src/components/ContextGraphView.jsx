const TYPE_COLORS = {
  Company: "var(--accent-running)",
  Director: "var(--accent-valid)",
  GSTEntity: "var(--accent-warn)",
  BankAccount: "#5fb0e8",
  BureauProfile: "var(--accent-error)",
  FinancialsSnapshot: "#b783f0",
  LedgerSnapshot: "#f0a3d0",
};

export default function ContextGraphView({ data }) {
  const nodes = data?.nodes || [];
  const edges = data?.edges || [];

  if (nodes.length === 0) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No graph data yet — run Layer 2 first.
      </div>
    );
  }

  const company = nodes.find((n) => n.type === "Company") || nodes[0];
  const others = nodes.filter((n) => n.id !== company.id);

  const width = 640, height = 420;
  const cx = width / 2, cy = height / 2;
  const radius = Math.min(170, 70 + others.length * 8);

  const positions = { [company.id]: { x: cx, y: cy } };
  others.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2;
    positions[n.id] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });

  const presentTypes = [...new Set(nodes.map((n) => n.type))];

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", maxHeight: 420 }}>
        {edges.map((e, i) => {
          const a = positions[e.source];
          const b = positions[e.target];
          if (!a || !b) return null;
          const midX = (a.x + b.x) / 2, midY = (a.y + b.y) / 2;
          return (
            <g key={i}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--border)" strokeWidth="1.5" />
              <text x={midX} y={midY} fontSize="9" fill="var(--text-faint)" fontFamily="var(--font-mono)" textAnchor="middle">
                {e.type}
              </text>
            </g>
          );
        })}
        {nodes.map((n) => {
          const pos = positions[n.id];
          if (!pos) return null;
          const isCompany = n.id === company.id;
          return (
            <g key={n.id}>
              <circle cx={pos.x} cy={pos.y} r={isCompany ? 16 : 10} style={{ fill: TYPE_COLORS[n.type] || "var(--accent-idle)" }} stroke="var(--bg)" strokeWidth="2" />
              <text
                x={pos.x}
                y={pos.y + (isCompany ? 30 : 22)}
                fontSize={isCompany ? "11" : "9.5"}
                fill="var(--text-muted)"
                fontFamily="var(--font-mono)"
                textAnchor="middle"
              >
                {String(n.label).slice(0, 22)}
              </text>
            </g>
          );
        })}
      </svg>
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginTop: 4 }}>
        {presentTypes.map((t) => (
          <div key={t} style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)" }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: TYPE_COLORS[t] || "var(--accent-idle)", display: "inline-block" }} />
            {t}
          </div>
        ))}
      </div>
    </div>
  );
}
