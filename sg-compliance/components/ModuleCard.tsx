import Link from "next/link";

export function ModuleCard({
  href,
  title,
  summary,
  status,
}: {
  href: string;
  title: string;
  summary: string;
  status: string;
}) {
  return (
    <Link
      href={href}
      className="group flex h-full flex-col rounded-xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-slate-900 hover:shadow-md dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-100"
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          {title}
        </h3>
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
          {status}
        </span>
      </div>
      <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
        {summary}
      </p>
      <span className="mt-4 text-sm font-medium text-slate-900 group-hover:underline dark:text-slate-100">
        →
      </span>
    </Link>
  );
}
