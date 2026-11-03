import { Background, Controls, ReactFlow } from "@xyflow/react";
import { useEffect, useMemo, useState } from "react";
import { fetchThreads, fetchTopology, followThread } from "./api";
import type { LiveSummary, RunEvent, Topology } from "./contract";
import { arcs, calls, stages } from "./layout";
import { NODE_TYPES } from "./nodes";
import { Panel } from "./panel";
import { fold, type Span } from "./spans";

const POLL_MS = 2000;

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
  const [picked, setPicked] = useState("");

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
    setPicked("");
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
        <span className={`online ${online ? "on" : "off"}`}>{online ? "live" : "reconnecting"}</span>
      </header>
      <main>
        <div className="canvas">
          <ReactFlow
            nodes={graph.nodes}
            edges={graph.edges}
            nodeTypes={NODE_TYPES}
            onNodeClick={(_, node) => setPicked(typeof node.data.span === "string" ? node.data.span : "")}
            nodeOrigin={[0.5, 0]}
            fitView
            proOptions={{ hideAttribution: true }}
            colorMode="dark"
          >
            <Background gap={24} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <Panel spans={spans} picked={picked} pick={setPicked} />
      </main>
    </div>
  );
}
