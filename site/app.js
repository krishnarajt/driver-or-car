/* =============================================================
 * Driver or Car — front-end
 * A single data file (data/season-dashboard.json) drives everything.
 * No framework: just small render functions + hand-drawn SVG charts.
 * ============================================================= */

const state = {
  data: null,
  year: null,
  teamId: null,
};

const $ = (sel) => document.querySelector(sel);

/* ----------------------------- utils ----------------------------- */
const fmtInt = (n) => new Intl.NumberFormat("en-US").format(n ?? 0);

function fmtPts(n) {
  if (n == null) return "0";
  return Number.isInteger(n) ? fmtInt(n) : n.toFixed(1);
}

function pct(n, digits = 1) {
  return n == null ? "—" : `${Number(n).toFixed(digits)}%`;
}

function flagOf(driver) {
  return driver?.flag || "🏁";
}

function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

/** Grow every `.js-grow` bar from 0 to its target width once painted. */
function animateBars(root) {
  const bars = root.querySelectorAll("[data-w]");
  bars.forEach((b) => (b.style.width = "0%"));
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      bars.forEach((b) => (b.style.width = b.dataset.w));
    })
  );
}

const revealObserver =
  "IntersectionObserver" in window
    ? new IntersectionObserver(
        (entries, obs) => {
          entries.forEach((e) => {
            if (e.isIntersecting) {
              e.target.classList.add("in");
              obs.unobserve(e.target);
            }
          });
        },
        { threshold: 0.12 }
      )
    : null;

function observeReveals(root) {
  const pending = root.querySelectorAll(".reveal:not(.in)");
  if (!revealObserver) {
    // No IntersectionObserver — never leave content hidden.
    pending.forEach((n) => n.classList.add("in"));
    return;
  }
  pending.forEach((n) => revealObserver.observe(n));
}

/** Safety net: nothing stays invisible, even if the observer never fires. */
function revealAllSoon(delay = 1200) {
  setTimeout(() => {
    document.querySelectorAll(".reveal:not(.in)").forEach((n) => n.classList.add("in"));
  }, delay);
}

/** Reveal immediately — used for panels that re-render on interaction, so a
 *  season change never flashes a blank card waiting on the scroll observer. */
function revealNow(root) {
  root.querySelectorAll(".reveal").forEach((n) => n.classList.add("in"));
}

/* --------------------------- selectors --------------------------- */
function seasonsWithDuels() {
  return state.data.seasons
    .filter((s) => (s.teammates || []).length > 0)
    .sort((a, b) => b.year - a.year);
}

function currentSeason() {
  return state.data.seasons.find((s) => s.year === state.year);
}

function currentPair() {
  const season = currentSeason();
  if (!season) return null;
  return (
    season.teammates.find((t) => t.constructorId === state.teamId) ||
    season.teammates[0] ||
    null
  );
}

/* ============================== HERO ============================= */
function renderHero() {
  const { headline, meta, overview } = state.data;
  $("#hero-adjacent").textContent = headline.adjacencyRate ?? "—";
  $("#hero-sub").innerHTML = `Across <strong>${fmtInt(
    headline.sampleSize
  )}</strong> same-team finishes in the ${headline.era} era. The other
    <strong>${(100 - headline.adjacencyRate).toFixed(
      1
    )}%</strong> of the time, a gap opened up — driver, strategy and luck.`;

  $("#topbar-meta").innerHTML = [
    `${overview.driverChampionshipSeasons} completed seasons`,
    `${meta.seasonStart}–${meta.latestCompletedSeason}`,
    `+ ${meta.seasonEnd} so far`,
  ]
    .map((t) => `<span class="chip">${t}</span>`)
    .join("");
}

/* ===================== GAP DISTRIBUTION (proof) ================== */
function renderGapChart() {
  const h = state.data.headline;
  $("#proof-sub").innerHTML = `In the ${h.era} era, two cars from the
    <strong>same team</strong> finished in adjacent positions only
    <strong>${pct(h.adjacencyRate)}</strong> of the time. Almost a quarter of the
    time (<strong>${pct(h.gap5PlusRate)}</strong>) they were 5+ places apart.
    Identical machinery, utterly different afternoons.`;

  const max = Math.max(...h.gapBuckets.map((b) => b.pct), 1);
  const host = $("#gap-chart");
  host.innerHTML = h.gapBuckets
    .map(
      (b) => `
      <div class="gaprow">
        <div class="gaprow__label">${b.label}<small>${fmtInt(
        b.count
      )} finishes</small></div>
        <div class="gaprow__track">
          <div class="gaprow__fill" data-w="${(b.pct / max) * 100}%">${pct(
        b.pct
      )}</div>
        </div>
      </div>`
    )
    .join("");

  $("#proof-foot").innerHTML = `Each finish counts one race in which a team had
    exactly two classified cars. Sample: ${fmtInt(h.sampleSize)} finishes,
    mean gap ${h.meanGap} positions. <em>If results were purely about the car,
    that top bar would tower over the rest — every team locking out adjacent
    finishes. It doesn't: the gap is what the driver, strategy and luck add.</em>`;

  animateBars(host);
}

/* ============================== DUEL ============================ */
function h2hRow(label, aVal, bVal, { glow = true } = {}) {
  const total = (aVal || 0) + (bVal || 0);
  const aw = total ? (aVal / total) * 100 : 0;
  const bw = total ? (bVal / total) * 100 : 0;
  const aWin = glow && aVal > bVal ? "win" : "";
  const bWin = glow && bVal > aVal ? "win" : "";
  return `
    <div class="h2h">
      <div class="h2h__side h2h__side--a ${aWin}">
        <span class="h2h__val">${aVal ?? 0}</span>
        <span class="h2h__bar"><i data-w="${aw}%"></i></span>
      </div>
      <div class="h2h__label">${label}</div>
      <div class="h2h__side h2h__side--b ${bWin}">
        <span class="h2h__bar"><i data-w="${bw}%"></i></span>
        <span class="h2h__val">${bVal ?? 0}</span>
      </div>
    </div>`;
}

function divergenceSVG(pair) {
  const tl = (pair.timeline || []).filter((p) => p.fa != null || p.fb != null);
  const W = 760;
  const H = 280;
  const padL = 34;
  const padR = 16;
  const padT = 22;
  const padB = 26;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  if (tl.length < 2) {
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Not enough shared races to chart"><text x="${
      W / 2
    }" y="${H / 2}" fill="#65718a" font-size="14" text-anchor="middle"
      font-family="JetBrains Mono">Not enough shared races to chart.</text></svg>`;
  }

  const maxRaw = Math.max(
    ...tl.flatMap((p) => [p.fa, p.fb].filter((v) => v != null))
  );
  const maxPos = Math.max(5, Math.ceil(maxRaw / 5) * 5);
  const n = tl.length;
  const x = (i) => padL + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (pos) => padT + ((pos - 1) / (maxPos - 1)) * plotH;

  // y gridlines
  const ticks = [];
  for (let p = 1; p <= maxPos; p += p === 1 ? 4 : 5) ticks.push(p);
  if (ticks[ticks.length - 1] !== maxPos) ticks.push(maxPos);
  const grid = ticks
    .map(
      (p) => `
      <line x1="${padL}" x2="${W - padR}" y1="${y(p)}" y2="${y(
        p
      )}" stroke="#1b2230" stroke-width="1"/>
      <text x="${padL - 8}" y="${y(p) + 4}" fill="#65718a" font-size="10"
        text-anchor="end" font-family="JetBrains Mono">P${p}</text>`
    )
    .join("");

  // x labels (round numbers, sparse)
  const step = Math.max(1, Math.round(n / 9));
  const xlabels = tl
    .map((p, i) =>
      i % step === 0 || i === n - 1
        ? `<text x="${x(i)}" y="${H - 6}" fill="#65718a" font-size="9.5"
            text-anchor="middle" font-family="JetBrains Mono">R${p.r}</text>`
        : ""
    )
    .join("");

  // gap connectors where both finished
  const gaps = tl
    .map((p, i) =>
      p.fa != null && p.fb != null
        ? `<line x1="${x(i)}" x2="${x(i)}" y1="${y(p.fa)}" y2="${y(
            p.fb
          )}" stroke="#2c3550" stroke-width="2"/>`
        : ""
    )
    .join("");

  // build line segments (break on null), per driver
  function segments(key) {
    const segs = [];
    let cur = [];
    tl.forEach((p, i) => {
      if (p[key] != null) cur.push([x(i), y(p[key])]);
      else if (cur.length) {
        segs.push(cur);
        cur = [];
      }
    });
    if (cur.length) segs.push(cur);
    return segs;
  }

  function lineFor(key, color) {
    const segs = segments(key);
    const paths = segs
      .map(
        (s) =>
          `<polyline points="${s
            .map((pt) => pt.join(","))
            .join(" ")}" fill="none" stroke="${color}" stroke-width="2.6"
            stroke-linejoin="round" stroke-linecap="round"/>`
      )
      .join("");
    const dots = segs
      .flatMap((s) => s)
      .map(
        (pt) =>
          `<circle cx="${pt[0]}" cy="${pt[1]}" r="3.4" fill="${color}"
            stroke="#0a0c10" stroke-width="1.2"/>`
      )
      .join("");
    return paths + dots;
  }

  // DNF markers (driver retired while we have a slot)
  const dnf = tl
    .map((p, i) => {
      let m = "";
      if (p.fa == null)
        m += `<text x="${x(i)}" y="${H - padB + 2}" fill="#19e0c8" font-size="11"
          text-anchor="middle">✕</text>`;
      if (p.fb == null)
        m += `<text x="${x(i)}" y="${H - padB + 12}" fill="#8b7bff" font-size="11"
          text-anchor="middle">✕</text>`;
      return m;
    })
    .join("");

  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Race-by-race finishing positions">
    ${grid}${gaps}
    ${lineFor("fa", "#19e0c8")}
    ${lineFor("fb", "#8b7bff")}
    ${dnf}${xlabels}
  </svg>`;
}

function renderDuel() {
  const pair = currentPair();
  const host = $("#duel-card");
  if (!pair) {
    host.innerHTML = `<div class="duel__context">No teammate pairing recorded for this team and season.</div>`;
    return;
  }
  const a = pair.a;
  const b = pair.b;
  const q = pair.qualiH2H;
  const r = pair.raceH2H;
  const scored = pair.pointsShare.a != null; // both null => team scored nothing
  const sa = pair.pointsShare.a ?? 50;
  const sb = pair.pointsShare.b ?? 50;

  const lead = !scored
    ? `neither driver scored for the team that year`
    : (a.points || 0) >= (b.points || 0)
    ? `${a.abbr} took <strong>${pct(sa, 0)}</strong> of their combined points`
    : `${b.abbr} took <strong>${pct(sb, 0)}</strong> of their combined points`;

  const shareHtml = scored
    ? `<div class="share__track">
        <div class="share__seg share__seg--a" data-w="${sa}%">${a.abbr} ${pct(sa, 0)}</div>
        <div class="share__seg share__seg--b" data-w="${sb}%">${pct(sb, 0)} ${b.abbr}</div>
      </div>
      <div class="share__cap">how the two split their combined points — one car, two drivers</div>`
    : `<div class="share__track">
        <div class="share__seg share__seg--none" data-w="100%">No points scored by either driver</div>
      </div>
      <div class="share__cap">${pair.constructor} went pointless this season</div>`;

  host.innerHTML = `
    <div class="duel__top">
      <div class="duel__driver duel__driver--a">
        <span class="duel__flag">${flagOf(a)}</span>
        <span class="duel__abbr">${a.abbr}</span>
        <span class="duel__name">${a.name ?? ""}</span>
        <span class="duel__role">${fmtPts(a.points)} pts · ${a.wins} win${
    a.wins === 1 ? "" : "s"
  }</span>
      </div>
      <div class="duel__vs">
        <span>VS</span>
        <small>identical<br/>machinery</small>
      </div>
      <div class="duel__driver duel__driver--b">
        <span class="duel__flag">${flagOf(b)}</span>
        <span class="duel__abbr">${b.abbr}</span>
        <span class="duel__name">${b.name ?? ""}</span>
        <span class="duel__role">${fmtPts(b.points)} pts · ${b.wins} win${
    b.wins === 1 ? "" : "s"
  }</span>
      </div>
    </div>

    <div class="duel__context">
      <strong>${pair.constructor}</strong>${
    pair.engine ? ` · ${pair.engine}` : ""
  } — same car, ${pair.sharedRaces} shared races.
      ${a.abbr} out-qualified ${b.abbr} <strong>${q.a}–${q.b}</strong> and
      finished ahead <strong>${r.a}–${r.b}</strong> on Sundays. ${lead}.
    </div>

    <div class="duel__bars">
      ${h2hRow("Points", Math.round(a.points || 0), Math.round(b.points || 0))}
      ${h2hRow("Out-qualified", q.a, q.b)}
      ${h2hRow("Finished ahead", r.a, r.b)}
      ${h2hRow("Wins", a.wins, b.wins)}
      ${h2hRow("Podiums", a.podiums, b.podiums)}
      ${h2hRow("DNFs", a.dnfs, b.dnfs, { glow: false })}
    </div>

    <div class="share">${shareHtml}</div>

    <div class="diverge">
      <div class="diverge__head">
        <span class="diverge__title">Race-by-race finishing position</span>
        <span class="diverge__legend">
          <span><i class="dot dot--a"></i>${a.abbr}</span>
          <span><i class="dot dot--b"></i>${b.abbr}</span>
          <span>✕ = retired</span>
        </span>
      </div>
      ${divergenceSVG(pair)}
    </div>`;

  animateBars(host);
}

/* ============================ VERDICT =========================== */
function tiltOf(v) {
  if (v.driverForce == null || v.carForce == null) return "mix";
  if (v.driverForce >= 60 && v.carForce < 32) return "driver";
  if (v.carForce >= 32 && v.driverForce < 60) return "car";
  if (v.driverForce >= v.carForce) return "driver";
  return "car";
}

function renderVerdict() {
  const season = currentSeason();
  const v = season?.verdict || {};
  $("#verdict-year").textContent = season?.year ?? "";
  $("#verdict-label").textContent = v.label || "Not enough data";

  const tag = $("#season-tag");
  if (v.label) {
    const note = v.partial ? " · so far" : v.lowSample ? " · small sample" : "";
    tag.innerHTML = `<span>this season reads as</span>
      <span class="verdict-pill" data-tilt="${tiltOf(v)}">${v.label}${note}</span>`;
  } else {
    tag.innerHTML = "";
  }

  const host = $("#verdict-card");
  if (v.carForce == null && v.driverForce == null) {
    host.innerHTML = `<p class="band__sub">This season predates the data needed for the verdict heuristic.</p>`;
    return;
  }

  // Caveats shown inline so a confident-looking score is never read as settled.
  const caveats = [];
  if (v.partial)
    caveats.push(
      `In progress — ${season.racesWithResults} of ${season.racesScheduled} races run, so this is a read on the season <strong>so far</strong>.`
    );
  if (v.lowSample)
    caveats.push(
      `Only <strong>${v.sampleSize}</strong> teammate finishes to go on — treat the driver-force number as indicative, not settled.`
    );
  const caveatHtml = caveats.length
    ? `<div class="verdict__caveat reveal">⚠︎ ${caveats.join(" ")}</div>`
    : "";

  // Pre-1958 had no constructors' championship, so there is no car-force basis.
  const carCard =
    v.carForce == null
      ? `<article class="force force--car force--na reveal">
          <div class="force__label"><span>Car force</span><span>n/a</span></div>
          <div class="force__num">n/a</div>
          <div class="force__meter"><i data-w="0%"></i></div>
          <p class="force__desc">No constructors' championship existed before 1958,
          so there is no "share of constructor points" to measure here.</p>
        </article>`
      : `<article class="force force--car reveal">
          <div class="force__label"><span>Car force</span><span>${v.carForce} / 100</span></div>
          <div class="force__num">${v.carForce}</div>
          <div class="force__meter"><i data-w="${v.carForce}%"></i></div>
          <p class="force__desc">The leading team scored <strong>${pct(
            v.carForce
          )}</strong> of all constructor points — how far one machine ran clear of
          the field.</p>
        </article>`;

  host.innerHTML = `
    ${carCard}

    <article class="force force--driver reveal">
      <div class="force__label"><span>Driver force</span><span>${
        v.driverForce ?? "—"
      } / 100</span></div>
      <div class="force__num">${v.driverForce ?? "—"}</div>
      <div class="force__meter"><i data-w="${v.driverForce ?? 0}%"></i></div>
      <p class="force__desc">Teammates in identical cars finished adjacent only
      <strong>${pct(
        v.teammateAdjacencyRate
      )}</strong> of the time${
    v.sampleSize ? ` (from ${fmtInt(v.sampleSize)} teammate finishes)` : ""
  } — the rest is the gap the driver, strategy and luck opened up.</p>
    </article>

    ${caveatHtml}

    <div class="verdict__spotlight reveal">
      <span class="quote">“</span>
      <p>${v.spotlight || ""}
        ${
          v.championTeamShare != null
            ? `<span class="champ">The champion scored <strong>${pct(
                v.championTeamShare
              )}</strong> of his own team's points — in the same car as his teammate.</span>`
            : ""
        }
      </p>
    </div>`;

  revealNow(host);
  animateBars(host);
}

/* =========================== STRATEGY =========================== */
function renderStrategy() {
  const season = currentSeason();
  const s = season?.strategy || {};
  $("#strategy-year").textContent = season ? `(${season.year})` : "";

  const movers = s.topMovers || [];
  const maxGain = Math.max(...movers.map((m) => m.gained), 1);
  const moversHtml = movers.length
    ? movers
        .map(
          (m) => `
        <div class="strat__row">
          <div class="strat__who">${m.flag || "🏁"} <b>${m.driver}</b></div>
          <div class="strat__metric pos">+${m.gained}</div>
          <div class="strat__bar"><i class="good" data-w="${
            (m.gained / maxGain) * 100
          }%"></i></div>
        </div>`
        )
        .join("")
    : `<p class="strat__hint">Grid-to-finish moves aren't recorded for this era.</p>`;

  const unreliable = s.leastReliable || [];
  const maxDnf = Math.max(...unreliable.map((c) => c.dnfRate), 1);
  const relHtml = unreliable.length
    ? unreliable
        .map(
          (c) => `
        <div class="strat__row">
          <div class="strat__who"><b>${c.constructor}</b>${
            c.incidentDnfs
              ? `<small class="strat__aside">+${c.incidentDnfs} crash${
                  c.incidentDnfs === 1 ? "" : "es"
                }</small>`
              : ""
          }</div>
          <div class="strat__metric bad">${pct(c.dnfRate)}</div>
          <div class="strat__bar"><i class="bad" data-w="${
            (c.dnfRate / maxDnf) * 100
          }%"></i></div>
        </div>`
        )
        .join("")
    : `<p class="strat__hint">No reliability breakdown for this season.</p>`;

  const host = $("#strat-grid");
  host.innerHTML = `
    <article class="strat reveal">
      <h3>Dragged it forward</h3>
      <p class="strat__hint">Net places gained from the grid — racecraft, strategy, and a little of others' misfortune.</p>
      ${moversHtml}
    </article>
    <article class="strat reveal">
      <h3>The car let them down</h3>
      <p class="strat__hint">Mechanical retirements as a share of entries — engine, gearbox, hydraulics. Crashes are kept separate; those are on the driver.</p>
      ${relHtml}
    </article>
    <article class="strat reveal">
      <h3>Pit-wall calls</h3>
      <p class="strat__hint">Average pit stops per car, per race — every one a decision.</p>
      <div class="strat__big">${s.avgPitStops != null ? s.avgPitStops : "—"}</div>
      <p class="strat__bigsub">${
        s.avgPitStops != null
          ? "stops per car each Sunday. Undercut, overcut, or hold — the same car can finish a dozen places apart on strategy alone."
          : "Pit-stop counts aren't recorded for this season."
      }</p>
    </article>`;

  revealNow(host);
  animateBars(host);
}

/* ========================= FLAGSHIPS ============================ */
function renderFlagships() {
  const host = $("#flagship-grid");
  host.innerHTML = state.data.flagshipDuels
    .map((d) => {
      // order winner (more points) on the left
      const [w, l] = (d.a.points || 0) >= (d.b.points || 0) ? [d.a, d.b] : [d.b, d.a];
      const total = (w.points || 0) + (l.points || 0) || 1;
      const lShare = (l.points / total) * 100;
      return `
      <article class="flag-card reveal">
        <div class="flag-card__top">
          <span class="flag-card__year">${d.year}</span>
          <span class="flag-card__team">${d.constructor}<small>${
        d.engine || ""
      }</small></span>
        </div>
        <div class="flag-card__duel">
          <div class="flag-card__d win">
            <div class="flag-card__nm">${flagOf(w)} ${w.abbr}</div>
            <div class="pts">${fmtPts(w.points)} pts</div>
          </div>
          <span class="flag-card__split">${d.imbalance}%</span>
          <div class="flag-card__d flag-card__d--b">
            <div class="flag-card__nm">${l.abbr} ${flagOf(l)}</div>
            <div class="pts">${fmtPts(l.points)} pts</div>
          </div>
        </div>
        <div class="flag-card__bar"><i data-w="${100 - lShare}%" style="width:${
        100 - lShare
      }%"></i></div>
        <div class="flag-card__meta">
          <span>Quali <b>${d.qualiH2H.a + d.qualiH2H.b ? `${Math.max(
            d.qualiH2H.a,
            d.qualiH2H.b
          )}–${Math.min(d.qualiH2H.a, d.qualiH2H.b)}` : "—"}</b></span>
          <span>Beat H2H <b>${Math.max(d.raceH2H.a, d.raceH2H.b)}–${Math.min(
        d.raceH2H.a,
        d.raceH2H.b
      )}</b></span>
          <span><b>${d.raceH2H.races}</b> races wheel-to-wheel</span>
        </div>
      </article>`;
    })
    .join("");
  revealNow(host);
}

/* ============ SMALL MULTIPLES (gap shape, every season) ========= */
function sparkline(buckets, ymax) {
  const W = 168;
  const H = 62;
  const padX = 8;
  const padTop = 8;
  const padBot = 10;
  const plotW = W - padX * 2;
  const plotH = H - padTop - padBot;
  const n = buckets.length;
  const x = (i) => padX + (i / (n - 1)) * plotW;
  const y = (v) => padTop + (1 - Math.min(v, ymax) / ymax) * plotH;

  const pts = buckets.map((b, i) => [x(i), y(b.pct)]);
  const line = pts.map((p) => p.join(",")).join(" ");
  const area = `${padX},${padTop + plotH} ${line} ${padX + plotW},${padTop + plotH}`;
  const dots = pts
    .map(
      (p, i) =>
        `<circle cx="${p[0]}" cy="${p[1]}" r="${i === 0 ? 3.2 : 2.2}" fill="${
          i === 0 ? "#ff8a00" : "#19e0c8"
        }"/>`
    )
    .join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Teammate finishing-gap distribution" preserveAspectRatio="none">
    <line x1="${padX}" x2="${W - padX}" y1="${padTop + plotH}" y2="${
    padTop + plotH
  }" stroke="#232b3d" stroke-width="1"/>
    <polygon points="${area}" fill="rgba(25,224,200,0.12)"/>
    <polyline points="${line}" fill="none" stroke="#19e0c8" stroke-width="2"
      stroke-linejoin="round" stroke-linecap="round"/>
    ${dots}
  </svg>`;
}

function renderSeasonGrid() {
  const seasons = state.data.seasons
    .filter((s) => (s.teammateSummary?.sampleSize || 0) > 0 && s.teammateSummary.gapBuckets.length)
    .sort((a, b) => b.year - a.year);

  // Fixed scale across every chart so the shapes are comparable. Cap so a tiny
  // early-season spike can't flatten everyone else.
  const ymax = Math.min(
    60,
    Math.ceil(
      Math.max(
        ...seasons
          .filter((s) => s.teammateSummary.sampleSize >= 20)
          .flatMap((s) => s.teammateSummary.gapBuckets.map((b) => b.pct)),
        40
      ) / 10
    ) * 10
  );

  $("#sm-legend").innerHTML = `
    <span><i class="dot" style="background:#ff8a00"></i>Adjacent (cars finish together)</span>
    <span class="sm-legend__axis">left → right: adjacent · 2 · 3–4 · 5–9 · 10+ apart</span>
    <span class="sm-legend__scale">y-axis 0–${ymax}%</span>`;

  $("#smallmults").innerHTML = seasons
    .map((s) => {
      const ts = s.teammateSummary;
      const low = ts.sampleSize < 20;
      return `
      <article class="sm reveal ${low ? "sm--low" : ""}" title="${s.year}: teammates finished adjacent ${pct(
        ts.adjacencyRate
      )} of the time (n=${ts.sampleSize})">
        <div class="sm__head">
          <span class="sm__year">${s.year}</span>
          <span class="sm__adj">${pct(ts.adjacencyRate, 0)}</span>
        </div>
        ${sparkline(ts.gapBuckets, ymax)}
        <div class="sm__foot">${low ? "n=" + ts.sampleSize : fmtInt(ts.sampleSize) + " finishes"}</div>
      </article>`;
    })
    .join("");
  observeReveals($("#smallmults"));
}

/* ======================== PACE + TABLES ========================= */
function paceCard(label, value, sub, match) {
  const cls = match === true ? "match" : match === false ? "split" : "neutral";
  const txt =
    match === true
      ? "Matched the title"
      : match === false
      ? "Title went elsewhere"
      : "Not decided";
  return `
    <div class="pace-card">
      <span>${label}</span>
      <strong>${value ?? "—"}</strong>
      <small>${sub}</small>
      <div class="tag ${cls}">${txt}</div>
    </div>`;
}

function renderDetail() {
  const season = currentSeason();
  if (!season) return;
  $("#detail-year").textContent = season.year;

  const pace = season.pace || {};
  const q = pace.qualifying || {};
  const fl = pace.fastestLap || {};
  const rw = pace.raceWins || {};
  $("#pace-grid").innerHTML = [
    paceCard(
      "Fastest over one lap",
      q.constructor,
      `${q.fastestRaces ?? 0}/${q.racesAvailable ?? 0} quickest qualifying weekends`,
      q.matchesConstructorChampion
    ),
    paceCard(
      "Fastest single lap",
      fl.constructor,
      `${fl.fastestRaces ?? 0}/${fl.racesAvailable ?? 0} quickest race laps`,
      fl.matchesConstructorChampion
    ),
    paceCard(
      "Most race wins",
      rw.constructor,
      `${rw.wins ?? 0}/${rw.racesAvailable ?? 0} race wins`,
      rw.matchesConstructorChampion
    ),
  ].join("");

  const driverRows = (season.driverStandings || [])
    .slice(0, 10)
    .map(
      (d) => `
      <tr class="${d.championshipWon ? "champ" : ""}">
        <td>${d.rank ?? d.positionText ?? ""}</td>
        <td>${d.name}</td>
        <td>${d.pointsLabel}</td>
      </tr>`
    )
    .join("");

  const conRows = (season.constructorStandings || [])
    .slice(0, 10)
    .map(
      (c) => `
      <tr class="${c.championshipWon ? "champ" : ""}">
        <td>${c.rank ?? c.positionText ?? ""}</td>
        <td>${c.name}</td>
        <td>${c.pointsLabel}</td>
      </tr>`
    )
    .join("");

  $("#tables").innerHTML = `
    <div class="tablecard">
      <h3>Drivers' championship</h3>
      <table><thead><tr><th>#</th><th>Driver</th><th>Pts</th></tr></thead>
      <tbody>${driverRows || '<tr><td colspan="3">No data</td></tr>'}</tbody></table>
    </div>
    <div class="tablecard">
      <h3>Constructors' championship</h3>
      <table><thead><tr><th>#</th><th>Constructor</th><th>Pts</th></tr></thead>
      <tbody>${conRows || '<tr><td colspan="3">Not awarded this season</td></tr>'}</tbody></table>
    </div>`;
}

/* ============================ FOOTER ============================ */
function renderFooter() {
  const { overview, meta, headline } = state.data;
  $("#coverage").innerHTML = [
    ["Races in the data", fmtInt(overview.races)],
    ["Race-result rows", fmtInt(overview.raceResultRows)],
    ["Qualifying rows", fmtInt(overview.qualifyingRows)],
    ["Lap-time rows", fmtInt(overview.lapTimeRows)],
  ]
    .map(([k, val]) => `<div class="cov"><span>${k}</span><strong>${val}</strong></div>`)
    .join("");
  $("#source-note").textContent = `${meta.source}. Headline sample ${fmtInt(
    headline.sampleSize
  )} same-team finishes (${headline.era}). Built locally; figures regenerate from CSV via the Python pipeline.`;
}

/* ====================== season-level refresh ==================== */
function refreshSeason() {
  renderVerdict();
  renderStrategy();
  renderDetail();
}

function populateTeamSelect() {
  const season = currentSeason();
  const sel = $("#team-select");
  sel.innerHTML = (season.teammates || [])
    .map(
      (t) =>
        `<option value="${t.constructorId}">${t.constructor} · ${fmtPts(
          t.teamPoints
        )} pts</option>`
    )
    .join("");
  // default: keep current team if present, else the season's top scorer
  if (!season.teammates.some((t) => t.constructorId === state.teamId)) {
    state.teamId = season.teammates[0]?.constructorId ?? null;
  }
  sel.value = state.teamId ?? "";
}

/* ============================== boot ============================ */
function wireControls() {
  const seasonSel = $("#season-select");
  seasonSel.innerHTML = seasonsWithDuels()
    .map((s) => `<option value="${s.year}">${s.year}</option>`)
    .join("");
  seasonSel.value = String(state.year);

  seasonSel.addEventListener("change", (e) => {
    state.year = Number(e.target.value);
    state.teamId = null; // reset to the season's top team
    populateTeamSelect();
    renderDuel();
    refreshSeason();
  });

  $("#team-select").addEventListener("change", (e) => {
    state.teamId = e.target.value;
    renderDuel();
  });
}

async function boot() {
  try {
    const res = await fetch("data/season-dashboard.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.data = await res.json();

    const duelSeasons = seasonsWithDuels();
    const preferred = state.data.meta.latestCompletedSeason;
    state.year = duelSeasons.some((s) => s.year === preferred)
      ? preferred
      : duelSeasons[0].year;

    renderHero();
    renderGapChart();
    renderFlagships();
    renderSeasonGrid();
    renderFooter();

    wireControls();
    populateTeamSelect();
    renderDuel();
    refreshSeason();

    observeReveals(document);
    revealAllSoon();
  } catch (err) {
    const box = $("#error");
    box.hidden = false;
    box.textContent = `Could not load dashboard data: ${err.message}. Run "npm run data" to (re)generate it, then "npm run dev".`;
  }
}

boot();
