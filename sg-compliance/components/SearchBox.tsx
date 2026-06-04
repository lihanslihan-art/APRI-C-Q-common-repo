export function SearchBox({
  locale,
  placeholder,
  defaultValue,
  size = "sm",
}: {
  locale: string;
  placeholder: string;
  defaultValue?: string;
  size?: "sm" | "lg";
}) {
  const inputClass =
    size === "lg"
      ? "w-full rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-slate-900 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-100"
      : "w-44 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 focus:border-slate-900 focus:outline-none lg:w-56 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:focus:border-slate-100";
  return (
    <form action={`/${locale}/search`} method="get" role="search">
      <input
        type="search"
        name="q"
        defaultValue={defaultValue ?? ""}
        placeholder={placeholder}
        className={inputClass}
        autoComplete="off"
      />
    </form>
  );
}
