// Pure calculation functions (no DOM). Log layout: [date, opp, home, min, pts, reb, ast, fg3, stl, blk, tov, gameId]
const PROPS = {
  PTS: {label: "Points", f: l => l[4], normal: true}, REB: {label: "Rebounds", f: l => l[5]}, AST: {label: "Assists", f: l => l[6]},
  FG3: {label: "3-pointers made", f: l => l[7]}, STL: {label: "Steals", f: l => l[8]}, BLK: {label: "Blocks", f: l => l[9]},
  TOV: {label: "Turnovers", f: l => l[10]}, PR: {label: "Points + Rebounds", f: l => l[4] + l[5], normal: true},
  PA: {label: "Points + Assists", f: l => l[4] + l[6], normal: true}, RA: {label: "Rebounds + Assists", f: l => l[5] + l[6]},
  PRA: {label: "Pts + Reb + Ast", f: l => l[4] + l[5] + l[6], normal: true},
};
const result = (v, line) => v > line ? "HIT" : v === line ? "PUSH" : "MISS";
function hitRate(vals, line) {
  const r = vals.map(v => result(v, line)), n = r.length;
  const hit = r.filter(x => x === "HIT").length, push = r.filter(x => x === "PUSH").length;
  return {n, hit, push, miss: n - hit - push, pct: n ? hit / n : null};
}
function streak(vals, line) { // vals newest first; PUSH ends a streak
  if (!vals.length) return null; const first = result(vals[0], line); if (first === "PUSH") return {type: "PUSH", len: 1};
  let k = 0; while (k < vals.length && result(vals[k], line) === first) k++; return {type: first, len: k};
}
const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
const median = a => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const sd = a => { if (a.length < 2) return null; const m = mean(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)); };
function describe(vals) { return vals.length ? {n: vals.length, mean: mean(vals), median: median(vals), max: Math.max(...vals), min: Math.min(...vals), sd: sd(vals)} : null; }
function erf(x) { const t = 1 / (1 + 0.3275911 * Math.abs(x)); const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x); return x >= 0 ? y : -y; }
const Phi = z => 0.5 * (1 + erf(z / Math.SQRT2));
// Discrete pmf: Poisson if variance <= mean, else negative binomial. Returns array pmf[0..K].
function countPmf(mu, variance, K) {
  const p = []; if (variance <= mu * 1.001) { p[0] = Math.exp(-mu); for (let k = 0; k < K; k++) p[k + 1] = p[k] * mu / (k + 1); }
  else { const r = mu * mu / (variance - mu), q = mu / (r + mu); p[0] = Math.pow(r / (r + mu), r); for (let k = 0; k < K; k++) p[k + 1] = p[k] * (k + r) / (k + 1) * q; }
  return p;
}
// Returns {over, push, under} for a line, from a distribution with mean mu and sd s.
function probabilities(mu, s, line, normal) {
  const whole = Number.isInteger(line); let over, push, under;
  if (normal) {
    const cdf = k => Phi((k + 0.5 - mu) / s); // P(X<=k), integer-valued stat
    if (whole) { under = cdf(line - 1); push = cdf(line) - cdf(line - 1); over = 1 - cdf(line); }
    else { under = cdf(Math.floor(line)); push = 0; over = 1 - under; }
  } else {
    const K = Math.max(60, Math.ceil(mu * 6)), p = countPmf(mu, s * s, K), cum = k => p.slice(0, Math.max(0, k + 1)).reduce((a, b) => a + b, 0);
    if (whole) { under = cum(line - 1); push = p[line] || 0; over = 1 - cum(line); }
    else { under = cum(Math.floor(line)); push = 0; over = 1 - under; }
  }
  return {over, push, under};
}
// Model: recency-weighted mean blended with longer-run mean, home/away adjustment (shrunk), distribution fit to recent variance.
function predict(logs, propKey, line, isHome, factors) {
  const P = PROPS[propKey], v = logs.map(P.f), n = v.length;
  if (n < 5) return null;
  const rec = v.slice(0, 20), w = rec.map((_, i) => Math.pow(0.92, i));
  const wmean = rec.reduce((s, x, i) => s + x * w[i], 0) / w.reduce((a, b) => a + b, 0);
  let mu = 0.7 * wmean + 0.3 * mean(v.slice(0, 40));
  const site = logs.filter(l => !!l[2] === isHome).map(P.f);
  if (site.length >= 3 && mean(v) > 0) { const k = site.length / (site.length + 8); mu *= 1 + Math.max(-0.1, Math.min(0.1, k * (mean(site) / mean(v) - 1))); }
  for (const f of factors || []) mu *= f.f; // context adjustments (pace, defense, blowout, rest, teammates)
  let s = sd(rec); s = Math.max(s, Math.sqrt(mu) * (P.normal ? 0.8 : 0.9)); // floor guards against over-confident tiny samples
  const pr = probabilities(mu, s, line, !!P.normal);
  const cv = s / Math.max(mu, 0.1), conf = n >= 20 && cv < 0.5 ? "High" : n >= 10 ? "Medium" : "Low";
  return {mu, sd: s, ...pr, conf, n};
}
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const addDay = (d, k) => new Date(Date.parse(d + "T00:00:00Z") + k * 864e5).toISOString().slice(0, 10);
const norm = s => s.normalize("NFD").replace(/[\u0300-\u036f.'’ ]/g, "").toLowerCase();
function withWithout(p, mate, f) { // player's stat in games with vs without a teammate, same date window
  const ids = new Set(mate.logs.map(l => l[11])), win = p.logs.filter(l => l[0] >= mate.logs[mate.logs.length - 1][0]);
  const wi = win.filter(l => ids.has(l[11])).map(f), wo = win.filter(l => !ids.has(l[11])).map(f);
  return {nWith: wi.length, nWithout: wo.length, mWith: wi.length ? mean(wi) : null, mWithout: wo.length ? mean(wo) : null};
}
// sit: {opp, home, teams, lgDef, scoreDate, out:[{p, status}]}. Every factor is a small, capped, shrunk heuristic (not backtested).
function ctxFactors(p, propKey, sit) {
  const fs = [], P = PROPS[propKey], f = P.f, all = p.logs, T = sit.teams || {}, A = T[p.team], B = T[sit.opp], mates = [];
  if (A && B) {
    const gp = (A.pace + B.pace) / 2;
    fs.push({name: "Game pace", f: 1 + clamp(0.5 * (gp / A.pace - 1), -0.05, 0.05), note: `expected ${gp.toFixed(1)} possessions vs team average ${A.pace.toFixed(1)}`});
    if (["PTS", "PR", "PA", "PRA"].includes(propKey) && sit.lgDef) fs.push({name: "Opponent defense", f: 1 + clamp(0.5 * (B.def / sit.lgDef - 1), -0.06, 0.06), note: `${sit.opp} defensive rating ${B.def.toFixed(1)} vs league ${sit.lgDef.toFixed(1)}`});
    const m = A.net - B.net + (sit.home ? 3 : -3), pb = 1 - (Phi((15 - m) / 12) - Phi((-15 - m) / 12)), starter = mean(all.slice(0, 10).map(l => l[3])) >= 28;
    fs.push({name: "Blowout risk", f: 1 - 0.06 * pb * (starter ? 1 : 0.3), note: `${Math.round(pb * 100)}% chance of a 15+ point game, estimated from team ratings (not a betting spread)`});
  }
  if (sit.scoreDate && all.length && all[0][0] === addDay(sit.scoreDate, -1)) {
    const b = [], o = []; all.forEach((l, i) => { const pv = all[i + 1]; (pv && addDay(pv[0], 1) === l[0] ? b : o).push(f(l)); });
    if (b.length >= 3 && o.length) fs.push({name: "Back-to-back", f: 1 + clamp(b.length / (b.length + 15) * (mean(b) / mean(o) - 1), -0.08, 0.08), note: `played yesterday; ${b.length} past back-to-backs on file`});
    else fs.push({name: "Back-to-back", f: 1, note: "played yesterday; too few past back-to-backs to adjust"});
  }
  for (const o of (sit.out || []).filter(o => o.p.id !== p.id && o.p.team === p.team).sort((a, b) => mean(b.p.logs.slice(0, 10).map(l => l[3])) - mean(a.p.logs.slice(0, 10).map(l => l[3]))).slice(0, 4)) {
    const w = withWithout(p, o.p, f), ok = w.nWith >= 3 && w.nWithout >= 3 && w.mWith > 0;
    mates.push({name: o.p.name, status: o.status, ...w, ok});
  }
  const use = mates.find(m => m.ok);
  if (use) fs.push({name: "Teammate out", f: 1 + clamp(use.nWithout / (use.nWithout + 10) * (use.mWithout / use.mWith - 1), -0.15, 0.15), note: `${use.name} (${use.status}): ${use.mWithout.toFixed(1)} avg in ${use.nWithout} games without him vs ${use.mWith.toFixed(1)} in ${use.nWith} with`});
  return {factors: fs, mates};
}
if (typeof module !== "undefined") module.exports = {ctxFactors, withWithout, norm, addDay, PROPS, result, hitRate, streak, describe, probabilities, predict, mean, median, sd};
