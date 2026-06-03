import Link from "next/link";
import type { Locale } from "@/lib/i18n-config";
import type { Dictionary } from "@/lib/dictionary";

type Section = { title: string; items: string[] };

export function ModulePage({
  locale,
  dict,
  heading,
  lead,
  sections,
}: {
  locale: Locale;
  dict: Dictionary;
  heading: string;
  lead: string;
  sections: Record<string, Section>;
}) {
  return (
    <article className="mx-auto max-w-3xl px-4 py-10">
      <Link
        href={`/${locale}`}
        className="text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
      >
        ← {dict.common.backToHome}
      </Link>
      <h1 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl">
        {heading}
      </h1>
      <p className="mt-3 text-base leading-relaxed text-slate-600 dark:text-slate-400">
        {lead}
      </p>

      <div className="mt-10 space-y-10">
        {Object.entries(sections).map(([key, section]) => (
          <section key={key}>
            <h2 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              {section.title}
            </h2>
            <ul className="mt-3 space-y-2 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
              {section.items.map((item, i) => (
                <li
                  key={i}
                  className="relative pl-5 before:absolute before:left-0 before:top-2 before:h-1.5 before:w-1.5 before:rounded-full before:bg-slate-400 dark:before:bg-slate-500"
                >
                  {item}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </article>
  );
}
