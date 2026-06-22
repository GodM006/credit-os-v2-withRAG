const BANDS = [
  { lo: 1,  hi: 19, label: "E",  color: "#f2545b" },
  { lo: 20, hi: 39, label: "D",  color: "#f5a623" },
  { lo: 40, hi: 59, label: "C",  color: "#f0c040" },
  { lo: 60, hi: 74, label: "B",  color: "#7ce38b" },
  { lo: 75, hi: 83, label: "A",  color: "#4fd1c5" },
];

function scoreColor(score) {
  const band = BANDS.find((b) => score >= b.lo && score <= b.hi);
  return band ? band.color : "#8893a6";
}

function arc(cx, cy, r, startDeg, endDeg) {
  const toRad = (d) => ((d - 90) * Math.PI) / 180;
  const x1 = cx + r * Math.cos(toRad(startDeg));
  const y1 = cy + r * Math.sin(toRad(startDeg));
  const x2 = cx + r * Math.cos(toRad(endDeg));
  const y2 = cy + r * Math.sin(toRad(endDeg));
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
}

export default function RiskScoreGauge({ riskScore, pd, lgd, riskBand, expectedLossRate, modelName, trainedOn }) {
  if (riskScore === null || riskScore === undefined) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No ML score yet — run Layer 5.
      </div>
    );
  }

  const cx = 110, cy = 100, r = 78;
  // Score 1-83 mapped to 0-270 degrees (arc from -135° to 135°)
  const startDeg = -135;
  const totalDeg = 270;
  const scoreDeg = startDeg + ((riskScore - 1) / 82) * totalDeg;
  const color = scoreColor(riskScore);

  return (
    <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "flex-start" }}>
      {/* Gauge */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        <svg viewBox="0 0 220 160" style={{ width: 220, height: 160 }}>
          {/* Track */}
          <path d={arc(cx, cy, r, -135, 135)} fill="none" stroke="var(--border)" strokeWidth="10" strokeLinecap="round" />
          {/* Filled arc */}
          {riskScore > 1 && (
            <path d={arc(cx, cy, r, -135, scoreDeg)} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round" />
          )}
          {/* Band tick labels */}
          {BANDS.map((b) => {
            const midScore = (b.lo + b.hi) / 2;
            const deg = startDeg + ((midScore - 1) / 82) * totalDeg;
            const rad = ((deg - 90) * Math.PI) / 180;
            const lx = cx + (r + 18) * Math.cos(rad);
            const ly = cy + (r + 18) * Math.sin(rad);
            return (
              <text key={b.label} x={lx} y={ly} fill={b.color} fontSize="10" fontFamily="var(--font-mono)"
                textAnchor="middle" dominantBaseline="middle" fontWeight="600">{b.label}</text>
            );
          })}
          {/* Center score */}
          <text x={cx} y={cy - 8} fill={color} fontSize="36" fontFamily="var(--font-display)"
            textAnchor="middle" dominantBaseline="middle" fontWeight="700">{riskScore}</text>
          <text x={cx} y={cy + 24} fill="var(--text-faint)" fontSize="10" fontFamily="var(--font-mono)"
            textAnchor="middle">/ 83</text>
          <text x={cx} y={cy + 42} fill="var(--text-muted)" fontSize="11" fontFamily="var(--font-mono)"
            textAnchor="middle">{(riskBand || "").split("—")[1]?.trim() || riskBand}</text>
        </svg>
      </div>

      {/* Stats */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, flex: 1, minWidth: 180 }}>
        {[
          { label: "Probability of Default", value: pd !== null ? `${(pd * 100).toFixed(2)}%` : "—" },
          { label: "Loss Given Default", value: lgd !== null ? `${(lgd * 100).toFixed(1)}%` : "—" },
          { label: "Expected Loss Rate", value: expectedLossRate !== null ? `${(expectedLossRate * 100).toFixed(2)}%` : "—" },
          { label: "Risk band", value: riskBand || "—" },
          { label: "Model", value: modelName || "—" },
          { label: "Trained on", value: trainedOn || "—" },
        ].map(({ label, value }) => (
          <div key={label} className="kv-row" style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
            <span className="kv-key">{label}</span>
            <span className="kv-val">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
