import { useState, useEffect } from "react";
import { api } from "./api";
import PipelineRail, { AGENTS } from "./components/PipelineRail";
import AgentCard from "./components/AgentCard";
import CollapsibleSection from "./components/CollapsibleSection";
import TrustWeightsTable from "./components/TrustWeightsTable";
import ContextGraphView from "./components/ContextGraphView";
import RelatedPartiesList from "./components/RelatedPartiesList";
import EffectiveMetricsPanel from "./components/EffectiveMetricsPanel";
import FraudSignalsPanel from "./components/FraudSignalsPanel";
import PolicyDecisionPanel from "./components/PolicyDecisionPanel";
import RiskScoreGauge from "./components/RiskScoreGauge";
import SanctionPanel from "./components/SanctionPanel";
import CreditMemoViewer from "./components/CreditMemoViewer";

const SCENARIOS = [
  { value: "clean", label: "Clean applicant" },
  { value: "noisy", label: "Noisy / messy OCR" },
  { value: "fraud_risk", label: "Fraud-risk signals" },
];

export default function App() {
  const [scenario, setScenario] = useState("clean");
  const [caseData, setCaseData] = useState(null);
  const [cases, setCases] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [note, setNote] = useState(null);

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

  useEffect(() => {
    refreshCaseList();
  }, []);

  async function refreshCaseList() {
    try {
      setCases(await api.listCases());
    } catch {
      // non-fatal - case selector just stays empty
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

  function resetLayer2Panels() {
    setGraphData(null);
    setRelatedParties(null);
    setLayer2Error(null);
    setLayer3Error(null);
    setLayer4Error(null);
    setLayer5Error(null);
    setLayer6Error(null);
  }

  async function handleGenerate() {
    setError(null);
    setNote(null);
    setGenerating(true);
    setCaseData(null);
    resetLayer2Panels();
    try {
      const result = await api.generateCase(scenario);
      setCaseData(result);
      refreshCaseList();
    } catch (e) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleGenerateLinkedPair() {
    setError(null);
    setGenerating(true);
    setCaseData(null);
    resetLayer2Panels();
    try {
      const { case_a, case_b } = await api.generateLinkedPair(scenario);
      setCaseData(case_a);
      setNote(
        `Linked twin case generated: ${case_b.case_id} (${case_b.company_name}) shares a director with this one. ` +
          `Run Layer 1 + Layer 2 on both, then check "related parties" on either to see the connection.`
      );
      refreshCaseList();
    } catch (e) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleLoadCase(caseId) {
    if (!caseId) return;
    setError(null);
    setNote(null);
    resetLayer2Panels();
    try {
      const result = await api.getCase(caseId);
      setCaseData(result);
      if (result?.evidence_map?.graph_write) {
        const [graph, related] = await Promise.all([
          api.getCaseGraph(caseId),
          api.getRelatedParties(caseId),
        ]);
        setGraphData(graph);
        setRelatedParties(related);
      }
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleRun() {
    if (!caseData) return;
    setError(null);
    setRunning(true);
    try {
      const result = await api.runCase(caseData.case_id);
      setCaseData(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  async function handleRunLayer2() {
    if (!caseData) return;
    setLayer2Error(null);
    setLayer2Running(true);
    try {
      const result = await api.runLayer2(caseData.case_id);
      setCaseData(result);
      const cin = result?.evidence_map?.graph_write?.company_cin;
      if (cin) {
        const [graph, related] = await Promise.all([
          api.getCaseGraph(caseData.case_id),
          api.getRelatedParties(caseData.case_id),
        ]);
        setGraphData(graph);
        setRelatedParties(related);
      }
    } catch (e) {
      setLayer2Error(e.message);
    } finally {
      setLayer2Running(false);
    }
  }

  async function handleCheckRelatedParties() {
    if (!caseData) return;
    setRelatedPartiesLoading(true);
    try {
      setRelatedParties(await api.getRelatedParties(caseData.case_id));
    } catch (e) {
      setLayer2Error(e.message);
    } finally {
      setRelatedPartiesLoading(false);
    }
  }

  async function handleRunLayer3() {
    if (!caseData) return;
    setLayer3Error(null);
    setLayer3Running(true);
    try {
      const result = await api.runLayer3(caseData.case_id);
      setCaseData(result);
    } catch (e) {
      setLayer3Error(e.message);
    } finally {
      setLayer3Running(false);
    }
  }

  async function handleRunLayer4() {
    if (!caseData) return;
    setLayer4Error(null);
    setLayer4Running(true);
    try {
      const result = await api.runLayer4(caseData.case_id);
      setCaseData(result);
    } catch (e) {
      setLayer4Error(e.message);
    } finally {
      setLayer4Running(false);
    }
  }

  async function handleRunLayer5() {
    if (!caseData) return;
    setLayer5Error(null);
    setLayer5Running(true);
    try {
      const result = await api.runLayer5(caseData.case_id);
      setCaseData(result);
    } catch (e) {
      setLayer5Error(e.message);
    } finally {
      setLayer5Running(false);
    }
  }

  async function handleRunLayer6() {
    if (!caseData) return;
    setLayer6Error(null);
    setLayer6Running(true);
    try {
      const result = await api.runLayer6(caseData.case_id);
      setCaseData(result);
    } catch (e) {
      setLayer6Error(e.message);
    } finally {
      setLayer6Running(false);
    }
  }

  return (
    <div className="app-shell">
      <div className="app-header">
        <div>
          <div className="app-title">
            Credit Decisioning OS
            <span className="layer-tag">LAYERS 1–6</span>
          </div>
          <div className="app-subtitle">
            {caseData ? `case ${caseData.case_id} · ${caseData.company_name}` : "no case loaded"}
          </div>
        </div>
        <div className="controls">
          {cases.length > 0 && (
            <select
              value={caseData?.case_id || ""}
              onChange={(e) => handleLoadCase(e.target.value)}
              disabled={generating || running || layer2Running}
            >
              <option value="" disabled>Load existing case…</option>
              {cases.map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id} · {c.company_name} ({c.scenario})
                </option>
              ))}
            </select>
          )}
          <select value={scenario} onChange={(e) => setScenario(e.target.value)} disabled={generating || running}>
            {SCENARIOS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          <button onClick={handleGenerate} disabled={generating || running}>
            {generating ? "Generating…" : "Generate case"}
          </button>
          <button onClick={handleGenerateLinkedPair} disabled={generating || running} title="Creates two cases sharing one director, for the related-party demo">
            Generate linked pair
          </button>
        </div>
      </div>

      {error && (
        <div className="card" style={{ borderColor: "var(--accent-error)", marginBottom: 20 }}>
          <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{error}</span>
        </div>
      )}

      {note && (
        <div className="card" style={{ borderColor: "var(--accent-running)", marginBottom: 20 }}>
          <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{note}</span>
        </div>
      )}

      {!caseData && !error && (
        <div className="empty-state">
          Generate a synthetic applicant to begin. Six agents will read banking, GST, bureau,
          financials, ledger, and KYC documents and extract structured JSON in parallel.
        </div>
      )}

      {caseData && (
        <>
          <div className="layer-heading-row">
            <div className="layer-heading" style={{ margin: 0 }}>
              <span className="layer-tag">LAYER 1</span> Data Acquisition Agents
            </div>
            <button className="primary" onClick={handleRun} disabled={running || generating}>
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

          <CollapsibleSection title="Raw documents (synthetic input)">
            <div className="doc-grid">
              {AGENTS.map((a) => (
                <div className="doc-box" key={a.key}>
                  <div className="doc-box-title">{a.label}</div>
                  <pre>{caseData.raw_docs?.[a.key]}</pre>
                </div>
              ))}
            </div>
          </CollapsibleSection>

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
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                {layer2Error}
              </span>
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
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                {layer3Error}
              </span>
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

          {/* ── LAYER 4 ────────────────────────────────────────────── */}
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
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                {layer4Error}
              </span>
            </div>
          )}

          {layer3Done && layer4Done && (
            <PolicyDecisionPanel policySummary={caseData.policy_summary} />
          )}

          {/* ── LAYER 5 ────────────────────────────────────────────── */}
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
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                {layer5Error}
              </span>
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

          {/* ── LAYER 6 ────────────────────────────────────────────── */}
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
              <span style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                {layer6Error}
              </span>
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
                  <CreditMemoViewer memo={caseData.credit_memo} />
                </CollapsibleSection>
              </div>
            </>
          )}

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
