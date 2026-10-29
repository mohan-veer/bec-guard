import type { CheckEvent, SampleRecords, ScenarioItem } from "./types";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json() as Promise<T>;
}

export const fetchScenarios = () => getJson<ScenarioItem[]>("/api/scenarios");
export const fetchHealth = () => getJson<{ llm_mode: string; tavily_mode: string }>("/healthz");
export const fetchRecords = () => getJson<SampleRecords>("/api/sample-records");

/** POSTs and calls onEvent for each NDJSON line as it arrives (the server streams check progress). */
export async function streamCheck(
  url: string,
  body: BodyInit | null,
  onEvent: (e: CheckEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch(url, { method: "POST", body, signal, headers: body ? { "content-type": "message/rfc822" } : {} });
  if (!res.ok || !res.body) {
    const detail = await res.json().then((j) => j.detail as string).catch(() => null);
    throw new Error(detail ?? `Check failed (${res.status})`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line) as CheckEvent);
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as CheckEvent);
}
