import { Link } from "@tanstack/react-router";

import { copy } from "./copy";
import { WaitlistForm } from "./WaitlistForm";

export function LandingPage() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-12 px-4 py-10">
      <header className="flex flex-col gap-4">
        <p className="text-lg font-bold text-brand">Casero</p>
        <h1 className="text-3xl font-bold leading-tight">{copy.hero.title}</h1>
        <p className="text-lg">{copy.hero.lead}</p>
        <p className="rounded-lg bg-amber-50 p-3 text-base text-amber-900">{copy.hero.notice}</p>
        <a
          href="#lista-de-espera"
          className="flex min-h-11 items-center justify-center rounded-lg bg-brand px-5 text-base font-semibold text-white hover:bg-brand-dark"
        >
          {copy.hero.action}
        </a>
      </header>

      <section aria-labelledby="como-funciona" className="flex flex-col gap-4">
        <h2 id="como-funciona" className="text-2xl font-bold">
          {copy.steps.title}
        </h2>
        <ol className="flex list-decimal flex-col gap-3 pl-6 text-base">
          {copy.steps.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="lo-que-no-hace" className="flex flex-col gap-3">
        <h2 id="lo-que-no-hace" className="text-2xl font-bold">
          {copy.limits.title}
        </h2>
        <p className="text-base">{copy.limits.body}</p>
      </section>

      <section aria-labelledby="precios" className="flex flex-col gap-4">
        <h2 id="precios" className="text-2xl font-bold">
          {copy.plans.title}
        </h2>
        <p className="text-base">{copy.plans.note}</p>
        <ul className="flex flex-col gap-4">
          {copy.plans.items.map((plan) => (
            <li key={plan.name} className="rounded-lg border border-stone-300 p-4">
              <p className="text-lg font-bold">{plan.name}</p>
              <p className="text-lg">{plan.price}</p>
              <p className="mt-2 text-base">{plan.detail}</p>
            </li>
          ))}
        </ul>
        <p className="text-base">{copy.plans.trial}</p>
      </section>

      <section
        id="lista-de-espera"
        aria-labelledby="lista-de-espera-titulo"
        className="flex flex-col gap-4"
      >
        <h2 id="lista-de-espera-titulo" className="text-2xl font-bold">
          {copy.waitlist.title}
        </h2>
        <WaitlistForm />
      </section>

      <footer className="flex flex-col gap-2 border-t border-stone-300 pt-6 text-base">
        <Link to="/privacidad" className="text-brand underline">
          {copy.footer.privacy}
        </Link>
        <p>{copy.footer.disclaimer}</p>
      </footer>
    </div>
  );
}
