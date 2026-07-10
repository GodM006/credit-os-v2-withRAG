import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";

// Node-type → color. Values may be CSS custom properties (resolved to hex at
// runtime for gradient math) or plain hex.
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

const FALLBACK_COLOR = "#3a4254"; // --accent-idle

// Resolve "var(--x)" (or a plain color) into a concrete color string so
// d3.color(...).brighter()/darker() can build gradient stops.
function resolveColor(value) {
  if (typeof value !== "string") return FALLBACK_COLOR;
  const m = value.match(/^var\((--[^)]+)\)$/);
  if (!m) return value;
  if (typeof window === "undefined") return FALLBACK_COLOR;
  const resolved = getComputedStyle(document.documentElement)
    .getPropertyValue(m[1])
    .trim();
  return resolved || FALLBACK_COLOR;
}

const colorForType = (type) => resolveColor(TYPE_COLORS[type] || FALLBACK_COLOR);

// Keeps only the top-k edges per node (by weight desc) to prevent hairball
// graphs on very dense cases. Ported from the neopatterns PatternGraph.
function capNeighbors(raw, k) {
  const count = new Map();
  const kept = [];
  const sorted = [...raw].sort((a, b) => (b.weight ?? 1) - (a.weight ?? 1));
  for (const e of sorted) {
    const s = typeof e.source === "string" ? e.source : e.source.id;
    const t = typeof e.target === "string" ? e.target : e.target.id;
    if ((count.get(s) ?? 0) < k && (count.get(t) ?? 0) < k) {
      kept.push(e);
      count.set(s, (count.get(s) ?? 0) + 1);
      count.set(t, (count.get(t) ?? 0) + 1);
    }
  }
  return kept;
}

// Merge counterparty nodes that differ only by transaction direction. Neo4j
// stores each direction as its own node (…:inflow / …:outflow) with the same
// display name and parent, which renders as duplicate labels in the graph
// (e.g. "muham med" twice). Collapse them into one node per (parent, name) and
// rewire the edges. Purely visual — the coverage panel keeps the true counts.
function mergeDirectionalDuplicates(rawNodes, rawEdges) {
  const nodes = rawNodes || [];
  const edges = rawEdges || [];
  const canonicalByKey = new Map(); // `${parent}::${name}` -> canonical id
  const idRemap = new Map();        // original id -> canonical id
  const mergedNodes = [];
  for (const n of nodes) {
    if (n.type === "Counterparty") {
      const key = `${n.parent_id ?? ""}::${n.label ?? n.id}`;
      const existing = canonicalByKey.get(key);
      if (existing) { idRemap.set(n.id, existing); continue; }
      canonicalByKey.set(key, n.id);
    }
    idRemap.set(n.id, n.id);
    mergedNodes.push(n);
  }
  const resolve = (id) => idRemap.get(id) ?? id;
  const seen = new Set();
  const mergedEdges = [];
  for (const e of edges) {
    const s = resolve(e.source), t = resolve(e.target);
    if (s === t) continue; // drop self-loops created by the merge
    const key = s < t ? `${s}|${t}|${e.type}` : `${t}|${s}|${e.type}`;
    if (seen.has(key)) continue;
    seen.add(key);
    mergedEdges.push({ ...e, source: s, target: t });
  }
  return { nodes: mergedNodes, edges: mergedEdges };
}

export default function ContextGraphView({ data }) {
  const svgRef = useRef(null);
  const zoomRef = useRef(null);
  const [tooltip, setTooltip] = useState(null); // { node, x, y }
  const [focusId, setFocusId] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const focusRef = useRef(null);

  const { nodes, edges } = mergeDirectionalDuplicates(data?.nodes, data?.edges);
  const presentTypes = [...new Set(nodes.map((n) => n.type))];

  const resetZoom = useCallback(() => {
    if (!svgRef.current || !zoomRef.current) return;
    d3.select(svgRef.current).transition().duration(500)
      .call(zoomRef.current.transform, d3.zoomIdentity);
  }, []);

  const zoomBy = useCallback((factor) => {
    if (!svgRef.current || !zoomRef.current) return;
    d3.select(svgRef.current).transition().duration(220)
      .call(zoomRef.current.scaleBy, factor);
  }, []);

  const toggleFullscreen = useCallback(() => {
    const el = svgRef.current?.closest("[data-graph-container]");
    if (!el) return;
    if (!document.fullscreenElement) el.requestFullscreen?.();
    else document.exitFullscreen?.();
  }, []);

  // Keep isFullscreen in sync (covers ESC / browser-driven exit) and size the
  // canvas to fill the screen while fullscreen.
  useEffect(() => {
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  useEffect(() => {
    if (!nodes.length || !svgRef.current) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const { width, height } = svgRef.current.getBoundingClientRect();
    const W = width || 640;
    const H = height || 520;

    // ── Identify company / hop-0 node ────────────────────────────────────────
    const company =
      nodes.find((n) => n.hop === 0) ||
      nodes.find((n) => n.type === "Company") ||
      nodes[0];

    const simNodes = nodes.map((n) => ({ ...n }));
    const idToNode = new Map(simNodes.map((n) => [n.id, n]));

    // ── Build edges from the real Neo4j relationships (deduped) ──────────────
    const nodeIds = new Set(simNodes.map((n) => n.id));
    const seen = new Set();
    let rawEdges = [];
    for (const e of edges) {
      if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
      const key = e.source < e.target ? `${e.source}|${e.target}` : `${e.target}|${e.source}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rawEdges.push({
        source: idToNode.get(e.source),
        target: idToNode.get(e.target),
        relationship: e.type,
        weight: 1,
      });
    }
    // Safety net for pathologically dense graphs.
    const simEdges = rawEdges.length > 400 ? capNeighbors(rawEdges, 6) : rawEdges;

    // ── Degree for sizing ────────────────────────────────────────────────────
    const degreeMap = new Map();
    simEdges.forEach((e) => {
      const s = e.source.id, t = e.target.id;
      degreeMap.set(s, (degreeMap.get(s) ?? 0) + 1);
      degreeMap.set(t, (degreeMap.get(t) ?? 0) + 1);
    });
    const nodeR = (n) =>
      n.id === company.id
        ? 18
        : Math.max(6, Math.min(13, 6 + (degreeMap.get(n.id) ?? 0) * 0.7));

    // ── Adjacency for ego-focus ──────────────────────────────────────────────
    const neighbors = new Map(simNodes.map((n) => [n.id, new Set([n.id])]));
    simEdges.forEach((e) => {
      neighbors.get(e.source.id)?.add(e.target.id);
      neighbors.get(e.target.id)?.add(e.source.id);
    });

    // ── Zoom / pan ───────────────────────────────────────────────────────────
    const zoom = d3.zoom()
      .scaleExtent([0.08, 8])
      .on("zoom", (e) => g.attr("transform", e.transform));
    zoomRef.current = zoom;
    svg.call(zoom);

    // Click on empty canvas clears the ego-focus.
    svg.on("click", () => { focusRef.current = null; setFocusId(null); applyFocus(); });

    const g = svg.append("g");
    const defs = svg.append("defs");

    // Subtle drop shadow.
    const filt = defs.append("filter").attr("id", "cg-shadow")
      .attr("x", "-30%").attr("y", "-30%").attr("width", "160%").attr("height", "160%");
    filt.append("feDropShadow")
      .attr("dx", 0).attr("dy", 1).attr("stdDeviation", "1.2")
      .attr("flood-color", "rgba(0,0,0,0.45)");

    // Radial gradient per present node type.
    presentTypes.forEach((type) => {
      const base = colorForType(type);
      const c = d3.color(base) || d3.color(FALLBACK_COLOR);
      const rg = defs.append("radialGradient")
        .attr("id", `cg-${cssId(type)}`).attr("cx", "38%").attr("cy", "32%").attr("r", "68%");
      rg.append("stop").attr("offset", "0%").attr("stop-color", c.brighter(0.4).toString());
      rg.append("stop").attr("offset", "100%").attr("stop-color", c.darker(0.3).toString());
    });

    // ── Links ────────────────────────────────────────────────────────────────
    const linkSel = g.append("g").selectAll("line")
      .data(simEdges)
      .join("line")
      .attr("stroke", "#64748b")
      .attr("stroke-width", 0.9)
      .attr("stroke-opacity", 0.4)
      .style("cursor", "pointer")
      .on("mouseover", (event, d) => {
        setTooltip({ edge: d, x: event.clientX, y: event.clientY });
        d3.select(event.currentTarget).attr("stroke", "#fac400").attr("stroke-opacity", 0.9);
      })
      .on("mousemove", (event, d) => setTooltip({ edge: d, x: event.clientX, y: event.clientY }))
      .on("mouseout", (event) => {
        setTooltip(null);
        d3.select(event.currentTarget).attr("stroke", "#64748b").attr("stroke-opacity", 0.4);
      });

    // ── Nodes ────────────────────────────────────────────────────────────────
    const nodeSel = g.append("g").selectAll("circle")
      .data(simNodes)
      .join("circle")
      .attr("r", nodeR)
      .attr("fill", (d) => `url(#cg-${cssId(d.type)})`)
      .attr("stroke", "rgba(0,0,0,0.25)")
      .attr("stroke-width", 1)
      .attr("filter", "url(#cg-shadow)")
      .style("cursor", "pointer")
      .on("mouseover", (event, d) => {
        setTooltip({ node: d, x: event.clientX, y: event.clientY });
        d3.select(event.currentTarget).raise()
          .transition().duration(100)
          .attr("r", nodeR(d) * 1.5)
          .attr("stroke", "#fac400").attr("stroke-width", 2);
      })
      .on("mousemove", (event, d) => setTooltip({ node: d, x: event.clientX, y: event.clientY }))
      .on("mouseout", (event, d) => {
        setTooltip(null);
        d3.select(event.currentTarget).transition().duration(100)
          .attr("r", nodeR(d))
          .attr("stroke", "rgba(0,0,0,0.25)").attr("stroke-width", 1);
      })
      .on("click", (event, d) => {
        event.stopPropagation();
        focusRef.current = focusRef.current === d.id ? null : d.id;
        setFocusId(focusRef.current);
        applyFocus();
      });

    nodeSel.call(
      d3.drag()
        .on("start", (ev, d) => { if (!ev.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
        .on("end", (ev, d) => {
          if (!ev.active) sim.alphaTarget(0);
          // Keep the company pinned at center; release everything else.
          if (d.id !== company.id) { d.fx = null; d.fy = null; }
        })
    );

    // ── Labels ───────────────────────────────────────────────────────────────
    const labelSel = g.append("g").selectAll("text")
      .data(simNodes)
      .join("text")
      .attr("font-size", (d) => (d.id === company.id ? 11 : 9))
      .attr("font-family", "var(--font-mono)")
      .attr("fill", "#9ca3af")
      .attr("pointer-events", "none")
      .attr("text-anchor", "middle")
      .attr("dy", (d) => nodeR(d) + 11)
      .text((d) => {
        const label = String(d.label ?? "");
        return label.length > 22 ? label.slice(0, 20) + "…" : label;
      });

    // Re-applies ego-focus dimming based on focusRef.
    function applyFocus() {
      const f = focusRef.current;
      const ego = f ? neighbors.get(f) : null;
      nodeSel
        .attr("fill-opacity", (d) => (!ego || ego.has(d.id) ? 1 : 0.12))
        .attr("stroke", (d) => (f && d.id === f ? "#fac400" : "rgba(0,0,0,0.25)"))
        .attr("stroke-width", (d) => (f && d.id === f ? 2.5 : 1));
      labelSel.attr("fill-opacity", (d) => (!ego || ego.has(d.id) ? 1 : 0.15));
      linkSel.attr("stroke-opacity", (d) =>
        !ego ? 0.4 : (ego.has(d.source.id) && ego.has(d.target.id) ? 0.6 : 0.05)
      );
    }

    // ── Simulation ───────────────────────────────────────────────────────────
    // Pin the company node at the center so the neighbourhood reads as company-centric.
    const centerNode = idToNode.get(company.id);
    if (centerNode) { centerNode.fx = W / 2; centerNode.fy = H / 2; }

    const sim = d3.forceSimulation(simNodes)
      .force("link", d3.forceLink(simEdges)
        .id((d) => d.id)
        .distance((e) => Math.max(45, 90 / (e.weight || 1)))
        .strength(0.4))
      .force("charge", d3.forceManyBody().strength(-120).distanceMax(500))
      .force("center", d3.forceCenter(W / 2, H / 2).strength(0.04))
      .force("collide", d3.forceCollide().radius((d) => nodeR(d) + 14).strength(0.85))
      .force("x", d3.forceX(W / 2).strength(0.025))
      .force("y", d3.forceY(H / 2).strength(0.025))
      .alphaDecay(0.015)
      .on("tick", () => {
        linkSel
          .attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
          .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
        nodeSel.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
        labelSel.attr("x", (d) => d.x).attr("y", (d) => d.y);
      });

    applyFocus();

    return () => { sim.stop(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  if (nodes.length === 0) {
    return (
      <div style={{ color: "var(--text-faint)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
        No graph data yet — run Layer 2 first.
      </div>
    );
  }

  const btnStyle = {
    width: 32, height: 32, borderRadius: 8,
    display: "flex", alignItems: "center", justifyContent: "center",
    background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)",
    color: "#8893a6", cursor: "pointer", padding: 0,
  };

  return (
    <div>
      <div
        data-graph-container
        style={{
          position: "relative", width: "100%", height: isFullscreen ? "100%" : 520,
          background: "var(--bg)", borderRadius: isFullscreen ? 0 : 8,
          border: "1px solid var(--border)", overflow: "hidden",
        }}
      >
        {/* Zoom controls */}
        <div style={{ position: "absolute", top: 10, right: 10, display: "flex", gap: 6, zIndex: 10 }}>
          <button style={btnStyle} title="Zoom in" onClick={() => zoomBy(1.5)}>{ICONS.zoomIn}</button>
          <button style={btnStyle} title="Zoom out" onClick={() => zoomBy(1 / 1.5)}>{ICONS.zoomOut}</button>
          <button style={btnStyle} title="Reset view" onClick={resetZoom}>{ICONS.home}</button>
          <button style={btnStyle} title="Fullscreen" onClick={toggleFullscreen}>{ICONS.expand}</button>
        </div>

        {focusId && (
          <div style={{
            position: "absolute", top: 10, left: 10, zIndex: 10,
            fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-faint)",
            background: "rgba(10,13,19,0.7)", padding: "3px 8px", borderRadius: 6,
            border: "1px solid var(--border)",
          }}>
            focused · click empty space to reset
          </div>
        )}

        <svg ref={svgRef} style={{ width: "100%", height: "100%", display: "block" }} />
      </div>

      {/* Tooltip */}
      {tooltip && <GraphTooltip tooltip={tooltip} />}

      {/* Legend */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 8 }}>
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
            {nodes.some((n) => n.type === t && n.hop === 2) && (
              <span style={{ fontSize: 9, opacity: 0.6 }}>· hop-2</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// Fixed-position hover tooltip (mirrors neopatterns GraphTooltip).
function GraphTooltip({ tooltip }) {
  const { x, y, node, edge } = tooltip;
  const style = {
    position: "fixed", left: x + 14, top: y + 14, zIndex: 50,
    maxWidth: 240, pointerEvents: "none",
    background: "rgba(15,20,30,0.95)", backdropFilter: "blur(8px)",
    border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px",
    fontFamily: "var(--font-mono)", boxShadow: "0 6px 24px rgba(0,0,0,0.5)",
  };

  if (edge) {
    return (
      <div style={style}>
        <div style={{ fontSize: 10, color: "var(--text)", fontWeight: 600 }}>{edge.relationship}</div>
        <div style={{ fontSize: 9, color: "var(--text-faint)", marginTop: 2 }}>
          {String(edge.source.label ?? edge.source.id).slice(0, 20)} → {String(edge.target.label ?? edge.target.id).slice(0, 20)}
        </div>
      </div>
    );
  }

  const props = node.props || {};
  const lines = Object.entries(props)
    .filter(([k, v]) => v !== null && v !== undefined && v !== "" && !["case_id", "ingested_at"].includes(k))
    .slice(0, 6);

  return (
    <div style={style}>
      <div style={{ fontSize: 9, color: "var(--accent-running)", textTransform: "uppercase", letterSpacing: 0.5 }}>
        {node.type}
      </div>
      <div style={{ fontSize: 11, color: "var(--text)", fontWeight: 600, margin: "2px 0 4px" }}>
        {String(node.label ?? node.id)}
      </div>
      {lines.map(([k, v]) => (
        <div key={k} style={{ fontSize: 9, color: "var(--text-faint)" }}>
          {k}: {String(v).slice(0, 28)}
        </div>
      ))}
    </div>
  );
}

// Turns an arbitrary type string into a safe SVG id fragment.
function cssId(type) {
  return String(type).replace(/[^a-zA-Z0-9_-]/g, "_");
}

// Inline SVG icons (replaces lucide-react to avoid an extra dependency).
const ICONS = {
  zoomIn: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /><line x1="11" y1="8" x2="11" y2="14" /><line x1="8" y1="11" x2="14" y2="11" />
    </svg>
  ),
  zoomOut: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /><line x1="8" y1="11" x2="14" y2="11" />
    </svg>
  ),
  home: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  ),
  expand: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
    </svg>
  ),
};
