import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useBusiness, type Business } from "../api/business";

export function withBusiness(text: string, business: Business | undefined): string {
  if (!business) {
    return text;
  }
  return text
    .replaceAll("[nombre completo según el RUC]", business.name)
    .replaceAll("[RUC]", business.ruc)
    .replaceAll("[domicilio]", business.address)
    .replaceAll("[correo de privacidad]", business.privacy_inbox);
}

export function LegalArticle({ source }: { source: string }) {
  const business = useBusiness();
  return (
    <article className="flex flex-col gap-4 [&_h1]:text-3xl [&_h1]:font-bold [&_h2]:mt-4 [&_h2]:text-2xl [&_h2]:font-bold [&_ol]:list-decimal [&_ol]:pl-6 [&_table]:w-full [&_td]:border [&_td]:border-stone-300 [&_td]:p-2 [&_th]:border [&_th]:border-stone-300 [&_th]:p-2 [&_th]:text-left [&_ul]:list-disc [&_ul]:pl-6 [&_a]:text-brand [&_a]:underline">
      <Markdown remarkPlugins={[remarkGfm]}>{withBusiness(source, business.data)}</Markdown>
    </article>
  );
}
