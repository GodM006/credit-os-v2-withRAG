export default function RelatedPartiesList({ relatedParties }) {
  const list = relatedParties?.related_parties || [];

  if (list.length === 0) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No related parties found — no other company in the graph shares a director
        with this one. Use "Generate linked pair" to create two cases that
        deliberately share a director and see this populate.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {list.map((rp) => (
        <div className="card" key={rp.cin} style={{ gap: 6 }}>
          <div className="card-header">
            <div className="card-title" style={{ textTransform: "none" }}>{rp.legal_name}</div>
            <span className="badge" style={{ color: "var(--accent-warn)", borderColor: "var(--accent-warn)", background: "rgba(245,166,35,0.12)" }}>
              related party
            </span>
          </div>
          <div className="kv-list">
            <div className="kv-row">
              <span className="kv-key">CIN</span>
              <span className="kv-val">{rp.cin}</span>
            </div>
            <div className="kv-row">
              <span className="kv-key">shared director(s)</span>
              <span className="kv-val">{(rp.shared_directors || []).join(", ")}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
