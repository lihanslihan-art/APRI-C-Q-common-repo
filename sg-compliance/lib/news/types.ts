export const NEWS_CATEGORIES = [
  "export-control",
  "trade-secrets",
  "employment",
  "general",
] as const;

export type NewsCategory = (typeof NEWS_CATEGORIES)[number];

export const NEWS_REGIONS = ["sg", "cn", "us", "jp", "global"] as const;

export type NewsRegion = (typeof NEWS_REGIONS)[number];

export interface NewsSource {
  id: string;
  name: string;
  category: NewsCategory;
  region: NewsRegion;
  url: string;
}

export interface NewsItem {
  id: string;
  sourceId: string;
  sourceName: string;
  category: NewsCategory;
  region: NewsRegion;
  title: string;
  link: string;
  snippet: string;
  publishedAt: string;
  fetchedAt: string;
}

export interface NewsStore {
  updatedAt: string;
  items: NewsItem[];
}
