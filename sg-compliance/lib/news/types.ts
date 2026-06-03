export const NEWS_CATEGORIES = [
  "export-control",
  "trade-secrets",
  "employment",
  "general",
] as const;

export type NewsCategory = (typeof NEWS_CATEGORIES)[number];

export interface NewsSource {
  id: string;
  name: string;
  category: NewsCategory;
  url: string;
}

export interface NewsItem {
  id: string;
  sourceId: string;
  sourceName: string;
  category: NewsCategory;
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
