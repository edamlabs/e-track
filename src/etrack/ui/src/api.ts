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

// The stream's state as a person reads it: no thread chosen, opening, open, or lost and being retried.
export type Link = "idle" | "connecting" | "live" | "reconnecting";

// EventSource reconnects by itself and resends Last-Event-ID: the server replays what the cursor missed.
export function followThread(
  thread: string,
  onFrame: (event: RunEvent) => void,
  onState: (link: Link) => void,
): () => void {
  onState("connecting");
  const source = new EventSource(`api/threads/${encodeURIComponent(thread)}/events`);
  source.addEventListener("frame", (message) => onFrame(JSON.parse((message as MessageEvent<string>).data)));
  source.onopen = () => onState("live");
  source.onerror = () => onState("reconnecting");
  return () => {
    source.close();
    onState("idle");
  };
}
