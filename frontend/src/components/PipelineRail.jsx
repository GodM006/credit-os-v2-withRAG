const AGENTS = [
  { key: "banking", label: "BANKING" },
  { key: "gst", label: "GST" },
  { key: "bureau", label: "BUREAU" },
  { key: "financials", label: "FINANCIALS" },
  { key: "ledger", label: "LEDGER" },
  { key: "kyc", label: "KYC" },
];

export default function PipelineRail({ statuses }) {
  return (
    <div className="rail">
      {AGENTS.map((agent, i) => {
        const status = statuses[agent.key] || "idle";
        return (
          <div key={agent.key} style={{ display: "flex", alignItems: "center", flex: i < AGENTS.length - 1 ? 1 : "0 0 auto" }}>
            <div className="rail-node">
              <div className={`rail-dot ${status}`} />
              <div className="rail-label">{agent.label}</div>
            </div>
            {i < AGENTS.length - 1 && <div className="rail-connector" />}
          </div>
        );
      })}
    </div>
  );
}

export { AGENTS };
