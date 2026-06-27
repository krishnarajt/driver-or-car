# Driver or Car?

An interactive look at the oldest argument in motorsport: when a Formula 1 team
does well, is it the **driver** or the **car**?

Public F1 data can't directly measure raw car performance, but it contains one
near-perfect natural experiment — **teammates**. Two drivers in the same
constructor drive effectively identical machinery in the same races. If results
were purely about the car, teammates would always finish next to each other.
They rarely do, and the gap that opens up between them is the cleanest signal we
have for the driver. Strategy, reliability and racecraft do the rest.

## The headline

Across the 2014–2026 era, two cars from the **same team** finished in adjacent
positions only **~30% of the time** (n≈1,920). If the car decided everything,
that number would be 100%.

## What the site shows

- **The proof** — the distribution of teammate finishing-position gaps across the
  whole field. One tall bar would mean "it's the car"; it isn't one tall bar.
- **The teammate duel** — pick any season and team and compare its two drivers in
  identical machinery: qualifying & race head-to-head, points split, wins,
  podiums, DNFs, and a race-by-race divergence chart.
- **The reading** — a transparent, side-by-side _Car force_ vs _Driver force_
  heuristic for each season (explicitly not a causal verdict).
- **Strategy, reliability & racecraft** — places gained from the grid, constructor
  reliability (DNF rates), and pit-stop intensity: the third actor.
- **Hall of fame** — the most lopsided "same car, different planet" teammate
  seasons of all time.
- **Every season, side by side** — a small-multiples grid: one sparkline per
  season showing how teammate finishing-gaps were distributed, so you can see
  the "cars rarely finish together" pattern hold across all of F1 history.
- **Full season picture** — championship tables and the classic pace proxies
  (did the fastest car over one lap actually win the title?).

## Run it

Requires Node 18+ and Python 3.10+ with `pandas`.

```sh
# 1. install the front-end toolchain
npm install

# 2. (re)generate the data the dashboard reads
python -m pip install -r requirements.txt   # once
npm run data                                # runs both Python builders

# 3. start the dev server (hot reload)
npm run dev
```

Then open the URL it prints (default http://localhost:5173).

Other scripts:

- `npm run build` — production build into `dist/`.
- `npm run preview` — serve the production build locally.
- `npm run data` — rebuild `analysis/*.csv` and `site/public/data/season-dashboard.json`.

## Layout

- `site/` — the static front-end (`index.html`, `app.js`, `styles.css`). Served by
  Vite; `site/public/` (data + assets) is exposed at the web root.
- `scripts/build_site_dashboard.py` — builds the dashboard JSON: teammate
  head-to-heads, strategy/reliability, the per-season verdict, and the flagship
  duels.
- `scripts/build_yearly_summary.py` — builds the pace-proxy and points-share
  analysis CSVs in `analysis/`.
- `data/` — the local F1DB and TracingInsights source data. See `DATA_SOURCES.md`
  for source URLs, versions, licenses and SHA-256 hashes.

## Honesty note

The per-season "Car force / Driver force" reading is a transparent heuristic, not
a causal model. Car force is the top constructor's share of all constructor
points; driver force is how far apart teammates in identical cars finished. They
are shown side by side precisely because the real answer is almost always "both".
A stronger causal model would additionally control for reliability, race
distance completed, era-specific scoring, and mid-season car/driver changes.
