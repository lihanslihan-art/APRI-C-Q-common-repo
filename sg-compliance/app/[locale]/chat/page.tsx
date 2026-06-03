import Link from "next/link";
import type { Locale } from "@/lib/i18n-config";
import { getDictionary } from "@/lib/dictionary";
import { Chat } from "@/components/Chat";

export const dynamic = "force-dynamic";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const typed = locale as Locale;
  const dict = await getDictionary(typed);

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <Link
        href={`/${typed}`}
        className="text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
      >
        ← {dict.common.backToHome}
      </Link>
      <h1 className="mt-4 text-2xl font-bold tracking-tight sm:text-3xl">
        {dict.chat.heading}
      </h1>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        {dict.chat.subheading}
      </p>
      <div className="mt-5">
        <Chat
          locale={typed}
          strings={{
            inputPlaceholder: dict.chat.inputPlaceholder,
            send: dict.chat.send,
            stop: dict.chat.stop,
            thinking: dict.chat.thinking,
            errorPrefix: dict.chat.errorPrefix,
            empty: dict.chat.empty,
            exampleHeading: dict.chat.exampleHeading,
            examples: dict.chat.examples,
            disclaimer: dict.chat.disclaimer,
            you: dict.chat.you,
            assistant: dict.chat.assistant,
          }}
        />
      </div>
    </div>
  );
}
