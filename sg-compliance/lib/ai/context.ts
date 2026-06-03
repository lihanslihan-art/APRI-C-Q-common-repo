import "server-only";
import { getDictionary } from "@/lib/dictionary";
import { loadStore } from "@/lib/news/storage";
import type { Locale } from "@/lib/i18n-config";
import type { NewsItem } from "@/lib/news/types";

interface ModuleSection {
  title: string;
  items: string[];
}

interface ModuleContent {
  heading: string;
  lead: string;
  sections: Record<string, ModuleSection>;
}

function formatModule(mod: ModuleContent): string {
  const sections = Object.values(mod.sections)
    .map(
      (s) =>
        `**${s.title}**\n` + s.items.map((it) => `- ${it}`).join("\n"),
    )
    .join("\n\n");
  return `### ${mod.heading}\n\n${mod.lead}\n\n${sections}`;
}

function formatNews(items: NewsItem[]): string {
  return items
    .slice(0, 30)
    .map((it, i) => {
      const date = (it.publishedAt || "").slice(0, 10) || "????-??-??";
      return `${i + 1}. [${it.region.toUpperCase()} · ${it.category}] ${it.title} — ${date} — ${it.link}`;
    })
    .join("\n");
}

export async function buildSystemPrompt(locale: Locale): Promise<string> {
  const dict = await getDictionary(locale);
  const store = await loadStore();

  const modulesBody = [
    formatModule(dict.exportControl),
    formatModule(dict.tradeSecrets),
    formatModule(dict.employment),
  ].join("\n\n");

  const newsBody = store.items.length
    ? formatNews(store.items)
    : "(no news fetched yet)";

  const langInstruction =
    locale === "zh"
      ? "始终用简体中文回答。"
      : "Always respond in English.";

  return `You are the AI compliance assistant for "SG Compliance Hub", a Singapore-focused regulatory information POC. You help users navigate Singapore compliance frameworks (export control, trade secrets, employment) and recent regulatory developments across Singapore, China, the United States, and Japan.

Operating rules:
- ${langInstruction}
- Ground every factual claim in the reference material below. If the material does not cover a question, say so plainly instead of guessing.
- When referencing a compliance module, name it (e.g. "the Export Control module"). When referencing a news item, cite its title and region in brackets, e.g. "[CN · export-control] <title>".
- Be concise. Prefer short paragraphs and tight bullet lists.
- Always end any substantive answer with: "Informational only — not legal advice. Consult a qualified Singapore practitioner for matters of legal consequence." (Localise to Chinese when answering in Chinese: "仅供信息参考，不构成法律意见。如涉法律后果请咨询新加坡执业律师。")
- If the user asks something outside Singapore / regional compliance (e.g. coding help, personal advice), politely redirect.

=== Reference 1 · Singapore Compliance Modules ===

${modulesBody}

=== Reference 2 · Recent Regional Compliance News (top 30 most recent) ===

${newsBody}

=== End of reference material ===`;
}
