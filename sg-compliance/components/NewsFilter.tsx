"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const CATEGORY_KEYS = [
  "all",
  "export-control",
  "trade-secrets",
  "employment",
  "general",
] as const;

export function NewsFilter({
  labels,
  active,
}: {
  labels: Record<string, string>;
  active: string;
}) {
  const pathname = usePathname() ?? "";
  const params = useSearchParams();
  const buildHref = (cat: string) => {
    const sp = new URLSearchParams(params?.toString() ?? "");
    if (cat === "all") sp.delete("cat");
    else sp.set("cat", cat);
    const qs = sp.toString();
    return qs ? `${pathname}?${qs}` : pathname;
  };
  return (
    <div className="flex flex-wrap gap-2">
      {CATEGORY_KEYS.map((cat) => {
        const isActive = active === cat;
        return (
          <Link
            key={cat}
            href={buildHref(cat)}
            className={
              isActive
                ? "rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white dark:bg-slate-100 dark:text-slate-900"
                : "rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 transition hover:border-slate-900 hover:text-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-100 dark:hover:text-slate-100"
            }
          >
            {labels[cat] ?? cat}
          </Link>
        );
      })}
    </div>
  );
}
