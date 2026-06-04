import Link from "next/link";
import { i18n, type Locale } from "@/lib/i18n-config";
import { getDictionary } from "@/lib/dictionary";
import { search } from "@/lib/search";
import { SearchBox } from "@/components/SearchBox";
import { NewsCard } from "@/components/NewsCard";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const dict = await getDictionary(locale as Locale);
  return { title: `${dict.search.heading} · ${dict.site.name}` };
}

function highlight(text: string, needle: string) {
  if (!needle) return text;
  const idx = text.toLowerCase().indexOf(needle.toLowerCase());
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="rounded bg-amber-200 px-0.5 dark:bg-amber-700/60 dark:text-amber-100">
        {text.slice(idx, idx + needle.length)}
      </mark>
      {text.slice(idx + needle.length)}
    </>
  );
}

export default async function SearchPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ q?: string }>;
}) {
  const { locale } = await params;
  const { q } = await searchParams;
  const typed = (i18n.locales as readonly string[]).includes(locale)
    ? (locale as Locale)
    : i18n.defaultLocale;

  const dict = await getDictionary(typed);
  const query = (q ?? "").slice(0, 200);
  const results = await search(typed, query);

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">{dict.search.heading}</h1>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{dict.search.subheading}</p>

      <div className="mt-6">
        <SearchBox
          locale={typed}
          placeholder={dict.search.inputPlaceholder}
          defaultValue={results.query}
          size="lg"
        />
      </div>

      {!results.query ? (
        <p className="mt-10 text-sm text-slate-500 dark:text-slate-400">{dict.search.empty}</p>
      ) : results.modules.length === 0 && results.news.length === 0 ? (
        <p className="mt-10 text-sm text-slate-500 dark:text-slate-400">
          {dict.search.noResults.replace("{q}", results.query)}
        </p>
      ) : (
        <div className="mt-10 space-y-12">
          {results.modules.length > 0 && (
            <section>
              <h2 className="mb-4 text-lg font-semibold">
                {dict.search.moduleResults}{" "}
                <span className="text-sm font-normal text-slate-500 dark:text-slate-400">
                  · {results.modules.length}
                </span>
              </h2>
              <div className="space-y-3">
                {results.modules.map((hit, i) => (
                  <Link
                    key={`${hit.moduleKey}-${i}`}
                    href={hit.href}
                    className="block rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-900 hover:shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-100"
                  >
                    <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      {hit.moduleHeading} · {hit.sectionTitle}
                    </div>
                    <ul className="mt-2 space-y-1 text-sm text-slate-700 dark:text-slate-300">
                      {hit.matches.slice(0, 3).map((m, j) => (
                        <li key={j} className="leading-snug">
                          {highlight(m, results.query)}
                        </li>
                      ))}
                    </ul>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {results.news.length > 0 && (
            <section>
              <h2 className="mb-4 text-lg font-semibold">
                {dict.search.newsResults}{" "}
                <span className="text-sm font-normal text-slate-500 dark:text-slate-400">
                  · {results.news.length}
                  {results.totalNewsMatches > results.news.length
                    ? ` / ${results.totalNewsMatches}`
                    : ""}
                </span>
              </h2>
              <div className="grid gap-4 sm:grid-cols-2">
                {results.news.map((item) => (
                  <NewsCard
                    key={item.id}
                    item={item}
                    locale={typed}
                    categoryLabel={
                      dict.news.categories[
                        item.category === "export-control"
                          ? "exportControl"
                          : item.category === "trade-secrets"
                            ? "tradeSecrets"
                            : item.category === "employment"
                              ? "employment"
                              : "general"
                      ]
                    }
                    regionLabel={dict.news.regions[item.region]}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </main>
  );
}
