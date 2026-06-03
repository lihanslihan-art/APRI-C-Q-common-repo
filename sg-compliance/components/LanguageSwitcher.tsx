"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { i18n, type Locale } from "@/lib/i18n-config";

export function LanguageSwitcher({
  currentLocale,
  label,
}: {
  currentLocale: Locale;
  label: string;
}) {
  const pathname = usePathname() ?? "/";
  const other = i18n.locales.find((l) => l !== currentLocale) ?? i18n.defaultLocale;
  const stripped = pathname.replace(new RegExp(`^/${currentLocale}(?=/|$)`), "") || "/";
  const href = `/${other}${stripped === "/" ? "" : stripped}`;
  return (
    <Link
      href={href}
      className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:border-slate-900 hover:text-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-100 dark:hover:text-slate-100"
    >
      {label}
    </Link>
  );
}
