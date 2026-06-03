import type { NewsCategory, NewsRegion, NewsSource } from "./types";

const ACTIVE_REGIONS: readonly Exclude<NewsRegion, "global">[] = [
  "sg",
  "cn",
  "us",
  "jp",
];

const ACTIVE_CATEGORIES: readonly Exclude<NewsCategory, "general">[] = [
  "export-control",
  "trade-secrets",
  "employment",
];

const REGION_QUERY: Record<Exclude<NewsRegion, "global">, string> = {
  sg: "Singapore",
  cn: "China",
  us: '("United States" OR "U.S." OR USA)',
  jp: "Japan",
};

const REGION_LABEL: Record<Exclude<NewsRegion, "global">, string> = {
  sg: "Singapore",
  cn: "China",
  us: "United States",
  jp: "Japan",
};

const CATEGORY_LABEL: Record<Exclude<NewsCategory, "general">, string> = {
  "export-control": "Export Control",
  "trade-secrets": "Trade Secrets",
  employment: "Employment",
};

const CATEGORY_KEYWORDS: Record<Exclude<NewsCategory, "general">, string> = {
  "export-control":
    '("export control" OR "strategic goods" OR "dual-use" OR sanctions OR "entity list" OR BIS OR EAR OR ITAR OR OFAC OR MOFCOM OR METI OR TradeNet)',
  "trade-secrets":
    '("trade secret" OR "trade secrets" OR confidentiality OR "breach of confidence" OR DTSA OR "Economic Espionage" OR "anti-unfair competition" OR "Unfair Competition Prevention")',
  employment:
    '("employment law" OR "work pass" OR "work visa" OR MOM OR CPF OR "Workplace Fairness" OR EEOC OR FLSA OR "Department of Labor" OR "Labour Contract" OR "Labour Standards" OR "social insurance")',
};

function gnews(q: string): string {
  return `https://news.google.com/rss/search?q=${encodeURIComponent(q)}&hl=en-SG&gl=SG&ceid=SG:en`;
}

export const NEWS_SOURCES: NewsSource[] = ACTIVE_REGIONS.flatMap((region) =>
  ACTIVE_CATEGORIES.map<NewsSource>((category) => ({
    id: `gnews-${category}-${region}`,
    name: `Google News · ${CATEGORY_LABEL[category]} · ${REGION_LABEL[region]}`,
    category,
    region,
    url: gnews(`${REGION_QUERY[region]} ${CATEGORY_KEYWORDS[category]}`),
  })),
);
