const S = require("./stats.js"), eq = (a, b, m) => { if (Math.abs(a - b) > 1e-6) { console.error("FAIL", m, a, b); process.exit(1); } };
const v = [32, 21, 25, 27, 18];
console.log(S.result(25, 25), S.result(25, 25.5)); // PUSH on whole line only
eq(S.hitRate(v, 25).hit, 2, "hits"); eq(S.hitRate(v, 25).push, 1, "push"); eq(S.hitRate(v, 25.5).push, 0, "no push on .5");
eq(S.streak([30, 28, 10], 25).len, 2, "streak"); eq(S.median([1, 3, 2, 10]), 2.5, "median"); eq(S.sd([2, 4, 4, 4, 5, 5, 7, 9]), 2.138089935, "sd");
for (const [mu, s, line, nm] of [[25, 6, 25.5, 1], [25, 6, 25, 1], [7, 3, 7, 0], [7, 2, 6.5, 0], [2, 1.2, 2, 0]]) {
  const p = S.probabilities(mu, s, line, !!nm); eq(p.over + p.push + p.under, 1, "sums to 1 " + [mu, s, line]); console.log(mu, s, line, nm ? "normal" : "count", p.over.toFixed(3), p.push.toFixed(3), p.under.toFixed(3));
}

const mk=(id,team,rows)=>({id,name:"P"+id,team,logs:rows});
const star=mk(1,"AAA",[["2026-11-07","BBB",1,36,30,5,5,2,1,1,3,"g5"],["2026-11-05","BBB",1,36,28,5,5,2,1,1,3,"g4"],["2026-11-03","CCC",0,35,20,5,5,2,1,1,3,"g3"],["2026-11-01","CCC",0,35,18,5,5,2,1,1,3,"g2"],["2026-10-30","DDD",1,34,22,5,5,2,1,1,3,"g1"]]);
const mate=mk(2,"AAA",[["2026-11-03","CCC",0,30,10,5,5,2,1,1,3,"g3"],["2026-11-01","CCC",0,30,10,5,5,2,1,1,3,"g2"],["2026-10-30","DDD",1,30,10,5,5,2,1,1,3,"g1"]]);
const wo=S.withWithout(star,mate,S.PROPS.PTS.f); eq(wo.nWith,3,"with n"); eq(wo.nWithout,2,"without n"); eq(wo.mWithout,29,"without mean");
const r=S.ctxFactors(star,"PTS",{opp:"BBB",home:true,teams:{AAA:{pace:100,def:112,net:2},BBB:{pace:104,def:116,net:-3}},lgDef:114,scoreDate:"2026-11-08",out:[{p:mate,status:"Out"}]});
console.log(r.factors.map(f=>f.name+" "+f.f.toFixed(3)).join(" | ")); r.factors.forEach(f=>{if(Math.abs(f.f-1)>0.15)throw new Error("factor out of cap")});
eq(r.factors.some(f=>f.name==="Back-to-back"),true,"b2b detected"); eq(S.ctxFactors(star,"PTS",{opp:"BBB",home:true,teams:{},scoreDate:"2026-11-10",out:[]}).factors.length,0,"no data => no factors");
console.log("ALL TESTS PASSED");
