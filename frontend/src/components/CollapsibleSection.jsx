import { useState } from "react";

export default function CollapsibleSection({ title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="section">
      <div className="section-head" onClick={() => setOpen(!open)}>
        <span>{title}</span>
        <span className="section-chevron">{open ? "[ – ]" : "[ + ]"}</span>
      </div>
      {open && <div className="section-body">{children}</div>}
    </div>
  );
}
