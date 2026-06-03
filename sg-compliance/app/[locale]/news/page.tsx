import Link from "next/link";
import type { Locale } from "@/lib/i18n-config";
import { getDictionary } from "@/lib/dictionary";
import { loadStore } from "@/lib/news/storage";
import { NEWS_CATEGORIES, NEWS_REGIONS } from "@/lib/news/types";
import { NewsCard } from "@/components/NewsCard";
import { NewsFilter } from "@/components/NewsFilter";

export const dynamic = "force-dynamic";

function formatUpdated(iso: string, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(locale === "zh" ? "zh-CN" : "en-SG", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default async function NewsPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ cat?: string; region?: string }>;
}) {
  const { locale } = await params;
  const { cat, region } = await searchParams;
  const typed = locale as Locale;
  const dict = await getDictionary(typed);
  const store = await loadStore();

  const activeCat = (NEWS_CATEGORIES as readonly string[]).includes(cat ?? "")
    ? cat!
    : "all";
  const activeRegion = (NEWS_REGIONS as readonly string[]).includes(region ?? "")
    ? region!
    : "all";

  const items = store.items.filter((it) => {
    if (activeCat !== "all" && it.category !== activeCat) return false;
    if (activeRegion !== "all" && it.region !== activeRegion) return false;
    return true;
  });

  const categoryLabels: Record<string, string> = {
    all: dict.news.filterAll,
    "export-control": dict.news.categories.exportControl,
    "trade-secrets": dict.news.categories.tradeSecrets,
    employment: dict.news.categories.employment,
    general: dict.news.categories.general,
  };

  const regionLabels: Record<string, string> = {
    all: dict.news.filterAll,
    sg: dict.news.regions.sg,
    cn: dict.news.regions.cn,
    us: dict.news.regions.us,
    jp: dict.news.regions.jp,
    global: dict.news.regions.global,
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <Link
        href={`/${typed}`}
        className="text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
      >
        ← {dict.common.backToHome}
      </Link>
      <h1 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
        {dict.news.heading}
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-600 dark:text-slate-400">
        {dict.news.subheading}
      </p>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-500">
        {dict.news.lastRefresh}: {formatUpdated(store.updatedAt, typed)} ·{" "}
        {items.length} / {store.items.length} {dict.news.itemsCount}
      </p>

      <div className="mt-6">
        <NewsFilter
          categoryLabels={categoryLabels}
          regionLabels={regionLabels}
          activeCategory={activeCat}
          activeRegion={activeRegion}
          categoryGroupLabel={dict.news.filterCategory}
          regionGroupLabel={dict.news.filterRegion}
        />
      </div>

      {items.length === 0 ? (
        <div className="mt-10 rounded-xl border border-dashed border-slate-300 bg-slate-50/50 p-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-400">
          {dict.news.empty}
        </div>
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {items.map((item) => (
            <NewsCard
              key={item.id}
              item={item}
              locale={typed}
              categoryLabel={categoryLabels[item.category] ?? item.category}
              regionLabel={regionLabels[item.region] ?? item.region}
            />
          ))}
        </div>
      )}
    </div>
  );
}
