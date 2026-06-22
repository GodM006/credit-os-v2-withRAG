import { useState } from "react";

export default function CreditMemoViewer({ memo }) {
  const [copied, setCopied] = useState(false);

  if (!memo) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No credit memo yet — run Layer 6.
      </div>
    );
  }

  function handleCopy() {
    navigator.clipboard.writeText(memo).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button onClick={handleCopy} style={{ fontSize: 12 }}>
          {copied ? "Copied!" : "Copy memo"}
        </button>
      </div>
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
    </div>
  );
}
