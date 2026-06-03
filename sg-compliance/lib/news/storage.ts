import "server-only";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { NewsItem, NewsStore } from "./types";

const STORE_PATH = resolve(process.cwd(), "data", "news.json");
const MAX_ITEMS = 200;
const EMPTY: NewsStore = { updatedAt: "", items: [] };

export async function loadStore(): Promise<NewsStore> {
  try {
    const txt = await readFile(STORE_PATH, "utf8");
    const parsed = JSON.parse(txt) as NewsStore;
    if (!Array.isArray(parsed.items)) return EMPTY;
    return parsed;
  } catch {
    return EMPTY;
  }
}

async function saveStore(store: NewsStore): Promise<void> {
  await mkdir(dirname(STORE_PATH), { recursive: true });
  await writeFile(STORE_PATH, JSON.stringify(store, null, 2), "utf8");
}

export async function mergeItems(incoming: NewsItem[]): Promise<NewsStore> {
  const existing = await loadStore();
  const map = new Map<string, NewsItem>();
  for (const it of existing.items) map.set(it.id, it);
  for (const it of incoming) {
    const prev = map.get(it.id);
    map.set(it.id, prev ? { ...prev, fetchedAt: it.fetchedAt } : it);
  }
  const merged = Array.from(map.values())
    .filter((it) => it.title && it.link)
    .sort((a, b) => (b.publishedAt || "").localeCompare(a.publishedAt || ""))
    .slice(0, MAX_ITEMS);
  const store: NewsStore = {
    updatedAt: new Date().toISOString(),
    items: merged,
  };
  await saveStore(store);
  return store;
}
