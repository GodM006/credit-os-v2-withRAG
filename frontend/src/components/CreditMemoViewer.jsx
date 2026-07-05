import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function triggerDownload(url, filename) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}

export default function CreditMemoViewer({ memo, caseId }) {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(null); // "docx" | "pdf" | null
  const [dlError, setDlError] = useState(null);

  async function handleDownload(fmt) {
    setDlError(null);
    setDownloading(fmt);
    try {
      await triggerDownload(
        `${API_BASE}/api/layer6/cases/${caseId}/download/cam.${fmt}`,
        `CAM_${caseId}.${fmt}`
      );
    } catch (e) {
      setDlError(e.message);
    } finally {
      setDownloading(null);
    }
  }

  function handleCopy() {
    if (!memo) return;
    navigator.clipboard.writeText(memo).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  if (!memo) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No credit memo yet — run Layer 6.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {/* Action buttons */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button
          onClick={() => handleDownload("docx")}
          disabled={downloading !== null}
          className="primary"
          style={{ fontSize: 12, padding: "8px 14px" }}
        >
          {downloading === "docx" ? "Generating…" : "⬇ Download CAM (.docx)"}
        </button>
        <button
          onClick={() => handleDownload("pdf")}
          disabled={downloading !== null}
          className="primary"
          style={{ fontSize: 12, padding: "8px 14px", background: "var(--accent-valid)", borderColor: "var(--accent-valid)", color: "#0a0d13" }}
        >
          {downloading === "pdf" ? "Generating…" : "⬇ Download CAM (.pdf)"}
        </button>
        <button
          onClick={handleCopy}
          style={{ fontSize: 12, padding: "8px 14px", marginLeft: "auto" }}
        >
          {copied ? "Copied!" : "Copy text"}
        </button>
      </div>

      {dlError && (
        <div style={{ color: "var(--accent-error)", fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
          {dlError}
        </div>
      )}

      <div style={{
        background: "var(--bg)",
        border: "1px solid var(--border-soft)",
        borderRadius: 8,
        padding: "16px 20px",
        fontFamily: "var(--font-body)",
        fontSize: 13.5,
        lineHeight: 1.75,
        color: "var(--text-muted)",
        whiteSpace: "pre-wrap",
        maxHeight: 520,
        overflowY: "auto",
      }}>
        {memo}
      </div>

      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--text-faint)" }}>
        The downloaded CAM includes all 12 sections: applicant profile, financials,
        banking, bureau, GST, triangulation analysis, fraud signals, policy BRE
        results, ML scoring, constraint waterfall, and this narrative — formatted
        for credit committee review.
      </div>
    </div>
  );
}
