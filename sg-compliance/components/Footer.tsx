import type { Dictionary } from "@/lib/dictionary";

export function Footer({ dict }: { dict: Dictionary }) {
  return (
    <footer className="mt-auto border-t border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/40">
      <div className="mx-auto max-w-6xl px-4 py-6 text-xs text-slate-500 dark:text-slate-400">
        <p className="mb-1">{dict.footer.disclaimer}</p>
        <p>{dict.footer.builtWith}</p>
      </div>
    </footer>
  );
}
