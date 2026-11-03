import type { Span } from "./spans";

function Tree({ spans, parent, depth, pick, picked }: TreeProps) {
  const children = [...spans.values()].filter((span) => span.parent === parent).sort((a, b) => a.seq - b.seq);
  return (
    <>
      {children.map((span) => (
        <div key={span.id}>
          <button
            type="button"
            className={`row ${span.status} ${picked === span.id ? "picked" : ""}`}
            style={{ paddingLeft: 8 + depth * 14 }}
            onClick={() => pick(span.id)}
          >
            <span className={`dot ${span.status}`} />
            <span className="kind">{span.kind}</span>
            <span className="label">{span.name}</span>
            {span.latency !== null && <span className="latency">{Math.round(span.latency)} ms</span>}
          </button>
          <Tree spans={spans} parent={span.id} depth={depth + 1} pick={pick} picked={picked} />
        </div>
      ))}
    </>
  );
}

interface TreeProps {
  spans: Map<string, Span>;
  parent: string;
  depth: number;
  pick: (id: string) => void;
  picked: string;
}

function Detail({ span }: { span: Span }) {
  const tokens = span.usage ? `${span.usage.input_tokens ?? 0} in · ${span.usage.output_tokens ?? 0} out` : "";
  return (
    <div className="detail">
      <h3>
        {span.kind} · {span.name}
      </h3>
      <p className={`status ${span.status}`}>
        {span.status}
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

export function Panel({
  spans,
  picked,
  pick,
}: {
  spans: Map<string, Span>;
  picked: string;
  pick: (id: string) => void;
}) {
  const span = spans.get(picked);
  return (
    <aside className="panel">
      <div className="tree">
        <Tree spans={spans} parent="" depth={0} pick={pick} picked={picked} />
      </div>
      {span && <Detail span={span} />}
    </aside>
  );
}
