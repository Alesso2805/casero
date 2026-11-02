# ADR-0014: Cuaderno design tokens and self-hosted fonts

- Status: Accepted
- Date: 2026-11-01
- Story: CS-35

## Context

The owner chose the "Cuaderno" visual direction: grid paper, ledger rows and ink blue, instead of the first green brand. The web app uses Tailwind CSS. Production sends `style-src 'self'` and `font-src 'self'`, so inline `style` attributes and fonts from another origin are blocked. The app also needs a navigation that works one-handed on a phone and uses the width of a desktop screen.

## Decision

- **Tokens:** colours and font families live in the `@theme` block of `web/src/styles.css`. Screens use names such as `brand`, `muted`, `rule`, `late` and `ok`, never literal colours. `grid-paper` is a stylesheet utility, because the CSP rejects an inline background.
- **Fonts:** IBM Plex Sans and IBM Plex Mono come from the `@fontsource` packages (OFL-1.1), bundled by Vite and served by Casero itself. Only the `latin` subset and the weights in use are imported. Each file is larger than Vite's inline limit, so none becomes a `data:` URL, which `font-src 'self'` would block.
- **Money:** amounts use the mono family, so figures line up in columns.
- **Navigation:** `AppShell` wraps the routes under `/app`. It shows four tabs on a phone and a side menu from the `lg` breakpoint. It makes no request of its own and reads the legal status from the cache of the query that the home page already runs, so a blocked account sees only its gate.

## Consequences

- No visitor data reaches a font provider, and the fonts work under the existing CSP.
- The six font files add about 130 KB, loaded with `font-display: swap`, so text shows at once in a system font.
- A screen that needs a new colour adds a token instead of a literal value.
- The admin panel shares the tokens but not the fonts, so it uses the system font.
