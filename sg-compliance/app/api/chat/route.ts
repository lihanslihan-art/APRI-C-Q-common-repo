import { NextResponse } from "next/server";
import { i18n, type Locale } from "@/lib/i18n-config";
import { buildSystemPrompt } from "@/lib/ai/context";
import { streamDeepSeek, type ChatMessage } from "@/lib/ai/deepseek";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_TURNS = 10;
const MAX_USER_LEN = 4000;

interface ChatRequest {
  locale?: string;
  messages?: Array<{ role: "user" | "assistant"; content: string }>;
}

export async function POST(req: Request) {
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      {
        error: "missing_api_key",
        message:
          "DEEPSEEK_API_KEY is not configured on the server. Add it to /etc/sg-compliance/env and restart sg-compliance.service.",
      },
      { status: 503 },
    );
  }

  let body: ChatRequest;
  try {
    body = (await req.json()) as ChatRequest;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }

  const locale = (i18n.locales as readonly string[]).includes(body.locale ?? "")
    ? (body.locale as Locale)
    : i18n.defaultLocale;

  const turns = (body.messages ?? [])
    .filter(
      (m) =>
        m &&
        (m.role === "user" || m.role === "assistant") &&
        typeof m.content === "string" &&
        m.content.trim().length > 0,
    )
    .slice(-MAX_TURNS);

  if (turns.length === 0 || turns[turns.length - 1].role !== "user") {
    return NextResponse.json({ error: "no_user_message" }, { status: 400 });
  }
  if (turns[turns.length - 1].content.length > MAX_USER_LEN) {
    return NextResponse.json({ error: "message_too_long" }, { status: 400 });
  }

  const systemPrompt = await buildSystemPrompt(locale);
  const messages: ChatMessage[] = [
    { role: "system", content: systemPrompt },
    ...turns.map((m) => ({ role: m.role, content: m.content })),
  ];

  try {
    const stream = await streamDeepSeek({ apiKey, messages });
    return new Response(stream, {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: "upstream_failed", message: msg },
      { status: 502 },
    );
  }
}
