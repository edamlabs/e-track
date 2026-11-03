import type { LiveSummary, RunEvent, Topology } from "./contract";

// Relative paths: the canvas is served at the app's root, or under the prefix a host mounts it at.
export async function fetchTopology(): Promise<Topology> {
  const reply = await fetch("api/topology");
  return (await reply.json()) as Topology;
}

export async function fetchThreads(): Promise<LiveSummary[]> {
  const reply = await fetch("api/threads");
  return (await reply.json()) as LiveSummary[];
}

// EventSource reconnects by itself and resends Last-Event-ID: the server replays what the cursor missed.
export function followThread(
  thread: string,
  onFrame: (event: RunEvent) => void,
  onState: (open: boolean) => void,
): () => void {
  const source = new EventSource(`api/threads/${encodeURIComponent(thread)}/events`);
  source.addEventListener("frame", (message) => onFrame(JSON.parse((message as MessageEvent<string>).data)));
  source.onopen = () => onState(true);
  source.onerror = () => onState(false);
  return () => source.close();
}
