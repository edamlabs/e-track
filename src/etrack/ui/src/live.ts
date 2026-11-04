import { createContext, useContext } from "react";
import { type Activity, IDLE } from "./layout";

// The run's light, handed to the declared nodes without rebuilding them: the canvas's nodes keep their identity, so
// React Flow keeps their measures, and only the nodes whose light changed render again.
export interface Live {
  activity: Map<string, Activity>;
  picked: string;
}

export const LiveContext = createContext<Live>({ activity: new Map(), picked: "" });

export function useActivity(id: string): { activity: Activity; picked: boolean } {
  const live = useContext(LiveContext);
  return { activity: live.activity.get(id) ?? IDLE, picked: live.picked === id };
}
