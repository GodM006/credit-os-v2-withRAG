import { useState, useEffect, useRef } from "react";
import { api } from "./api";
import PipelineRail, { AGENTS } from "./components/PipelineRail";
import AgentCard from "./components/AgentCard";
import CollapsibleSection from "./components/CollapsibleSection";
import TrustWeightsTable from "./components/TrustWeightsTable";
import ContextGraphView from "./components/ContextGraphView";
import GraphDataCoveragePanel from "./components/GraphDataCoveragePanel";
import RelatedPartiesList from "./components/RelatedPartiesList";
import EffectiveMetricsPanel from "./components/EffectiveMetricsPanel";
import FraudSignalsPanel from "./components/FraudSignalsPanel";
import PolicyDecisionPanel from "./components/PolicyDecisionPanel";
import RiskScoreGauge from "./components/RiskScoreGauge";
import SanctionPanel from "./components/SanctionPanel";
import CreditMemoViewer from "./components/CreditMemoViewer";

// File slot definitions for the upload panel
const FILE_SLOTS = [
  { key: "consumer_cibil",   label: "Consumer CIBIL Report",    accept: ".pdf",        required: false, hint: "PDF" },
  { key: "commercial_cibil", label: "Commercial CIBIL Report",  accept: ".pdf",        required: false, hint: "PDF" },
  { key: "bank_statement_1", label: "Bank Statement 1",         accept: ".xlsx,.xls",  required: false, hint: "Excel" },
  { key: "bank_statement_2", label: "Bank Statement 2",         accept: ".xlsx,.xls",  required: false, hint: "Excel (optional)" },
  { key: "gst_json",         label: "GST Data",                 accept: ".json",       required: false, hint: "JSON" },
  { key: "financials",       label: "Financials / P&L",         accept: ".pdf,.xlsx",  required: false, hint: "PDF or Excel" },
  { key: "ledger",           label: "Sales & Purchase Ledger",  accept: ".pdf,.xlsx",  required: false, hint: "PDF or Excel" },
  { key: "kyc",              label: "KYC / Company Docs",       accept: ".pdf",        required: false, hint: "PDF" },
];

export default function App() {
  const [caseData, setCaseData] = useState(null);
  const [cases, setCases] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [uploadFiles, setUploadFiles] = useState({}); // { [slotKey]: File }
  const [uploadDone, setUploadDone] = useState(false);
  const [resettingGraph, setResettingGraph] = useState(false);

  const [layer2Running, setLayer2Running] = useState(false);
  const [layer2Error, setLayer2Error] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [relatedParties, setRelatedParties] = useState(null);
  const [relatedPartiesLoading, setRelatedPartiesLoading] = useState(false);

  const [layer3Running, setLayer3Running] = useState(false);
  const [layer3Error, setLayer3Error] = useState(null);

  const [layer4Running, setLayer4Running] = useState(false);
  const [layer4Error, setLayer4Error] = useState(null);

  const [layer5Running, setLayer5Running] = useState(false);
  const [layer5Error, setLayer5Error] = useState(null);

  const [layer6Running, setLayer6Running] = useState(false);
  const [layer6Error, setLayer6Error] = useState(null);

  useEffect(() => { refreshCaseList(); }, []);

  async function refreshCaseList() {
    try { setCases(await api.listCases()); } catch { /* non-fatal */ }
  }

  async function handleResetGraph() {
    if (!window.confirm(
      "Clear the entire Neo4j context graph? This deletes all companies, directors, " +
      "bank accounts and links written by every previous upload, so the next case starts " +
      "from an empty graph. In-memory cases are not affected."
    )) return;
    setResettingGraph(true);
    setError(null);
    try {
      const res = await api.resetGraph();
      setGraphData(null);
      setRelatedParties(null);
      setError(`Graph cleared — removed ${res.deleted_nodes} nodes and ${res.deleted_relationships} relationships.`);
    } catch (e) {
      setError(`Failed to reset graph: ${e.message}`);
    } finally {
      setResettingGraph(false);
    }
  }

  const statuses = {};
  AGENTS.forEach((a) => {
    if (running) statuses[a.key] = "running";
    else if (caseData?.source_jsons?.[a.key]) statuses[a.key] = caseData.source_jsons[a.key].validation_status;
    else statuses[a.key] = "idle";
  });

  const layer1Done = caseData && AGENTS.every((a) => caseData.source_jsons?.[a.key]);
  const layer2Done = !!caseData?.evidence_map?.graph_write;
  const layer2HasPairwise = !!(caseData?.trust_weights?.pairwise && Object.keys(caseData.trust_weights.pairwise).length > 0);
  const layer3Done = !!caseData?.effective_metrics?.fraud_risk;
  const layer4Done = !!caseData?.policy_summary?.policy_decision;
  const layer5Done = caseData?.risk_score !== null && caseData?.risk_score !== undefined;
  const layer6Done = caseData?.recommended_limit !== null && caseData?.recommended_limit !== undefined;

  function resetPanels() {
    setGraphData(null); setRelatedParties(null);
    setLayer2Error(null); setLayer3Error(null);
    setLayer4Error(null); setLayer5Error(null); setLayer6Error(null);
  }

  function handleFileSelect(slotKey, file) {
    setUploadFiles((prev) => ({ ...prev, [slotKey]: file }));
  }

  async function handleUpload() {
    const hasAny = Object.values(uploadFiles).some(Boolean);
    if (!hasAny) { setError("Please select at least one document to upload."); return; }
    setError(null);
    setUploading(true);
    setCaseData(null);
    resetPanels();
    try {
      const formData = new FormData();
      for (const [key, file] of Object.entries(uploadFiles)) {
        if (file) formData.append(key, file);
      }
      const result = await api.uploadCaseFiles(formData);
      setCaseData(result);
      setUploadDone(true);
      refreshCaseList();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  function handleNewUpload() {
    setUploadFiles({});
    setUploadDone(false);
    setCaseData(null);
    setError(null);
    resetPanels();
  }

  async function handleLoadCase(caseId) {
    if (!caseId) return;
    setError(null);
    resetPanels();
    try {
      const result = await api.getCase(caseId);
      setCaseData(result);
      setUploadDone(true);
      const cin = result?.evidence_map?.graph_write?.company_cin;
      if (cin) {
        const [graphResult, relatedResult] = await Promise.allSettled([
          api.getCaseGraph(caseId),
          api.getRelatedParties(caseId),
        ]);
        if (graphResult.status === "fulfilled") setGraphData(graphResult.value);
        if (relatedResult.status === "fulfilled") setRelatedParties(relatedResult.value);
      }
    } catch (e) { setError(e.message); }
  }

  async function handleRun() {
    if (!caseData) return;
    setError(null);
    setRunning(true);
    try {
      const result = await api.runCase(caseData.case_id);
      setCaseData(result);
    } catch (e) { setError(e.message); } finally { setRunning(false); }
  }

  async function handleRunLayer2() {
    if (!caseData) return;
    setLayer2Error(null); setLayer2Running(true);
    try {
      const result = await api.runLayer2(caseData.case_id);
      setCaseData(result);
      const cin = result?.evidence_map?.graph_write?.company_cin;
      if (cin) {
        const [graph, related] = await Promise.all([
          api.getCaseGraph(caseData.case_id),
          api.getRelatedParties(caseData.case_id),
        ]);
        setGraphData(graph); setRelatedParties(related);
      }
    } catch (e) { setLayer2Error(e.message); } finally { setLayer2Running(false); }
  }

  async function handleCheckRelatedParties() {
    if (!caseData) return;
    setRelatedPartiesLoading(true);
    try { setRelatedParties(await api.getRelatedParties(caseData.case_id)); }
    catch (e) { setLayer2Error(e.message); } finally { setRelatedPartiesLoading(false); }
  }

  async function handleRunLayer3() {
    if (!caseData) return;
    setLayer3Error(null); setLayer3Running(true);
    try { const result = await api.runLayer3(caseData.case_id); setCaseData(result); }
    catch (e) { setLayer3Error(e.message); } finally { setLayer3Running(false); }
  }

  async function handleRunLayer4() {
    if (!caseData) return;
    setLayer4Error(null); setLayer4Running(true);
    try { const result = await api.runLayer4(caseData.case_id); setCaseData(result); }
    catch (e) { setLayer4Error(e.message); } finally { setLayer4Running(false); }
  }

  async function handleRunLayer5() {
    if (!caseData) return;
    setLayer5Error(null); setLayer5Running(true);
    try { const result = await api.runLayer5(caseData.case_id); setCaseData(result); }
    catch (e) { setLayer5Error(e.message); } finally { setLayer5Running(false); }
  }

  async function handleRunLayer6() {
    if (!caseData) return;
    setLayer6Error(null); setLayer6Running(true);
    try { const result = await api.runLayer6(caseData.case_id); setCaseData(result); }
    catch (e) { setLayer6Error(e.message); } finally { setLayer6Running(false); }
  }

  return (
    <div className="app-shell">
      {/* ── HEADER ───────────────────────────────────────── */}
      <div className="app-header">
        <div>
          <div className="app-title">
            Credit Decisioning OS
            <span className="layer-tag">LAYERS 1–6</span>
          </div>
          <div className="app-subtitle">
            {caseData
              ? `case ${caseData.case_id} · ${caseData.company_name}`
              : "upload documents to begin"}
          </div>
        </div>
        <div className="controls">
          {cases.length > 0 && (
            <select
              value={caseData?.case_id || ""}
              onChange={(e) => handleLoadCase(e.target.value)}
              disabled={uploading || running || layer2Running}
            >
              <option value="" disabled>Load existing case…</option>
              {cases.map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id} · {c.company_name} ({c.scenario})
                </option>
              ))}
            </select>
          )}
          {uploadDone && (
            <button onClick={handleNewUpload} disabled={uploading || running}>
              ＋ New upload
            </button>
          )}
          <button
            onClick={handleResetGraph}
            disabled={resettingGraph || layer2Running}
            title="Wipe the shared Neo4j context graph so the next upload starts clean"
          >
            {resettingGraph ? "Clearing…" : "⟲ Reset graph"}
          </button>
        </div>
      </div>

      {/* ── GLOBAL ERROR ─────────────────────────────────── */}
      {error && (
        <div className="card" style={{ borderColor: "var(--accent-error)", marginBottom: 20 }}>
          <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{error}</span>
        </div>
      )}

      {/* ── UPLOAD PANEL (shown until files are uploaded) ── */}
      {!uploadDone && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="layer-heading" style={{ marginBottom: 16 }}>
            <span className="layer-tag">UPLOAD</span> Loan Application Documents
          </div>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: "14px",
            marginBottom: "20px"
          }}>
            {FILE_SLOTS.map((slot) => (
              <FileSlot
                key={slot.key}
                slot={slot}
                file={uploadFiles[slot.key] || null}
                onSelect={(file) => handleFileSelect(slot.key, file)}
              />
            ))}
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button
              className="primary"
              onClick={handleUpload}
              disabled={uploading}
              style={{ minWidth: 160 }}
            >
              {uploading ? "Parsing & uploading…" : "Upload & Create Case"}
            </button>
            <span style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
              At least one document required · CIBIL PDFs, Excel bank statements, GST JSON
            </span>
          </div>
        </div>
      )}

      {/* ── EMPTY STATE ──────────────────────────────────── */}
      {!caseData && !error && uploadDone && (
        <div className="empty-state">
          Case created. Run Layer 1 to extract structured data from your uploaded documents.
        </div>
      )}

      {/* ── PIPELINE ─────────────────────────────────────── */}
      {caseData && (
        <>
          {/* LAYER 1 */}
          <div className="layer-heading-row">
            <div className="layer-heading" style={{ margin: 0 }}>
              <span className="layer-tag">LAYER 1</span> Data Acquisition Agents
            </div>
            <button className="primary" onClick={handleRun} disabled={running || uploading}>
              {running ? "Running agents…" : "Run Layer 1"}
            </button>
          </div>

          <PipelineRail statuses={statuses} />

          <div className="agent-grid">
            {AGENTS.map((a) => (
              <AgentCard
                key={a.key}
                label={a.label.toLowerCase()}
                status={statuses[a.key]}
                result={caseData.source_jsons?.[a.key]}
              />
            ))}
          </div>

          <CollapsibleSection title="Parsed document text (uploaded input)">
            <div className="doc-grid">
              {AGENTS.map((a) => (
                <div className="doc-box" key={a.key}>
                  <div className="doc-box-title">{a.label}</div>
                  <pre>{caseData.raw_docs?.[a.key]
                    ? caseData.raw_docs[a.key].slice(0, 2000) + (caseData.raw_docs[a.key].length > 2000 ? "\n\n… [truncated for display]" : "")
                    : "(no document uploaded for this source)"}
                  </pre>
                </div>
              ))}
            </div>
          </CollapsibleSection>

          {/* LAYER 2 */}
          <div className="layer-heading-row">
            <div className="layer-heading" style={{ margin: 0 }}>
              <span className="layer-tag">LAYER 2</span> Context Graph (Neo4j)
            </div>
            <button
              className="primary"
              onClick={handleRunLayer2}
              disabled={!layer1Done || layer2Running || running}
              title={!layer1Done ? "Run Layer 1 first" : ""}
            >
              {layer2Running ? "Writing graph + computing weights…" : "Run Layer 2"}
            </button>
          </div>

          {!layer1Done && (
            <div className="empty-state" style={{ padding: "30px 20px" }}>
              Run Layer 1 first — Layer 2 projects its extracted entities into Neo4j.
            </div>
          )}

          {layer2Error && (
            <div className="card" style={{ borderColor: "var(--accent-error)", marginBottom: 16 }}>
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{layer2Error}</span>
            </div>
          )}

          {layer1Done && layer2Done && (
            <>
              <div className="two-col">
                <div>
                  <div className="case-pill" style={{ marginBottom: 10, display: "inline-block" }}>
                    {caseData.evidence_map.graph_write.nodes_written.join(" · ") || "no nodes written"}
                  </div>
                  <TrustWeightsTable trustWeights={caseData.trust_weights} />
                </div>
                <div>
                  <div className="card-title" style={{ marginBottom: 10, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-faint)", textTransform: "uppercase" }}>
                    Company graph neighbourhood
                  </div>
                  <ContextGraphView data={graphData} />
                  <GraphDataCoveragePanel graphWrite={caseData?.evidence_map?.graph_write} />
                </div>
              </div>

              <CollapsibleSection title="Related parties (shared-director detection)" defaultOpen>
                <div style={{ marginBottom: 10 }}>
                  <button onClick={handleCheckRelatedParties} disabled={relatedPartiesLoading}>
                    {relatedPartiesLoading ? "Checking…" : "Re-check related parties"}
                  </button>
                </div>
                <RelatedPartiesList relatedParties={relatedParties} />
              </CollapsibleSection>
            </>
          )}

          {/* LAYER 3 */}
          <div className="layer-heading-row">
            <div className="layer-heading" style={{ margin: 0 }}>
              <span className="layer-tag">LAYER 3</span> Triangulation Engine
            </div>
            <button
              className="primary"
              onClick={handleRunLayer3}
              disabled={!layer2HasPairwise || layer3Running}
              title={!layer2HasPairwise ? "Run Layer 2 first" : ""}
            >
              {layer3Running ? "Reconciling…" : "Run Layer 3"}
            </button>
          </div>

          {!layer2HasPairwise && (
            <div className="empty-state" style={{ padding: "30px 20px" }}>
              Run Layer 2 first — Layer 3 reconciles its pairwise trust weights into an effective turnover figure.
            </div>
          )}

          {layer3Error && (
            <div className="card" style={{ borderColor: "var(--accent-error)", marginBottom: 16 }}>
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{layer3Error}</span>
            </div>
          )}

          {layer2HasPairwise && layer3Done && (
            <>
              <EffectiveMetricsPanel metrics={caseData.effective_metrics} />
              <CollapsibleSection title="Fraud signals & contradictions" defaultOpen>
                <FraudSignalsPanel fraudSignals={caseData.fraud_signals} contradictions={caseData.contradictions} />
              </CollapsibleSection>
            </>
          )}

          {/* LAYER 4 */}
          <div className="layer-heading-row">
            <div className="layer-heading" style={{ margin: 0 }}>
              <span className="layer-tag">LAYER 4</span> Policy Engine / BRE
            </div>
            <button
              className="primary"
              onClick={handleRunLayer4}
              disabled={!layer3Done || layer4Running}
              title={!layer3Done ? "Run Layer 3 first" : ""}
            >
              {layer4Running ? "Evaluating rules…" : "Run Layer 4"}
            </button>
          </div>

          {!layer3Done && (
            <div className="empty-state" style={{ padding: "30px 20px" }}>
              Run Layer 3 first — the policy engine needs effective_metrics (DSCR, turnover, etc.).
            </div>
          )}

          {layer4Error && (
            <div className="card" style={{ borderColor: "var(--accent-error)", marginBottom: 16 }}>
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{layer4Error}</span>
            </div>
          )}

          {layer3Done && layer4Done && (
            <PolicyDecisionPanel policySummary={caseData.policy_summary} />
          )}

          {/* LAYER 5 */}
          <div className="layer-heading-row">
            <div className="layer-heading" style={{ margin: 0 }}>
              <span className="layer-tag">LAYER 5</span> ML Risk Scoring
            </div>
            <button
              className="primary"
              onClick={handleRunLayer5}
              disabled={!layer3Done || layer5Running}
              title={!layer3Done ? "Run Layer 3 first" : ""}
            >
              {layer5Running ? "Scoring…" : "Run Layer 5"}
            </button>
          </div>

          {!layer3Done && (
            <div className="empty-state" style={{ padding: "30px 20px" }}>
              Run Layer 3 first — the ML model uses effective_metrics as input features.
            </div>
          )}

          {layer5Error && (
            <div className="card" style={{ borderColor: "var(--accent-error)", marginBottom: 16 }}>
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{layer5Error}</span>
            </div>
          )}

          {layer3Done && layer5Done && (
            <div className="card">
              <RiskScoreGauge
                riskScore={caseData.risk_score}
                pd={caseData.pd}
                lgd={caseData.lgd}
                riskBand={caseData.effective_metrics?.risk_band}
                expectedLossRate={caseData.effective_metrics?.expected_loss_rate}
                modelName={caseData.effective_metrics?.ml_model_name}
                trainedOn={caseData.effective_metrics?.ml_trained_on}
              />
            </div>
          )}

          {/* LAYER 6 */}
          <div className="layer-heading-row">
            <div className="layer-heading" style={{ margin: 0 }}>
              <span className="layer-tag">LAYER 6</span> Sanction / Limit + Credit Memo
            </div>
            <button
              className="primary"
              onClick={handleRunLayer6}
              disabled={!layer4Done || layer6Running}
              title={!layer4Done ? "Run Layer 4 first" : ""}
            >
              {layer6Running ? "Computing limit + writing memo…" : "Run Layer 6"}
            </button>
          </div>

          {!layer4Done && (
            <div className="empty-state" style={{ padding: "30px 20px" }}>
              Run Layers 3 and 4 first — the limit optimiser needs effective_metrics and the policy decision.
            </div>
          )}

          {layer6Error && (
            <div className="card" style={{ borderColor: "var(--accent-error)", marginBottom: 16 }}>
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{layer6Error}</span>
            </div>
          )}

          {layer4Done && layer6Done && (
            <>
              <div className="two-col">
                <SanctionPanel
                  recommendedLimit={caseData.recommended_limit}
                  limitOptimizerResult={caseData.evidence_map?.limit_optimiser}
                  policyDecision={caseData.policy_summary?.policy_decision}
                />
                <CollapsibleSection title="Credit Memo" defaultOpen>
                  <CreditMemoViewer memo={caseData.credit_memo} caseId={caseData.case_id} />
                </CollapsibleSection>
              </div>
            </>
          )}

          {/* AUDIT TRAIL */}
          <CollapsibleSection title={`Audit trail (${caseData.audit_trail?.length || 0} entries)`}>
            {(caseData.audit_trail || []).map((entry, idx) => (
              <div className="audit-row" key={idx}>
                <span>{entry.timestamp}</span>
                <span>layer={entry.layer}</span>
                <span>agent={entry.agent}</span>
                {entry.validation_status && <span>status={entry.validation_status}</span>}
                {entry.confidence !== undefined && <span>confidence={entry.confidence}</span>}
              </div>
            ))}
            {(!caseData.audit_trail || caseData.audit_trail.length === 0) && (
              <span style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                Run the pipeline to populate the audit trail.
              </span>
            )}
          </CollapsibleSection>
        </>
      )}

      <div className="footer-note">credit decisioning os · 6-layer agentic pipeline · AppState · LangGraph</div>
    </div>
  );
}

// ── File Slot Sub-component ───────────────────────────────────────────────────
function FileSlot({ slot, file, onSelect }) {
  const inputRef = useRef(null);

  return (
    <div
      onClick={() => inputRef.current?.click()}
      style={{
        border: `1.5px dashed ${file ? "var(--accent-valid)" : "var(--border)"}`,
        borderRadius: 8,
        padding: "14px 16px",
        cursor: "pointer",
        background: file ? "rgba(79,209,197,0.05)" : "var(--panel)",
        transition: "border-color 0.2s, background 0.2s",
        display: "flex",
        flexDirection: "column",
        gap: 4,
        minHeight: 72,
        justifyContent: "center",
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={slot.accept}
        style={{ display: "none" }}
        onChange={(e) => onSelect(e.target.files?.[0] || null)}
      />
      <div style={{
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        color: "var(--text-faint)",
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        marginBottom: 2,
      }}>
        {slot.hint}
      </div>
      <div style={{ fontWeight: 600, fontSize: 13, color: file ? "var(--accent-valid)" : "var(--text)" }}>
        {file ? `✓ ${file.name}` : slot.label}
      </div>
      {!file && (
        <div style={{ fontSize: 11, color: "var(--text-faint)" }}>
          Click to select file
        </div>
      )}
    </div>
  );
}
