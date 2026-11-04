import { Background, Controls, ReactFlow } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { fetchThreads, fetchTopology, followThread } from "./api";
import type { LiveSummary, RunEvent, Topology } from "./contract";
import { LEGEND } from "./kinds";
import { activity, layout, trail } from "./layout";
import { LiveContext } from "./live";
import { NODE_TYPES } from "./nodes";
import { Panel, type Pick } from "./panel";
import { fold, hostNode, type Span } from "./spans";

const POLL_MS = 2000;
const EMPTY = { nodes: [], edges: [] };

function initialThread(): string {
  return new URLSearchParams(window.location.search).get("thread") ?? "";
}

export function App() {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [threads, setThreads] = useState<LiveSummary[]>([]);
  const [thread, setThread] = useState(initialThread);
  const [frames, setFrames] = useState<RunEvent[]>([]);
  const [run, setRun] = useState("");
  const [online, setOnline] = useState(false);
  const [picked, setPicked] = useState<Pick>(null);

  useEffect(() => {
    fetchTopology().then(setTopology);
  }, []);

  useEffect(() => {
    const poll = () => fetchThreads().then(setThreads);
    poll();
    const timer = window.setInterval(poll, POLL_MS);
    return () => window.clearInterval(timer);
  }, []);

  // No thread chosen yet: follow the most recently written one.
  useEffect(() => {
    if (!thread && threads[0]) setThread(threads[0].thread);
  }, [thread, threads]);

  useEffect(() => {
    if (!thread) return;
    const url = new URL(window.location.href);
    url.searchParams.set("thread", thread);
    window.history.replaceState(null, "", url);
    setFrames([]);
    setRun("");
    setPicked(null);
    // frames arrive in bursts: they are kept and handed to React once per animation frame, never one render each.
    let pending: RunEvent[] = [];
    let scheduled = 0;
    const flush = () => {
      const batch = pending;
      pending = [];
      scheduled = 0;
      setFrames((seen) => seen.concat(batch));
    };
    const stop = followThread(
      thread,
      (event) => {
        pending.push(event);
        scheduled ||= window.requestAnimationFrame(flush);
      },
      setOnline,
    );
    return () => {
      stop();
      window.cancelAnimationFrame(scheduled);
    };
  }, [thread]);

  const runs = useMemo(() => [...new Set(frames.map((event) => event.run_id))], [frames]);
  const current = run || runs[runs.length - 1] || "";

  const spans = useMemo(
    () => frames.filter((event) => event.run_id === current).reduce(fold, new Map<string, Span>()),
    [frames, current],
  );

  // Built once per topology: the same node objects for the whole session, so nothing is ever re-measured or hidden.
  const graph = useMemo(() => (topology ? layout(topology) : EMPTY), [topology]);
  const lit = useMemo(() => (topology ? activity(topology, spans) : new Map()), [topology, spans]);
  const walked = useMemo(() => (topology ? trail(topology, spans) : null), [topology, spans]);
  const edges = useMemo(
    () =>
      graph.edges.map((edge) => {
        const state = edge.id === walked?.last ? "hot" : walked?.walked.has(edge.id) ? "walked" : "";
        return state ? { ...edge, className: `${edge.className ?? ""} ${state}`, animated: state === "hot" } : edge;
      }),
    [graph.edges, walked],
  );

  // The pick lights its declared node: a node itself, or the node a picked span ran under.
  const pickedNode = useMemo(() => {
    if (picked?.type === "node") return picked.id;
    const span = picked?.type === "span" ? spans.get(picked.id) : undefined;
    const host = span && (span.kind === "node" ? span : hostNode(spans, span));
    return topology?.nodes.find((node) => node.name === host?.name)?.id ?? "";
  }, [picked, spans, topology]);
  const live = useMemo(() => ({ activity: lit, picked: pickedNode }), [lit, pickedNode]);

  return (
    <div className="shell">
      <header>
        <strong>e-track</strong>
        <label>
          thread
          <select value={thread} onChange={(change) => setThread(change.target.value)}>
            {thread && !threads.some((known) => known.thread === thread) && <option value={thread}>{thread}</option>}
            {threads.map((known) => (
              <option key={known.thread} value={known.thread}>
                {known.thread} · {known.offset} frames
              </option>
            ))}
          </select>
        </label>
        <label>
          run
          <select value={current} onChange={(change) => setRun(change.target.value)}>
            {runs.map((id, index) => (
              <option key={id} value={id}>
                #{index + 1} · {id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        <span className="legend">
          {LEGEND.map((entry) => (
            <span key={entry.family} className={`swatch fam-${entry.family}`}>
              {entry.label}
            </span>
          ))}
          <span className="states">◌ running · ✓ done · ✕ error</span>
        </span>
        <span className={`online ${online ? "on" : "off"}`}>{online ? "live" : "reconnecting"}</span>
      </header>
      <main>
        <div className="canvas">
          <LiveContext.Provider value={live}>
            <ReactFlow
              nodes={graph.nodes}
              edges={edges}
              nodeTypes={NODE_TYPES}
              onNodeClick={(_, node) => setPicked({ type: "node", id: node.id })}
              onPaneClick={() => setPicked(null)}
              nodeOrigin={[0.5, 0]}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={false}
              fitView
              fitViewOptions={{ padding: 0.1 }}
              proOptions={{ hideAttribution: true }}
              colorMode="dark"
            >
              <Background gap={24} />
              <Controls showInteractive={false} />
            </ReactFlow>
          </LiveContext.Provider>
        </div>
        {topology && <Panel topology={topology} spans={spans} picked={picked} pick={setPicked} />}
      </main>
    </div>
  );
}
