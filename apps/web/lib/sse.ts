const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type AskStreamInput = {
  question: string;
  datasourceId: number;
  deepThink?: boolean;
  executionMode?: string;
};

export type SseEvent = {
  eventType: string;
  data: Record<string, unknown>;
};

export type AskStreamResult = {
  sessionId: string | null;
};

async function consumeSse(
  response: Response,
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal
): Promise<AskStreamResult> {
  const sessionId = response.headers.get("X-Session-Id");

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("Response body is not readable");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    if (signal?.aborted) {
      await reader.cancel();
      throw new DOMException("Aborted", "AbortError");
    }

    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      if (!part.trim()) continue;
      const event = parseSseBlock(part);
      if (event) {
        if (!sessionId && event.data.session_id) {
          // fallback if header missing
        }
        onEvent(event);
      }
    }
  }

  return { sessionId };
}

export async function askStream(
  input: AskStreamInput,
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal
): Promise<AskStreamResult> {
  const response = await fetch(`${API_URL}/api/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: input.question,
      datasource_id: input.datasourceId,
      deep_think: input.deepThink ?? false,
      execution_mode: input.executionMode ?? "AUTO",
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`SSE request failed: ${response.status}`);
  }

  const sessionId = response.headers.get("X-Session-Id");
  await consumeSse(response, onEvent, signal);
  return { sessionId };
}

export async function stopStream(sessionId: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/ask/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!response.ok) {
    throw new Error(`Stop request failed: ${response.status}`);
  }
}

export async function resumeStream(
  sessionId: string,
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal
): Promise<AskStreamResult> {
  const response = await fetch(`${API_URL}/api/ask/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Resume request failed: ${response.status}`);
  }

  const headerSessionId = response.headers.get("X-Session-Id");
  await consumeSse(response, onEvent, signal);
  return { sessionId: headerSessionId ?? sessionId };
}

function parseSseBlock(block: string): SseEvent | null {
  let eventType = "message";
  let dataStr = "";

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataStr += line.slice(5).trim();
    }
  }

  if (!dataStr) return null;

  try {
    return { eventType, data: JSON.parse(dataStr) };
  } catch {
    return { eventType, data: { raw: dataStr } };
  }
}
