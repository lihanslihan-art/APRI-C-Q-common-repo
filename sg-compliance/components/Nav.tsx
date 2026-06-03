import Link from "next/link";
import type { Locale } from "@/lib/i18n-config";
import type { Dictionary } from "@/lib/dictionary";
import { LanguageSwitcher } from "./LanguageSwitcher";

export function Nav({ locale, dict }: { locale: Locale; dict: Dictionary }) {
  const links = [
    { href: `/${locale}`, label: dict.nav.home },
    { href: `/${locale}/export-control`, label: dict.nav.exportControl },
    { href: `/${locale}/trade-secrets`, label: dict.nav.tradeSecrets },
    { href: `/${locale}/employment`, label: dict.nav.employment },
    { href: `/${locale}/news`, label: dict.nav.news },
  ];
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/80 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link href={`/${locale}`} className="text-sm font-semibold tracking-tight">
          {dict.site.name}
        </Link>
        <nav className="hidden flex-1 items-center gap-5 text-sm sm:flex">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="text-slate-600 transition hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            >
              {l.label}
            </Link>
          ))}
          <span className="text-slate-400 dark:text-slate-600">·</span>
          <span className="text-slate-400 dark:text-slate-600">{dict.nav.chat}</span>
        </nav>
        <div className="ml-auto sm:ml-0">
          <LanguageSwitcher currentLocale={locale} label={dict.nav.switchLang} />
        </div>
      </div>
    </header>
  );
}
