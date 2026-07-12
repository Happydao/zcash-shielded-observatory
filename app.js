const ZAT = 100_000_000n;
const $ = (id) => document.getElementById(id);

function bigint(value) { return value === null || value === undefined ? null : BigInt(value); }
function formatZec(value, compact = true) {
  const raw = bigint(value);
  if (raw === null) return "Not available";
  const sign = raw < 0n ? "−" : raw > 0n ? "+" : "";
  const abs = raw < 0n ? -raw : raw;
  const whole = abs / ZAT;
  const fraction = String(abs % ZAT).padStart(8, "0");
  if (compact && whole >= 1_000_000n) return `${sign}${(Number(whole) / 1_000_000).toFixed(2)}M ZEC`;
  if (compact && whole >= 10_000n) return `${sign}${(Number(whole) / 1_000).toFixed(1)}K ZEC`;
  const grouped = whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${sign}${grouped}.${fraction.slice(0, compact ? 2 : 8)} ZEC`;
}
function pctBps(value) { return value == null ? "—" : `${(Number(value) / 10_000).toFixed(2)}%`; }
function deltaPct(value) { if (value == null) return "—"; const n=Number(value)/10_000; return `${n>0?"+":n<0?"−":""}${Math.abs(n).toFixed(2)}%`; }
function text(id, value) { const node = $(id); if (node) node.textContent = value; }
function number(value) { return Number(value || 0).toLocaleString("en-US"); }
function dateTime(value) { return new Intl.DateTimeFormat("en", {month:"short",day:"numeric",hour:"2-digit",minute:"2-digit",timeZone:"UTC",timeZoneName:"short"}).format(new Date(value)); }
function deltaClass(value) { const n = bigint(value); return n === null || n === 0n ? "" : n > 0n ? "positive" : "negative"; }

function renderActivation(data) {
  const activation = data.activation;
  const ironwood = data.pools.ironwood;
  const module = document.querySelector(".ironwood-core");
  const proximity = Math.max(0, Math.min(1, 1 - Number(activation.blocks_remaining) / 25_000));
  const urgency = Math.pow(proximity, 1.35);
  module.style.setProperty("--orbit-a-speed", `${(28 - urgency * 20).toFixed(2)}s`);
  module.style.setProperty("--orbit-b-speed", `${(20 - urgency * 14).toFixed(2)}s`);
  module.style.setProperty("--orbit-c-speed", `${(14 - urgency * 10).toFixed(2)}s`);
  module.style.setProperty("--pulse-speed", `${(2.8 - urgency * 1.45).toFixed(2)}s`);
  module.style.setProperty("--grid-intensity", (0.15 + urgency * 0.13).toFixed(3));
  module.style.setProperty("--orbit-intensity", (0.14 + urgency * 0.24).toFixed(3));
  module.style.setProperty("--core-glow", `${Math.round(30 + urgency * 42)}px`);
  module.style.setProperty("--core-halo", `${Math.round(110 + urgency * 85)}px`);
  module.style.setProperty("--particle-scale", (1 + urgency * 0.65).toFixed(2));
  text("current-height", number(activation.current_height));
  text("blocks-remaining", number(activation.blocks_remaining));
  text("ironwood-balance", formatZec(ironwood.balance_zatoshis));
  text("ironwood-map-balance", formatZec(ironwood.balance_zatoshis));
  $("activation-progress").style.width = `${Math.min(100, Number(activation.progress_bps) / 10000)}%`;
  const labels = {
    pending_activation: "Pending activation", supported_pre_activation: "Node ready · pre-activation",
    activation_reached_waiting_data: "Activation reached · awaiting data", backfilling: "Backfilling chain",
    active: "Ironwood active", stale: "Data stale", source_error: "Source error"
  };
  const label = labels[ironwood.status] || ironwood.status;
  module.classList.toggle("is-active", ironwood.active);
  module.classList.toggle("is-transitioning", activation.reached && !ironwood.active);
  text("ironwood-status", label); text("ironwood-map-status", `${label} · ${pctBps(ironwood.supply_share_bps)} of supply`); text("ironwood-data-state", label);
  if (ironwood.active) {
    text("ironwood-status", "Live · Ironwood active");
    document.querySelector(".core-label").textContent = "The shielded protocol is live";
  } else if (activation.reached) {
    document.querySelector(".core-label").textContent = "Activation reached · synchronizing";
  }
  text("zebra-ready", ironwood.supported ? "Zebra reports Ironwood support" : "Zebra source not configured");
  text("readiness-state", ironwood.supported ? "Ready" : "Watching");
  text("ironwood-net", formatZec(ironwood.net_change_24h_zatoshis));
  text("ironwood-since", formatZec(ironwood.net_change_since_activation_zatoshis));
  text("ironwood-message", ironwood.active
    ? "Ironwood is active. Verified block history is being collected automatically."
    : "Collection begins automatically at activation. No synthetic observations are stored.");
  const target = new Date(activation.estimated_at).getTime();
  if (ironwood.active) {
    $("countdown").innerHTML = `<div class="activated-at"><b>ACTIVE</b><span>since block ${number(activation.height)}</span></div>`;
    return;
  }
  function tick() {
    const diff = Math.max(0, target - Date.now());
    const values = [Math.floor(diff / 86400000), Math.floor(diff / 3600000) % 24, Math.floor(diff / 60000) % 60, Math.floor(diff / 1000) % 60];
    $("countdown").querySelectorAll("b").forEach((node, index) => node.textContent = String(values[index]).padStart(2, "0"));
  }
  tick(); setInterval(tick, 1000);
}

function renderSupply(data) {
  const supply = data.supply;
  text("shielded-total", formatZec(supply.shielded_zatoshis));
  text("transparent-total", formatZec(supply.transparent_zatoshis));
  text("shielded-share", `${pctBps(supply.shielded_share_bps)} of emitted supply`);
  text("shielded-percent", pctBps(supply.shielded_share_bps));
  text("transparent-percent", pctBps(supply.transparent_share_bps));
  text("shielded-day", formatZec(supply.net_change_24h_zatoshis));
  text("shielded-week", formatZec(supply.net_change_7d_zatoshis));
  const percent = Number(supply.shielded_share_bps || 0) / 10000;
  $("shielded-bar").style.width = `${percent}%`;
  $("shielded-ring").style.strokeDashoffset = String(615.75 * (1 - percent / 100));
}

function renderPool(name, pool) {
  text(`${name}-balance`, formatZec(pool.balance_zatoshis));
  text(`${name}-share`, `${pctBps(pool.shielded_share_bps)} shielded · ${pctBps(pool.supply_share_bps)} total supply`);
  for (const [period, field] of [["day", "net_change_24h_zatoshis"], ["week", "net_change_7d_zatoshis"]]) {
    const node = $(`${name}-${period}`); if (!node) continue;
    node.textContent = formatZec(pool[field]); node.className = deltaClass(pool[field]);
  }
  const since = $(`${name}-since`);
  if (since) { since.textContent = formatZec(pool.net_change_since_activation_zatoshis); since.className = deltaClass(pool.net_change_since_activation_zatoshis); }
}

function renderSpark(id, history, key, color) {
  const svg = $(id); const points = history.filter((p) => p[key] != null).slice(-45);
  if (points.length < 2) return;
  const vals = points.map((p) => Number(p[key])); const min = Math.min(...vals), max = Math.max(...vals);
  const d = vals.map((v, i) => `${i ? "L" : "M"}${(i/(vals.length-1)*240).toFixed(1)},${(50-(v-min)/Math.max(1,max-min)*42).toFixed(1)}`).join(" ");
  svg.innerHTML = `<path d="${d}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
}

function chartPoints(history, ironwoodHistory) {
  let ironwoodIndex = -1;
  return history.map((point) => {
    while (ironwoodIndex + 1 < ironwoodHistory.length && Number(ironwoodHistory[ironwoodIndex + 1].height) <= Number(point.height)) ironwoodIndex += 1;
    return {
      ...point,
      ironwood: ironwoodIndex >= 0 ? ironwoodHistory[ironwoodIndex].balance_zatoshis : null,
    };
  });
}

function renderChart(history, ironwoodHistory = [], range = "all") {
  const svg = $("history-chart");
  const latest = history.at(-1)?.timestamp || 0;
  const cutoff = range === "all" ? 0 : latest - Number(range) * 86400;
  let points = chartPoints(history, ironwoodHistory).filter((p) => p.timestamp >= cutoff && (p.sapling != null || p.orchard != null));
  if (!points.length) { svg.innerHTML = `<text class="chart-label" x="450" y="180" text-anchor="middle">No observations in this interval</text>`; return; }
  const width=900,height=360,m={t:18,r:20,b:34,l:64},iw=width-m.l-m.r,ih=height-m.t-m.b;
  const max=Math.max(...points.flatMap((p)=>[Number(p.transparent||0),Number(p.sapling||0),Number(p.orchard||0),Number(p.ironwood||0)]),1);
  const x=(i)=>m.l+(points.length === 1 ? iw/2 : i/(points.length-1)*iw), y=(v)=>m.t+ih-Number(v)/max*ih;
  const path=(key)=>{let drawing=false;return points.map((p,i)=>{if(p[key]==null){drawing=false;return ""}const command=drawing?"L":"M";drawing=true;return `${command}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`}).join(" ")};
  let html=`<defs><linearGradient id="orchardGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#86d8a7" stop-opacity=".14"/><stop offset="1" stop-color="#86d8a7" stop-opacity="0"/></linearGradient></defs>`;
  for(let i=0;i<5;i++){const yy=m.t+i*ih/4;const zec=Math.round(max*(4-i)/4/1e8);const val=zec>=1e6?(zec/1e6).toFixed(1)+'M':Math.round(zec/1e3)+'K';html+=`<line class="chart-grid" x1="${m.l}" y1="${yy}" x2="${width-m.r}" y2="${yy}"/><text class="chart-label" x="${m.l-10}" y="${yy+3}" text-anchor="end">${val}</text>`;}
  const orchard=path("orchard"); html+=`<path class="area-orchard" d="${orchard} L${width-m.r},${height-m.b} L${m.l},${height-m.b}Z"/><path class="chart-path" stroke="#8ec5d6" d="${path("transparent")}"/><path class="chart-path" stroke="#86d8a7" d="${orchard}"/><path class="chart-path" stroke="#b6a98a" d="${path("sapling")}"/>`;
  if(points.some(p=>p.ironwood!=null)) html+=`<path class="chart-path" stroke="#c9ff6a" d="${path("ironwood")}"/>`;
  [0,.5,1].forEach((r)=>{const p=points[Math.round((points.length-1)*r)];html+=`<text class="chart-label" x="${m.l+iw*r}" y="${height-10}" text-anchor="${r===0?'start':r===1?'end':'middle'}">${new Date(p.timestamp*1000).toLocaleDateString('en',{year:'numeric',month:'short',day:range==='all'?undefined:'numeric'})}</text>`});
  svg.innerHTML=html;
}

function visibleRangePoints(data, range) {
  const merged=chartPoints(data.history,data.ironwood_history||[]);
  const latest=merged.at(-1)?.timestamp||0;
  const cutoff=range==="all"?0:latest-Number(range)*86400;
  return merged.filter((point)=>point.timestamp>=cutoff);
}

function pointShielded(point) {
  return ["sprout","sapling","orchard","ironwood"].reduce((sum,key)=>sum+BigInt(point[key]||0),0n);
}

function pointTotal(point) {
  return ["transparent","sprout","sapling","orchard","ironwood","lockbox"].reduce((sum,key)=>sum+BigInt(point[key]||0),0n);
}

function pointShare(part, total) {
  return total===0n?0:Number(part*1_000_000n/total)/10_000;
}

function renderRangeLens(data, range="all") {
  const points=visibleRangePoints(data,range),start=points[0],end=points.at(-1);
  if (!start || !end) return;
  const shortDate=(timestamp)=>new Date(timestamp*1000).toLocaleDateString("en",{month:"short",year:"numeric"});
  text("lens-dates",`${shortDate(start.timestamp)} — ${shortDate(end.timestamp)}`);
  text("lens-blocks",`Block ${number(start.height)} → ${number(end.height)}`);
  const startShielded=pointShielded(start),endShielded=pointShielded(end),startTotal=pointTotal(start),endTotal=pointTotal(end);
  const startShare=pointShare(startShielded,startTotal),endShare=pointShare(endShielded,endTotal),shareChange=endShare-startShare;
  text("lens-shielded-share",`${endShare.toFixed(2)}%`);
  text("lens-share-change",`${shareChange>0?"+":shareChange<0?"−":""}${Math.abs(shareChange).toFixed(2)} percentage points`);
  const rows=[
    ["Transparent",bigint(end.transparent),"transparent"],
    ["Orchard",bigint(end.orchard),"orchard"],
    ["Sapling",bigint(end.sapling),"sapling"],
    ["Ironwood",end.ironwood==null?null:bigint(end.ironwood),"ironwood"],
  ];
  $("lens-pools").innerHTML=rows.map(([name,value,className])=>{
    const share=value==null?null:pointShare(value,endTotal);
    return `<div class="lens-pool ${className}"><div><span>${name}</span><b>${share==null?"—":`${share.toFixed(2)}%`}</b></div><div class="lens-bar"><i style="width:${share==null?0:Math.max(.4,share)}%"></i></div><small>${value==null?"Pending activation":formatZec(value)}</small></div>`;
  }).join("");
  const netShielded=endShielded-startShielded;
  text("lens-net-shielded",formatZec(netShielded));
  $("lens-net-shielded").className=deltaClass(netShielded);
  text("lens-period-label",({all:"Across all available history","365":"Across the selected year","30":"Across the selected 30 days","7":"Across the selected 7 days","1":"Across the selected 24 hours"})[range]);
}

function renderIntegrity(data) {
  const diff=bigint(data.supply.accounting_difference_zatoshis); text("accounting-diff",formatZec(diff,false));
  const ok=diff===0n; text("integrity-icon",ok?"✓":"!"); text("integrity-copy",ok?"Public value-pool accounting balances":"Accounting difference detected");
  text("chain-status",`${data.health.chain_status} · ${data.health.status}`); text("last-update",dateTime(data.generated_at));
  text("footer-tip",number(data.activation.current_height)); text("footer-time",dateTime(data.generated_at));
  $("live-dot").style.background=data.health.status==="ok"?"var(--lime)":"var(--danger)";
  const supply=data.supply,pools=data.pools,legacy=bigint(supply.legacy_sprout_zatoshis||0)+bigint(supply.lockbox_zatoshis||0);
  text("eq-transparent",formatZec(supply.transparent_zatoshis));text("eq-sapling",formatZec(pools.sapling.balance_zatoshis));text("eq-orchard",formatZec(pools.orchard.balance_zatoshis));text("eq-ironwood",formatZec(pools.ironwood.balance_zatoshis));text("eq-legacy",formatZec(legacy));
  text("emitted-supply",formatZec(supply.total_zatoshis));text("accounted-supply",formatZec(bigint(supply.total_zatoshis)-diff));text("integrity-difference",formatZec(diff,false));
  const balanced=diff===0n, active=pools.ironwood.active, reached=data.activation.reached;
  text("assurance-state",balanced?(active?"Supply bound active":"Public accounting balanced"):"Accounting discrepancy");
  text("turnstile-state",active?"Active · consensus enforced":reached?"Activation reached · verifying":"Pending NU6.3");
  text("assurance-message",active?"Ironwood consensus rules prevent excess ZEC from being accepted out of Orchard, restoring a verifiable upper bound on circulating supply.":"Public value-pool accounting currently matches the emitted ZEC supply.");
  text("integrity-proof-copy",active?"Ironwood is active. Its turnstile rules prevent excess value from leaving Orchard and entering circulation.":"All public value pools currently add up to the emitted ZEC supply. After NU6.3, Ironwood’s turnstile rules will prevent excess value from leaving Orchard and entering circulation.");
  $("assurance-light").style.background=balanced?(active?"#f4b728":"var(--lime)"):"var(--danger)";
}

async function init(){
  try{
    const response=await fetch("data/data.json",{cache:"no-store"}); if(!response.ok)throw new Error(response.status);
    const data=await response.json(); renderActivation(data); renderSupply(data); renderPool("sapling",data.pools.sapling); renderPool("orchard",data.pools.orchard);
    let selectedRange="all";const redraw=()=>{renderChart(data.history,data.ironwood_history||[],selectedRange);renderRangeLens(data,selectedRange)};
    renderSpark("sapling-spark",data.history,"sapling","#b6a98a"); renderSpark("orchard-spark",data.history,"orchard","#86d8a7"); redraw(); renderIntegrity(data);
    document.querySelectorAll("[data-range]").forEach((button)=>button.addEventListener("click",()=>{document.querySelectorAll("[data-range]").forEach(b=>b.classList.remove("active"));button.classList.add("active");selectedRange=button.dataset.range;redraw()}));
  }catch(error){console.error(error);text("chain-status","Dataset unavailable");$("live-dot").style.background="var(--danger)";}
  const observer=new IntersectionObserver((entries)=>entries.forEach((entry)=>entry.isIntersecting&&entry.target.classList.add("visible")),{threshold:.08});document.querySelectorAll(".reveal").forEach((node)=>observer.observe(node));
}
init();
