"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatStrings {
  inputPlaceholder: string;
  send: string;
  stop: string;
  thinking: string;
  errorPrefix: string;
  empty: string;
  exampleHeading: string;
  examples: string[];
  disclaimer: string;
  you: string;
  assistant: string;
}

export function Chat({
  locale,
  strings,
}: {
  locale: string;
  strings: ChatStrings;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function send(text: string) {
    if (!text.trim() || loading) return;
    const userMsg: Message = { role: "user", content: text.trim() };
    const next: Message[] = [...messages, userMsg];
    setMessages([...next, { role: "assistant", content: "" }]);

    const ac = new AbortController();
    abortRef.current = ac;
    setLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ locale, messages: next }),
        signal: ac.signal,
      });

      if (!res.ok || !res.body) {
        const detail = await res.text().catch(() => "");
        const note = (() => {
          try {
            const obj = JSON.parse(detail) as { message?: string; error?: string };
            return obj.message || obj.error || detail;
          } catch {
            return detail || `HTTP ${res.status}`;
          }
        })();
        setMessages([
          ...next,
          { role: "assistant", content: `${strings.errorPrefix}: ${note}` },
        ]);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let acc = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        setMessages([...next, { role: "assistant", content: acc }]);
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setMessages([
        ...next,
        {
          role: "assistant",
          content: `${strings.errorPrefix}: ${(err as Error).message}`,
        },
      ]);
    } finally {
      setLoading(false);
      abortRef.current = null;
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input;
    setInput("");
    send(text);
  }

  function onStop() {
    abortRef.current?.abort();
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <div
        ref={scrollerRef}
        className="flex-1 space-y-5 overflow-y-auto rounded-xl border border-slate-200 bg-slate-50/50 p-4 dark:border-slate-800 dark:bg-slate-900/30"
      >
        {messages.length === 0 ? (
          <div className="mx-auto max-w-xl py-8 text-center text-sm text-slate-500 dark:text-slate-400">
            <p className="mb-6">{strings.empty}</p>
            <p className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
              {strings.exampleHeading}
            </p>
            <div className="flex flex-col gap-2">
              {strings.examples.map((ex, i) => (
                <button
                  key={i}
                  onClick={() => send(ex)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-700 transition hover:border-slate-900 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-slate-100 dark:hover:text-slate-100"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className="flex flex-col gap-1">
              <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {m.role === "user" ? strings.you : strings.assistant}
              </div>
              {m.role === "user" ? (
                <div className="whitespace-pre-wrap rounded-xl bg-slate-900 px-4 py-3 text-sm text-white dark:bg-slate-100 dark:text-slate-900">
                  {m.content}
                </div>
              ) : (
                <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-900 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100">
                  {m.content ? (
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        p: ({ children }) => (
                          <p className="mb-2 last:mb-0">{children}</p>
                        ),
                        ul: ({ children }) => (
                          <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>
                        ),
                        ol: ({ children }) => (
                          <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>
                        ),
                        li: ({ children }) => <li>{children}</li>,
                        strong: ({ children }) => (
                          <strong className="font-semibold">{children}</strong>
                        ),
                        em: ({ children }) => <em className="italic">{children}</em>,
                        code: ({ children }) => (
                          <code className="rounded bg-slate-100 px-1 py-0.5 text-[12px] dark:bg-slate-800">
                            {children}
                          </code>
                        ),
                        pre: ({ children }) => (
                          <pre className="my-2 overflow-x-auto rounded-lg bg-slate-100 p-3 text-xs dark:bg-slate-800">
                            {children}
                          </pre>
                        ),
                        a: ({ href, children }) => (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 underline hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                          >
                            {children}
                          </a>
                        ),
                        h1: ({ children }) => (
                          <h3 className="mt-3 mb-2 text-base font-semibold">{children}</h3>
                        ),
                        h2: ({ children }) => (
                          <h3 className="mt-3 mb-2 text-base font-semibold">{children}</h3>
                        ),
                        h3: ({ children }) => (
                          <h3 className="mt-3 mb-2 text-base font-semibold">{children}</h3>
                        ),
                        blockquote: ({ children }) => (
                          <blockquote className="my-2 border-l-2 border-slate-300 pl-3 text-slate-600 dark:border-slate-600 dark:text-slate-400">
                            {children}
                          </blockquote>
                        ),
                        table: ({ children }) => (
                          <div className="my-2 overflow-x-auto">
                            <table className="min-w-full border-collapse text-xs">
                              {children}
                            </table>
                          </div>
                        ),
                        th: ({ children }) => (
                          <th className="border border-slate-300 bg-slate-100 px-2 py-1 text-left font-semibold dark:border-slate-700 dark:bg-slate-800">
                            {children}
                          </th>
                        ),
                        td: ({ children }) => (
                          <td className="border border-slate-300 px-2 py-1 dark:border-slate-700">
                            {children}
                          </td>
                        ),
                      }}
                    >
                      {m.content}
                    </ReactMarkdown>
                  ) : loading && i === messages.length - 1 ? (
                    <span className="text-slate-500 dark:text-slate-400">
                      {strings.thinking}
                    </span>
                  ) : null}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <form onSubmit={onSubmit} className="mt-3 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit(e as unknown as FormEvent);
            }
          }}
          rows={2}
          placeholder={strings.inputPlaceholder}
          className="flex-1 resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-100"
          disabled={loading}
        />
        {loading ? (
          <button
            type="button"
            onClick={onStop}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:border-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-100"
          >
            {strings.stop}
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim()}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-40 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
          >
            {strings.send}
          </button>
        )}
      </form>
      <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-500">
        {strings.disclaimer}
      </p>
    </div>
  );
}
