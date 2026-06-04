import "server-only";
import { getDictionary } from "./dictionary";
import { loadStore } from "./news/storage";
import type { Locale } from "./i18n-config";
import type { NewsItem } from "./news/types";

const MODULE_KEYS = ["exportControl", "tradeSecrets", "employment"] as const;
type ModuleKey = (typeof MODULE_KEYS)[number];

const MODULE_PATH: Record<ModuleKey, string> = {
  exportControl: "export-control",
  tradeSecrets: "trade-secrets",
  employment: "employment",
};

export interface ModuleHit {
  moduleKey: ModuleKey;
  moduleHeading: string;
  sectionTitle: string;
  matches: string[];
  href: string;
}

export interface SearchResults {
  query: string;
  modules: ModuleHit[];
  news: NewsItem[];
  totalNewsMatches: number;
}

const MAX_NEWS = 30;

export async function search(
  locale: Locale,
  rawQuery: string,
): Promise<SearchResults> {
  const q = rawQuery.trim();
  const needle = q.toLowerCase();
  if (!needle) {
    return { query: q, modules: [], news: [], totalNewsMatches: 0 };
  }

  const dict = await getDictionary(locale);
  const moduleHits: ModuleHit[] = [];

  for (const key of MODULE_KEYS) {
    const mod = dict[key];
    const headingHit = mod.heading.toLowerCase().includes(needle);
    for (const section of Object.values(mod.sections)) {
      const matches = section.items.filter((it) =>
        it.toLowerCase().includes(needle),
      );
      const sectionTitleHit = section.title.toLowerCase().includes(needle);
      if (matches.length || sectionTitleHit || headingHit) {
        moduleHits.push({
          moduleKey: key,
          moduleHeading: mod.heading,
          sectionTitle: section.title,
          matches: matches.length ? matches : section.items.slice(0, 1),
          href: `/${locale}/${MODULE_PATH[key]}`,
        });
      }
    }
  }

  const store = await loadStore();
  const newsAll = store.items.filter(
    (it) =>
      it.title.toLowerCase().includes(needle) ||
      (it.snippet ?? "").toLowerCase().includes(needle) ||
      it.sourceName.toLowerCase().includes(needle),
  );

  return {
    query: q,
    modules: moduleHits,
    news: newsAll.slice(0, MAX_NEWS),
    totalNewsMatches: newsAll.length,
  };
}
