import { accountCopy as text } from "./copy";
import { textLink } from "./fields";

/** The legal export: also on the blocked home page, where nothing else works. */
export function DataDownload() {
  return (
    <section aria-labelledby="data-download-title" className="flex flex-col gap-2">
      <h2 id="data-download-title" className="text-2xl font-bold">
        {text.dataDownload.title}
      </h2>
      <p>{text.dataDownload.intro}</p>
      <a href="/api/app/exports/my-data.zip" download className={textLink}>
        {text.dataDownload.link}
      </a>
    </section>
  );
}
