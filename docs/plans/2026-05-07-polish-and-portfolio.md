# Polish + portfolio-readiness plan

Two tracks combined. Track 1 is "what's still broken / half-built that a real
visitor would notice." Track 2 is "what would have to be true for me to link
this from my résumé." Some items overlap.

Both based on a fresh browse of `homefinder.patbuilds.dev` on May 7, 2026.

---

## Bugs surfaced by the browse

**B1.** *Already fixed in this session.* Django template comment leaked as
plain text into the dashboard sidebar — `{# … #}` is single-line only;
the multi-line variant is `{% comment %}…{% endcomment %}`. Both
occurrences in `templates/WebScraper/dashboard.html` corrected.

---

## Track 1 — UX polish

Each item is sized to roughly fit a single focused commit. P1 = noticed
on first impression; P2 = noticed on second look; P3 = nice-to-have.

### P1 — Brand/content mismatch

The home page sells "Find Your Perfect Florida Home." The default
dashboard sort surfaces a $347M hospital, a $245M federal facility, and
a $186M church on the first page. That's a commercial database that
markets itself as a home-buyer site.

Pick one:
- **(a)** Default the dashboard filter to residential property types
  (Single Family / Condo / Townhouse / Multi-Family / Mobile Home) so
  the first-page experience matches the marketing.
- **(b)** Rebrand: hero copy → "Search Pinellas County property data —
  homes, commercial, land." Drops the misleading expectation.

I'd do (a) for the buyer-app pitch, (b) only if the user genuinely wants
the universal "search-everything" tool.

### P1 — "How It Works" and "Everything You Need" are empty

Two big sections on the home page have headings but no body. Either
fill with real content (3 cards each) or remove. Empty sections look
like the site is mid-build.

### P2 — Property type filter labels don't match the data

The form offers "Single Family / Condo / Townhouse / Multi-Family /
Vacant Land / Mobile Home / Commercial." PCPAO uses descriptions like
"Single Family Home", "Condominium", "Duplex-Triplex-Fourplex",
"Vacant Residential - lot & acreage less than 5 acres", "Manufactured
Home (Co-Op or Share Owned)". The current `__icontains` matching mostly
works but "Multi-Family" misses "Duplex-Triplex-Fourplex" entirely (a
Pinellas-favorite property type for investors).

Either:
- Map each form label to a list of substring matches (e.g. Multi-Family
  → ["Duplex-Triplex-Fourplex", "Multi-Family", "ALF"]), or
- Show the actual DOR descriptions as filter chips (more accurate but
  visually noisy — there are ~15 common ones).

### P2 — Property detail page lacks market context

When a user lands on a $400k duplex in St. Pete, they want to know:
- What's the median for duplexes in this ZIP / city?
- $/sqft vs the neighborhood average?
- Tax burden vs comparable types?

Right now the detail page shows the single property's numbers and 4
similar-by-price properties. Add a 3-stat panel near the header:
*Neighborhood median*, *$/sqft vs city average*, *Tax % of value vs city
average*. Pulls from the same aggregations the export already computes.

### P2 — Empty state is good; "no city match" empty state can be
**better.** The "No properties found" state on `?city=NotARealCity12345`
correctly shows the empty illustration + Clear/New Search buttons. But
the H1 still says *"Properties in NotARealCity12345"* — confusing. Add
a check: if the queried city isn't in `PINELLAS_CITIES`, swap the H1 to
*"Unrecognized city — check spelling"*.

### P3 — Skip-to-content link missing

`base.html` should include `<a href="#main" class="sr-only focus:not-sr-only">Skip to main content</a>` as the first focusable element. Standard a11y. 5 minutes.

### P3 — Spinner JS is now dead

The `data-loading-form` + `LoadingButton` wiring made sense when search
took 30s. Now it's an instant 302 — the spinner shows for ~1 frame.
Either keep it (harmless) or remove the wiring (cleaner). I'd keep it
since the export downloads still benefit.

### P3 — Hero image attribution

The home page hero has a high-res Florida house photo. If sourced from
Unsplash/Pexels, attribution may be required even for free use. Verify
license + add credit if needed.

---

## Track 2 — Portfolio readiness

### R1 — README rewrite

Current `README.md` is the project-as-built notes from earlier sessions.
For a portfolio reader hitting the GitHub repo first, it should have:
- One-paragraph "what this is + why" at the top
- Live link badge (`https://homefinder.patbuilds.dev`)
- Two screenshots (search form + dashboard) inline
- "Architecture" section with a diagram or 3-bullet stack summary
- "Interesting bits" — link to docs/SESSION_NOTES.md (architecture pivot)
  and the search-architecture-pivot plan
- Local dev quickstart (clone → venv → `manage.py migrate` → `runserver`)
- Honest limitations section ("PCPAO doesn't expose bedrooms; Street
  View needs a Google API key with billing")

### R2 — Public case-study page

Repurpose `docs/SESSION_NOTES.md` content into an `/about` route on the
deployed site. The story is the portfolio piece — went from a Celery +
Redis + scraper architecture that broke, diagnosed it, pivoted to a 2-
service indexed-DB design, ended up with sub-second searches and free
hosting. Recruiters skim READMEs but read narrative case studies.

### R3 — Repo cleanup

`git status` currently lists untracked files that shouldn't be in the
repo: `.coverage`, `.playwright-mcp/`, `cookies.txt`, `progress-check`,
`screenshots/`, `cookies.txt`. Add to `.gitignore`. Delete the
checked-in `home_finder/.gitignore` if it's a leftover.

### R4 — Existing pytest suite is broken

`apps/WebScraper/tests/test_tasks.py`, `test_performance.py`, etc. still
import `generate_sorted_properties`, `analyze_data`,
`send_results_via_email`, `quick_sort` — all removed in the Celery
pivot. Either delete those tests or rewrite them for the current
architecture. Right now `make test` fails immediately. CI also runs
this and is presumably red.

### R5 — Lighthouse / performance pass

Hobby Vercel has a CDN. The dashboard with 12 cards + 12 Street View
images probably scores OK but worth running Lighthouse and recording the
score. Likely wins:
- Defer or async the Street View images (already `loading="lazy"` —
  good)
- Inline critical CSS for first paint
- Add `<link rel="preconnect">` to `maps.googleapis.com`

### R6 — Accessibility pass

Beyond the skip link (P3 above):
- Confirm color contrast on the teal/charcoal palette meets WCAG AA
- Form fields have `<label for="…">` (look right from search.html)
- Property card click target is `<article onclick=…>` — make the card
  a `<a>` instead so keyboard nav works (right now you tab to the link
  inside but the whole card is clickable only via mouse)
- ARIA labels on icon-only buttons (filter sheet toggle, view toggle)

### R7 — Error monitoring

Right now production errors show up only via `vercel logs` if you
remember to look. Add Sentry (free tier covers a portfolio app
indefinitely) so 5xxs page you. Setup is a few lines in `settings.py`
and a `SENTRY_DSN` env var.

### R8 — Open Graph + favicon

For when the URL gets pasted into Slack/LinkedIn/Twitter:
- `<meta property="og:title">`, `og:description`, `og:image` (use a
  screenshot of the dashboard)
- `<meta name="twitter:card" content="summary_large_image">`
- Verify favicon is set (looks like the green house icon already is)

### R9 — `LICENSE` file

Add MIT or Apache 2.0 if missing. Recruiters notice.

### R10 — One-page "how the data flows" diagram

For the README and the about page. Boxes for: PCPAO bulk download → COPY
to Neon → Django queries → Vercel serverless → user. Five boxes, two
arrows. Mermaid renders inline on GitHub.

---

## Suggested execution order

| Order | Item | Why |
|---|---|---|
| 1 | B1 — comment leak (already done in session) | Visible bug |
| 2 | P1 — empty home-page sections | Visible "site is unfinished" tell |
| 3 | P1 — branding/default-filter | Surfaces residential by default |
| 4 | R3 — repo cleanup + R4 — fix broken tests | CI red is a bad first impression |
| 5 | R1 — README rewrite | Recruiters land here first |
| 6 | R8 — Open Graph meta | One-time, big payoff for sharing |
| 7 | P2 — property type label mapping | Concrete data quality fix |
| 8 | P2 — detail page market context | Highest "feature" impact for buyers |
| 9 | R2 — public case-study page | Tells the engineering story |
| 10 | P3 + R5 + R6 + R7 + R9 + R10 | Sweep of remaining polish |

Estimate to finish 1–8: **half a day to a day** of focused work. Items
9–10 are larger and could wait.

---

## What I'm not planning

- Bringing back bedrooms/bathrooms (no public data source).
- Per-property refresh button (Phase 3 of the prior plan, deferred — the
  monthly bulk refresh already covers freshness).
- New providers / paid APIs (would break the $0 / Vercel constraint).
