"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const CATEGORY_KEYS = [
  "all",
  "export-control",
  "trade-secrets",
  "employment",
] as const;

const REGION_KEYS = ["all", "sg", "cn", "us", "jp"] as const;

const REGION_FLAG: Record<string, string> = {
  sg: "🇸🇬",
  cn: "🇨🇳",
  us: "🇺🇸",
  jp: "🇯🇵",
};

function pillClass(active: boolean) {
  return active
    ? "rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white dark:bg-slate-100 dark:text-slate-900"
    : "rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 transition hover:border-slate-900 hover:text-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-100 dark:hover:text-slate-100";
}

export function NewsFilter({
  categoryLabels,
  regionLabels,
  activeCategory,
  activeRegion,
  categoryGroupLabel,
  regionGroupLabel,
}: {
  categoryLabels: Record<string, string>;
  regionLabels: Record<string, string>;
  activeCategory: string;
  activeRegion: string;
  categoryGroupLabel: string;
  regionGroupLabel: string;
}) {
  const pathname = usePathname() ?? "";
  const params = useSearchParams();

  const buildHref = (key: "cat" | "region", value: string) => {
    const sp = new URLSearchParams(params?.toString() ?? "");
    if (value === "all") sp.delete(key);
    else sp.set(key, value);
    const qs = sp.toString();
    return qs ? `${pathname}?${qs}` : pathname;
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {categoryGroupLabel}
        </span>
        {CATEGORY_KEYS.map((cat) => (
          <Link
            key={cat}
            href={buildHref("cat", cat)}
            className={pillClass(activeCategory === cat)}
          >
            {categoryLabels[cat] ?? cat}
          </Link>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {regionGroupLabel}
        </span>
        {REGION_KEYS.map((region) => (
          <Link
            key={region}
            href={buildHref("region", region)}
            className={pillClass(activeRegion === region)}
          >
            {region !== "all" && REGION_FLAG[region]
              ? `${REGION_FLAG[region]} ${regionLabels[region]}`
              : regionLabels[region] ?? region}
          </Link>
        ))}
      </div>
    </div>
  );
}
