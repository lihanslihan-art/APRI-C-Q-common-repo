import Link from "next/link";
import { i18n, type Locale } from "@/lib/i18n-config";
import { getDictionary } from "@/lib/dictionary";
import { ModuleCard } from "@/components/ModuleCard";

export async function generateStaticParams() {
  return i18n.locales.map((locale) => ({ locale }));
}

export default async function Home({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const typed = locale as Locale;
  const dict = await getDictionary(typed);

  const modules = [
    {
      href: `/${typed}/export-control`,
      ...dict.modules.exportControl,
    },
    {
      href: `/${typed}/trade-secrets`,
      ...dict.modules.tradeSecrets,
    },
    {
      href: `/${typed}/employment`,
      ...dict.modules.employment,
    },
  ];

  return (
    <div className="mx-auto max-w-6xl px-4">
      <section className="py-14 sm:py-20">
        <span className="inline-block rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          {dict.home.phaseBadge}
        </span>
        <h1 className="mt-4 text-3xl font-bold tracking-tight sm:text-5xl">
          {dict.home.heroTitle}
        </h1>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-slate-600 dark:text-slate-400 sm:text-lg">
          {dict.home.heroSubtitle}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <a
            href="#modules"
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
          >
            {dict.home.ctaModules}
          </a>
          <a
            href="#chat"
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:border-slate-900 hover:text-slate-900 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-100 dark:hover:text-slate-100"
          >
            {dict.home.ctaChat}
          </a>
        </div>
      </section>

      <section id="modules" className="py-6">
        <h2 className="text-xl font-semibold tracking-tight">
          {dict.home.modulesTitle}
        </h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((m) => (
            <ModuleCard
              key={m.href}
              href={m.href}
              title={m.title}
              summary={m.summary}
              status={m.status}
            />
          ))}
        </div>
      </section>

      <section className="py-10">
        <h2 className="text-xl font-semibold tracking-tight">
          {dict.home.newsTitle}
        </h2>
        <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50/50 p-6 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-400">
          {dict.home.newsPlaceholder}
        </div>
      </section>

      <section id="chat" className="pb-14">
        <h2 className="text-xl font-semibold tracking-tight">
          {dict.home.chatTitle}
        </h2>
        <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50/50 p-6 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-400">
          {dict.home.chatPlaceholder}
        </div>
      </section>
    </div>
  );
}
