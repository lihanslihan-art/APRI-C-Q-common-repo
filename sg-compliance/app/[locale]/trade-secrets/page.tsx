import { i18n, type Locale } from "@/lib/i18n-config";
import { getDictionary } from "@/lib/dictionary";
import { ModulePage } from "@/components/ModulePage";

export async function generateStaticParams() {
  return i18n.locales.map((locale) => ({ locale }));
}

export default async function TradeSecretsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const typed = locale as Locale;
  const dict = await getDictionary(typed);
  return (
    <ModulePage
      locale={typed}
      dict={dict}
      heading={dict.tradeSecrets.heading}
      lead={dict.tradeSecrets.lead}
      sections={dict.tradeSecrets.sections}
    />
  );
}
