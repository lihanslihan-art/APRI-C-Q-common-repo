import type { NewsItem } from "@/lib/news/types";

const CATEGORY_COLOR: Record<string, string> = {
  "export-control": "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  "trade-secrets": "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300",
  employment: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  general: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

const REGION_FLAG: Record<string, string> = {
  sg: "🇸🇬",
  cn: "🇨🇳",
  us: "🇺🇸",
  jp: "🇯🇵",
  global: "🌐",
};

function formatDate(iso: string, locale: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-SG", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function NewsCard({
  item,
  locale,
  categoryLabel,
  regionLabel,
}: {
  item: NewsItem;
  locale: string;
  categoryLabel: string;
  regionLabel: string;
}) {
  return (
    <a
      href={item.link}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col rounded-xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-slate-900 hover:shadow-md dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-100"
    >
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
        <span
          className={`rounded-full px-2 py-0.5 font-medium uppercase tracking-wide ${CATEGORY_COLOR[item.category] ?? CATEGORY_COLOR.general}`}
        >
          {categoryLabel}
        </span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          {REGION_FLAG[item.region] ?? ""} {regionLabel}
        </span>
        <span className="text-slate-500 dark:text-slate-400">
          {formatDate(item.publishedAt, locale)}
        </span>
        <span className="truncate text-slate-400 dark:text-slate-500">
          · {item.sourceName}
        </span>
      </div>
      <h3 className="text-base font-semibold leading-snug text-slate-900 group-hover:underline dark:text-slate-100">
        {item.title}
      </h3>
      {item.snippet && (
        <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
          {item.snippet}
        </p>
      )}
    </a>
  );
}
