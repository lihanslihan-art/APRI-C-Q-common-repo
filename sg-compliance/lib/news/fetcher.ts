import "server-only";
import Parser from "rss-parser";
import { createHash } from "node:crypto";
import type { NewsItem, NewsSource } from "./types";

const parser = new Parser({
  timeout: 12000,
  headers: { "User-Agent": "sg-compliance-news/0.1 (+https://github.com/lihanslihan-art/APRI-C-Q-common-repo)" },
});

function hash(s: string): string {
  return createHash("sha1").update(s).digest("hex").slice(0, 12);
}

function stripHtml(s: string): string {
  return s.replace(/<[^>]+>/g, "").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&");
}

function cleanSnippet(s: string | undefined, limit = 220): string {
  if (!s) return "";
  const cleaned = stripHtml(s).replace(/\s+/g, " ").trim();
  return cleaned.length > limit ? cleaned.slice(0, limit - 1).trimEnd() + "…" : cleaned;
}

export async function fetchSource(source: NewsSource): Promise<NewsItem[]> {
  const feed = await parser.parseURL(source.url);
  const now = new Date().toISOString();
  const items: NewsItem[] = [];
  for (const it of feed.items || []) {
    const link = (it.link || "").trim();
    const title = (it.title || "").trim();
    if (!link || !title) continue;
    items.push({
      id: hash(link),
      sourceId: source.id,
      sourceName: source.name,
      category: source.category,
      title,
      link,
      snippet: cleanSnippet(it.contentSnippet || it.content || it.summary),
      publishedAt: it.isoDate || it.pubDate || now,
      fetchedAt: now,
    });
  }
  return items;
}

export interface FetchResult {
  items: NewsItem[];
  errors: Array<{ sourceId: string; error: string }>;
}

export async function fetchAll(sources: NewsSource[]): Promise<FetchResult> {
  const errors: FetchResult["errors"] = [];
  const items: NewsItem[] = [];
  const results = await Promise.allSettled(sources.map(fetchSource));
  results.forEach((res, i) => {
    if (res.status === "fulfilled") {
      items.push(...res.value);
    } else {
      errors.push({
        sourceId: sources[i].id,
        error: res.reason instanceof Error ? res.reason.message : String(res.reason),
      });
    }
  });
  return { items, errors };
}
