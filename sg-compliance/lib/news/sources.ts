import type { NewsSource } from "./types";

const gnews = (q: string) =>
  `https://news.google.com/rss/search?q=${encodeURIComponent(q)}&hl=en-SG&gl=SG&ceid=SG:en`;

export const NEWS_SOURCES: NewsSource[] = [
  {
    id: "gnews-export-control",
    name: "Google News · Export Control",
    category: "export-control",
    url: gnews(
      "Singapore (export control OR strategic goods OR sanctions OR TradeNet) when:30d",
    ),
  },
  {
    id: "gnews-trade-secrets",
    name: "Google News · Trade Secrets",
    category: "trade-secrets",
    url: gnews(
      "Singapore (trade secret OR confidentiality OR breach of confidence OR Computer Misuse Act) when:30d",
    ),
  },
  {
    id: "gnews-employment",
    name: "Google News · Employment",
    category: "employment",
    url: gnews(
      "Singapore (MOM OR work pass OR Employment Pass OR Employment Act OR CPF OR Workplace Fairness) when:30d",
    ),
  },
  {
    id: "bt-government-economy",
    name: "Business Times · Government & Economy",
    category: "general",
    url: "https://www.businesstimes.com.sg/rss/government-economy",
  },
];
