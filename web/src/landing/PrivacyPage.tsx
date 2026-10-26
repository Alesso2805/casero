import { Link } from "@tanstack/react-router";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import policy from "../../../docs/legal/privacy-short.md?raw";
import { copy } from "./copy";

export function PrivacyPage() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10 text-base">
      <Link to="/" className="text-brand underline">
        {copy.privacyBack}
      </Link>
      <article className="flex flex-col gap-4 [&_h1]:text-3xl [&_h1]:font-bold [&_h2]:mt-4 [&_h2]:text-2xl [&_h2]:font-bold [&_table]:w-full [&_td]:border [&_td]:border-stone-300 [&_td]:p-2 [&_th]:border [&_th]:border-stone-300 [&_th]:p-2 [&_th]:text-left [&_ul]:list-disc [&_ul]:pl-6">
        <Markdown remarkPlugins={[remarkGfm]}>{policy}</Markdown>
      </article>
    </div>
  );
}
