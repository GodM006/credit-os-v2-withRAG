function formatVal(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    return Math.abs(v) >= 1000 ? v.toLocaleString("en-IN") : String(v);
  }
  if (Array.isArray(v)) {
    if (v.length === 0) return "none";
    if (typeof v[0] === "object") return `${v.length} record(s)`;
    return v.join(", ");
  }
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

const FIELD_LABELS = {
  inferred_annual_turnover: "Annual turnover",
  avg_monthly_balance: "Avg monthly balance",
  cash_deposit_ratio: "Cash deposit ratio",
  bounce_count: "Bounces (12m)",
  gstr3b_annual_turnover: "Turnover (GSTR-3B)",
  gstr1_annual_turnover: "Turnover (GSTR-1)",
  vintage_months: "GST vintage (months)",
  filing_status: "Filing status",
  bureau_score: "Bureau score",
  dpd_90_plus: "90+ DPD accounts",
  enquiries_last_6m: "Enquiries (6m)",
  total_exposure: "Total exposure",
  debt_equity_ratio: "Debt/Equity",
  net_worth: "Net worth",
  is_audited: "Audited",
  debtor_days: "Debtor days",
  top_debtor_concentration_pct: "Top debtor conc. (%)",
  kyc_doc_status: "KYC docs",
  directors: "Directors",
};

function pickDisplayFields(data) {
  // show a curated subset (first ~6 scalar-ish fields) rather than the full schema
  const keys = Object.keys(data);
  return keys.slice(0, 7);
}

export default function AgentCard({ label, status, result }) {
  const isPending = !result;
  const data = result?.data;

  return (
    <div className="card">
      <div className="card-header">
        <div className="card-title">{label}</div>
        <span className={`badge ${status}`}>
          {status === "idle" ? "pending" : status === "running" ? "running" : status.replace("_", " ")}
        </span>
      </div>

      {!isPending && data && (
        <>
          <div className="confidence-bar">
            <div className="confidence-fill" style={{ width: `${Math.round(result.confidence * 100)}%` }} />
          </div>
          <div className="kv-list">
            {pickDisplayFields(data).map((k) => (
              <div className="kv-row" key={k}>
                <span className="kv-key">{FIELD_LABELS[k] || k}</span>
                <span className="kv-val">{formatVal(data[k])}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {!isPending && !data && (
        <div className="kv-list">
          <div className="kv-row"><span className="kv-key">extraction</span><span className="kv-val">failed</span></div>
        </div>
      )}

      {isPending && (
        <div className="kv-list">
          <span className="kv-key" style={{ fontStyle: "italic" }}>waiting to run…</span>
        </div>
      )}

      {!isPending && result.issues?.length > 0 && (
        <div className="issues-list">
          {result.issues.slice(0, 3).map((iss, idx) => (
            <div className="issue-row" key={idx}>
              <span className={`issue-dot ${iss.severity}`} />
              <span>{iss.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
