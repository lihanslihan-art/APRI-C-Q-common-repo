import "server-only";

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface LLMOptions {
  apiKey: string;
  baseUrl?: string;
  model?: string;
  messages: ChatMessage[];
  temperature?: number;
  signal?: AbortSignal;
}

const DEFAULT_BASE = "https://api.lkeap.cloud.tencent.com/plan/v3";
const DEFAULT_MODEL = "glm-5.1";

export async function streamChat(
  opts: LLMOptions,
): Promise<ReadableStream<Uint8Array>> {
  const base = (opts.baseUrl ?? DEFAULT_BASE).replace(/\/+$/, "");
  const upstream = await fetch(`${base}/chat/completions`, {
    method: "POST",
    signal: opts.signal,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${opts.apiKey}`,
    },
    body: JSON.stringify({
      model: opts.model ?? DEFAULT_MODEL,
      messages: opts.messages,
      stream: true,
      temperature: opts.temperature ?? 0.3,
    }),
  });

  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => "");
    throw new Error(`LLM upstream ${upstream.status}: ${detail.slice(0, 400)}`);
  }

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const reader = upstream.body!.getReader();
      const decoder = new TextDecoder();
      const encoder = new TextEncoder();
      let buffer = "";
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const raw of lines) {
            const line = raw.trim();
            if (!line.startsWith("data:")) continue;
            const data = line.slice(5).trim();
            if (data === "[DONE]") {
              controller.close();
              return;
            }
            try {
              const chunk = JSON.parse(data) as {
                choices?: Array<{ delta?: { content?: string } }>;
              };
              const delta = chunk.choices?.[0]?.delta?.content;
              if (delta) controller.enqueue(encoder.encode(delta));
            } catch {
              // partial JSON or keepalive — skip
            }
          }
        }
        controller.close();
      } catch (err) {
        controller.error(err);
      }
    },
  });
}
