import { useState } from "react";

const TYPE_COLORS = {
  Company:              "var(--accent-running)",
  Director:             "var(--accent-valid)",
  GSTEntity:            "var(--accent-warn)",
  BankAccount:          "#5fb0e8",
  BureauProfile:        "var(--accent-error)",
  FinancialsSnapshot:   "#b783f0",
  LedgerSnapshot:       "#f0a3d0",
  // Hop-2 node types
  Counterparty:         "#f0c040",
  LoanFacility:         "#e07050",
  PersonalBureauProfile:"#80c8ff",
};

const HOP1_TYPES = new Set([
  "Director", "GSTEntity", "BankAccount",
  "BureauProfile", "FinancialsSnapshot", "LedgerSnapshot",
]);

const WIDTH  = 720;
const HEIGHT = 520;
const CX     = WIDTH  / 2;
const CY     = HEIGHT / 2;
const R0     = 0;    // Company
const R1     = 155;  // hop-1 ring
const R2     = 280;  // hop-2 ring

/** Given a hop-1 node's angle and the set of hop-2 children, spread children
 *  in a small arc around the parent's angle so they cluster visually. */
function spreadAngles(parentAngle, count) {
  if (count === 0) return [];
  const spread = Math.min(Math.PI / 3, (count - 1) * 0.35); // max 60° arc
  const step   = count > 1 ? spread / (count - 1) : 0;
  const start  = parentAngle - spread / 2;
  return Array.from({ length: count }, (_, i) => start + i * step);
}

export default function ContextGraphView({ data }) {
  const [hovered, setHovered] = useState(null);
  const nodes = data?.nodes || [];
  const edges = data?.edges || [];

  if (nodes.length === 0) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No graph data yet — run Layer 2 first.
      </div>
    );
  }

  // ── Layout calculation ──────────────────────────────────────────────────────
  const company  = nodes.find((n) => n.hop === 0) || nodes.find((n) => n.type === "Company") || nodes[0];
  const hop1     = nodes.filter((n) => n.hop === 1 || (n.hop !== 0 && n.hop !== 2 && n.id !== company.id));
  const hop2     = nodes.filter((n) => n.hop === 2);

  const positions = {};
  positions[company.id] = { x: CX, y: CY };

  // Place hop-1 nodes evenly on inner ring
  const hop1Angles = {};
  hop1.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(hop1.length, 1) - Math.PI / 2;
    hop1Angles[n.id] = angle;
    positions[n.id] = {
      x: CX + R1 * Math.cos(angle),
      y: CY + R1 * Math.sin(angle),
    };
  });

  // Group hop-2 nodes by their parent_id
  const hop2ByParent = {};
  hop2.forEach((n) => {
    const pid = n.parent_id;
    if (!hop2ByParent[pid]) hop2ByParent[pid] = [];
    hop2ByParent[pid].push(n);
  });

  // Place hop-2 nodes in arc clusters near their parent's angle
  Object.entries(hop2ByParent).forEach(([parentId, children]) => {
    const parentAngle = hop1Angles[parentId] ?? 0;
    const angles = spreadAngles(parentAngle, children.length);
    children.forEach((n, i) => {
      positions[n.id] = {
        x: CX + R2 * Math.cos(angles[i]),
        y: CY + R2 * Math.sin(angles[i]),
      };
    });
  });

  // For hop-2 nodes whose parent is not a hop-1 node (e.g. parent is Company itself),
  // fall back to placing them evenly on the outer ring.
  const unpositioned = hop2.filter((n) => !positions[n.id]);
  unpositioned.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(unpositioned.length, 1) - Math.PI / 2;
    positions[n.id] = { x: CX + R2 * Math.cos(angle), y: CY + R2 * Math.sin(angle) };
  });

  const presentTypes = [...new Set(nodes.map((n) => n.type))];

  // ── Tooltip content ─────────────────────────────────────────────────────────
  const hoveredNode = hovered ? nodes.find((n) => n.id === hovered) : null;

  return (
    <div>
      {/* Ring labels */}
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} style={{ width: "100%", maxHeight: HEIGHT }}>
        {/* Faint ring guides */}
        <circle cx={CX} cy={CY} r={R1} fill="none" stroke="var(--border)" strokeWidth="0.5" strokeDasharray="4 4" opacity="0.4" />
        <circle cx={CX} cy={CY} r={R2} fill="none" stroke="var(--border)" strokeWidth="0.5" strokeDasharray="4 4" opacity="0.25" />

        {/* Edges */}
        {edges.map((e, i) => {
          const a = positions[e.source];
          const b = positions[e.target];
          if (!a || !b) return null;
          const midX = (a.x + b.x) / 2;
          const midY = (a.y + b.y) / 2;
          const isHop2Edge = !!(
            nodes.find((n) => n.id === e.target && n.hop === 2) ||
            nodes.find((n) => n.id === e.source && n.hop === 2)
          );
          return (
            <g key={i}>
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke="var(--border)"
                strokeWidth={isHop2Edge ? "1" : "1.5"}
                strokeDasharray={isHop2Edge ? "3 3" : "none"}
                opacity={isHop2Edge ? 0.6 : 1}
              />
              <text
                x={midX} y={midY}
                fontSize="8" fill="var(--text-faint)"
                fontFamily="var(--font-mono)" textAnchor="middle"
                opacity="0.7"
              >
                {e.type}
              </text>
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map((n) => {
          const pos = positions[n.id];
          if (!pos) return null;
          const isCompany = n.hop === 0 || n.id === company.id;
          const isHop2    = n.hop === 2;
          const r = isCompany ? 18 : isHop2 ? 8 : 11;
          const color = TYPE_COLORS[n.type] || "var(--accent-idle)";
          const isHovered = hovered === n.id;

          return (
            <g
              key={n.id}
              style={{ cursor: "pointer" }}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}
            >
              {isHovered && (
                <circle
                  cx={pos.x} cy={pos.y} r={r + 5}
                  fill={color} opacity="0.15"
                />
              )}
              <circle
                cx={pos.x} cy={pos.y} r={r}
                style={{ fill: color }}
                stroke={isHovered ? "var(--text)" : "var(--bg)"}
                strokeWidth={isHovered ? "2.5" : "2"}
                opacity={isHop2 ? 0.85 : 1}
              />
              <text
                x={pos.x}
                y={pos.y + r + (isCompany ? 14 : 12)}
                fontSize={isCompany ? "11" : isHop2 ? "8.5" : "9.5"}
                fill={isHop2 ? "var(--text-faint)" : "var(--text-muted)"}
                fontFamily="var(--font-mono)"
                textAnchor="middle"
              >
                {String(n.label).slice(0, isHop2 ? 18 : 22)}
              </text>
            </g>
          );
        })}

        {/* Tooltip */}
        {hoveredNode && (() => {
          const pos = positions[hoveredNode.id];
          if (!pos) return null;
          const props = hoveredNode.props || {};
          const lines = Object.entries(props)
            .filter(([k, v]) => v !== null && v !== undefined && v !== "" && !["case_id", "ingested_at"].includes(k))
            .slice(0, 6);
          const ttWidth = 200, ttHeight = lines.length * 14 + 24;
          let ttX = pos.x + 14, ttY = pos.y - ttHeight / 2;
          if (ttX + ttWidth > WIDTH) ttX = pos.x - ttWidth - 14;
          if (ttY < 4) ttY = 4;
          if (ttY + ttHeight > HEIGHT) ttY = HEIGHT - ttHeight - 4;
          return (
            <g>
              <rect x={ttX} y={ttY} width={ttWidth} height={ttHeight} rx="4"
                fill="var(--panel)" stroke="var(--border)" strokeWidth="1" opacity="0.97" />
              <text x={ttX + 8} y={ttY + 14} fontSize="10" fontWeight="600"
                fill="var(--text)" fontFamily="var(--font-mono)">
                {hoveredNode.type}
              </text>
              {lines.map(([k, v], i) => (
                <text key={k} x={ttX + 8} y={ttY + 24 + i * 14}
                  fontSize="9" fill="var(--text-faint)" fontFamily="var(--font-mono)">
                  {k}: {String(v).slice(0, 22)}
                </text>
              ))}
            </g>
          );
        })()}
      </svg>

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 6 }}>
        {presentTypes.map((t) => (
          <div key={t} style={{ display: "flex", alignItems: "center", gap: 5,
            fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-faint)" }}>
            <span style={{
              width: 7, height: 7, borderRadius: "50%",
              background: TYPE_COLORS[t] || "var(--accent-idle)",
              display: "inline-block",
              opacity: HOP1_TYPES.has(t) || t === "Company" ? 1 : 0.75,
            }} />
            {t}
            {hop2.some((n) => n.type === t) && (
              <span style={{ fontSize: 9, opacity: 0.6 }}>· hop-2</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
