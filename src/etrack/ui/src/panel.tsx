import type { Topology } from "./contract";
import { family, STATUS_GLYPH } from "./kinds";
import { titleOf } from "./layout";
import { hostNode, outer, type Span } from "./spans";

export type Pick = { type: "span"; id: string } | { type: "node"; id: string } | null;

interface Shared {
  topology: Topology;
  spans: Map<string, Span>;
  pick: (next: Pick) => void;
}

function SpanRow({ span, depth, picked, topology, pick }: { span: Span; depth: number; picked: Pick } & Shared) {
  const name = span.kind === "node" ? titleOf(topology, span.name) : span.name;
  const active = picked?.type === "span" && picked.id === span.id;
  return (
    <button
      type="button"
      className={`row ${span.status} ${active ? "picked" : ""}`}
      style={{ paddingLeft: 8 + depth * 14 }}
      onClick={() => pick({ type: "span", id: span.id })}
    >
      <span className={`glyph ${span.status}`}>{STATUS_GLYPH[span.status]}</span>
      <span className={`kind fam-${family(span.kind)}`}>{span.kind}</span>
      <span className="label">{name}</span>
      {span.latency !== null && <span className="latency">{Math.round(span.latency)} ms</span>}
    </button>
  );
}

function Tree({ parent, depth, picked, ...shared }: { parent: string; depth: number; picked: Pick } & Shared) {
  const children = [...shared.spans.values()].filter((span) => span.parent === parent).sort((a, b) => a.seq - b.seq);
  return (
    <>
      {children.map((span) => (
        <div key={span.id}>
          <SpanRow span={span} depth={depth} picked={picked} {...shared} />
          <Tree parent={span.id} depth={depth + 1} picked={picked} {...shared} />
        </div>
      ))}
    </>
  );
}

function SpanDetail({ span }: { span: Span }) {
  const tokens = span.usage ? `${span.usage.input_tokens ?? 0} in · ${span.usage.output_tokens ?? 0} out` : "";
  return (
    <div className="detail">
      <h3>
        <span className={`kind fam-${family(span.kind)}`}>{span.kind}</span> {span.name}
      </h3>
      <p className={`status ${span.status}`}>
        {STATUS_GLYPH[span.status]} {span.status}
        {span.latency !== null && ` · ${Math.round(span.latency)} ms`}
        {tokens && ` · ${tokens}`}
      </p>
      {span.error && <pre className="error">{span.error}</pre>}
      {span.reasoning && (
        <>
          <h4>reasoning</h4>
          <pre>{span.reasoning}</pre>
        </>
      )}
      {span.text && (
        <>
          <h4>text</h4>
          <pre>{span.text}</pre>
        </>
      )}
      <h4>input</h4>
      <pre>{JSON.stringify(span.input, null, 2)}</pre>
      {span.output !== null && (
        <>
          <h4>output</h4>
          <pre>{JSON.stringify(span.output, null, 2)}</pre>
        </>
      )}
    </div>
  );
}

// A declared node: what it is in the graph, how it is wired, and what it did in this run.
function NodeDetail({ id, topology, spans, pick }: { id: string } & Shared) {
  const node = topology.nodes.find((found) => found.id === id);
  if (!node) return null;
  const role = node.entry ? "entry — where a run enters the graph" : node.exit ? "exit — where a run leaves" : "node";
  const into = topology.edges.filter((edge) => edge.target === id);
  const out = topology.edges.filter((edge) => edge.source === id);
  const visits = [...spans.values()]
    .filter((span) => span.kind === "node" && span.name === node.name && outer(spans, span))
    .sort((a, b) => a.seq - b.seq);
  const calls = [...spans.values()]
    .filter((span) => span.kind !== "node" && hostNode(spans, span)?.name === node.name)
    .sort((a, b) => a.seq - b.seq);
  const arc = (other: string, label: string, conditional: boolean, loop: boolean) =>
    `${titleOf(topology, other)}${label ? ` · "${label}"` : ""}${conditional ? " · router" : ""}${loop ? " · loop" : ""}`;
  return (
    <div className="detail">
      <h3>{node.label || node.name}</h3>
      <dl>
        <dt>role</dt>
        <dd>{role}</dd>
        <dt>name</dt>
        <dd>
          <code>{node.name}</code> — what its spans carry
        </dd>
        {node.id !== node.name && (
          <>
            <dt>id</dt>
            <dd>
              <code>{node.id}</code>
            </dd>
          </>
        )}
        <dt>from</dt>
        <dd>
          {into.map((edge) => arc(edge.source, edge.label ?? "", !!edge.conditional, !!edge.loop)).join(", ") || "—"}
        </dd>
        <dt>to</dt>
        <dd>
          {out.map((edge) => arc(edge.target, edge.label ?? "", !!edge.conditional, !!edge.loop)).join(", ") || "—"}
        </dd>
      </dl>
      <h4>visits in this run · {visits.length}</h4>
      {visits.length === 0 && <p className="muted">not reached in this run</p>}
      {visits.map((span, index) => (
        <button
          type="button"
          key={span.id}
          className={`row ${span.status}`}
          onClick={() => pick({ type: "span", id: span.id })}
        >
          <span className={`glyph ${span.status}`}>{STATUS_GLYPH[span.status]}</span>
          <span className="label">visit {index + 1}</span>
          {span.latency !== null && <span className="latency">{Math.round(span.latency)} ms</span>}
        </button>
      ))}
      {calls.length > 0 && <h4>calls · {calls.length}</h4>}
      {calls.map((span) => (
        <button
          type="button"
          key={span.id}
          className={`row ${span.status}`}
          onClick={() => pick({ type: "span", id: span.id })}
        >
          <span className={`glyph ${span.status}`}>{STATUS_GLYPH[span.status]}</span>
          <span className={`kind fam-${family(span.kind)}`}>{span.kind}</span>
          <span className="label">{span.name}</span>
          {span.latency !== null && <span className="latency">{Math.round(span.latency)} ms</span>}
        </button>
      ))}
    </div>
  );
}

export function Panel({ picked, ...shared }: { picked: Pick } & Shared) {
  const span = picked?.type === "span" ? shared.spans.get(picked.id) : undefined;
  return (
    <aside className="panel">
      <div className="tree">
        <Tree parent="" depth={0} picked={picked} {...shared} />
      </div>
      {picked?.type === "node" && <NodeDetail id={picked.id} {...shared} />}
      {span && <SpanDetail span={span} />}
      {!picked && (
        <p className="hint">Click a node or a call on the canvas, or a span in the tree, to see what it is.</p>
      )}
    </aside>
  );
}
