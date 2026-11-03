import { Background, Controls, ReactFlow, useNodesInitialized, useReactFlow } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { fetchThreads, fetchTopology, followThread } from "./api";
import type { LiveSummary, RunEvent, Topology } from "./contract";
import { LEGEND } from "./kinds";
import { arcs, calls, stages } from "./layout";
import { NODE_TYPES } from "./nodes";
import { Panel, type Pick } from "./panel";
import { fold, type Span } from "./spans";

const POLL_MS = 2000;

// The view refits whenever the canvas grows: calls appear while the run goes on, after the first fit.
// Only once the nodes are measured: a fit before that frames boxes of unknown size and lands off-centre.
function FitOnGrow({ count }: { count: number }) {
  const { fitView } = useReactFlow();
  const measured = useNodesInitialized();
  useEffect(() => {
    if (measured && count > 0) fitView({ duration: 200, padding: 0.12 });
  }, [measured, count, fitView]);
  return null;
}

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
    return followThread(thread, (event) => setFrames((seen) => [...seen, event]), setOnline);
  }, [thread]);

  const runs = useMemo(() => [...new Set(frames.map((event) => event.run_id))], [frames]);
  const current = run || runs[runs.length - 1] || "";

  const spans = useMemo(
    () => frames.filter((event) => event.run_id === current).reduce(fold, new Map<string, Span>()),
    [frames, current],
  );

  const graph = useMemo(() => {
    if (!topology) return { nodes: [], edges: [] };
    const declared = stages(topology, spans);
    const live = calls(declared, spans);
    return { nodes: [...declared, ...live.nodes], edges: [...arcs(topology, spans), ...live.edges] };
  }, [topology, spans]);

  // The pick is the canvas's selection too: the node or the call it names is drawn selected.
  const nodes = useMemo(
    () =>
      graph.nodes.map((node) => ({
        ...node,
        selected:
          picked?.type === "node" ? node.id === picked.id : picked?.type === "span" && node.data.span === picked.id,
      })),
    [graph.nodes, picked],
  );

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
          <ReactFlow
            nodes={nodes}
            edges={graph.edges}
            nodeTypes={NODE_TYPES}
            onNodeClick={(_, node) =>
              setPicked(
                typeof node.data.span === "string"
                  ? { type: "span", id: node.data.span }
                  : { type: "node", id: node.id },
              )
            }
            onPaneClick={() => setPicked(null)}
            nodeOrigin={[0.5, 0]}
            fitView
            proOptions={{ hideAttribution: true }}
            colorMode="dark"
          >
            <Background gap={24} />
            <Controls showInteractive={false} />
            <FitOnGrow count={graph.nodes.length} />
          </ReactFlow>
        </div>
        {topology && <Panel topology={topology} spans={spans} picked={picked} pick={setPicked} />}
      </main>
    </div>
  );
}
