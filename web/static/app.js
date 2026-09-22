const TYPE_COLOR = {normal:"#9fa19f",fire:"#e8622c",water:"#3d9bfd",electric:"#f2c33a",
 grass:"#4fbf5c",ice:"#5fd0d6",fighting:"#d3425f",poison:"#a865c9",ground:"#d9a55c",
 flying:"#8fa8e8",psychic:"#f7628f",bug:"#92bc2c",rock:"#c4b06b",ghost:"#6b5fa8",
 dragon:"#7b62e3",dark:"#5a5366",steel:"#7b9aa8",fairy:"#ef8fe0"};
const $ = s => document.querySelector(s);

// White-on-yellow (electric, ice, bug, ground...) is unreadable on a light
// page. Pick the label colour from the badge's own luminance rather than
// maintaining a hand-kept list of "light" types.
function inkFor(hex){
  const n = parseInt(hex.slice(1), 16);
  const srgb = [(n>>16)&255, (n>>8)&255, n&255].map(v => {
    v /= 255; return v <= .03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4);
  });
  const L = .2126*srgb[0] + .7152*srgb[1] + .0722*srgb[2];
  return L > .42 ? "#2a2410" : "#ffffff";       // dark ink on light badges
}
const badge = t => {
  const c = TYPE_COLOR[t] || "#9aa4b2", ink = inkFor(c);
  return `<span class="t" style="background:${c};color:${ink};text-shadow:${
    ink === "#ffffff" ? "0 1px 1px rgba(0,0,0,.25)" : "none"}">${t}</span>`;
};
const sprite = (id, shiny) => `/static/sprites/${shiny?"shiny":"normal"}/${id}.png`;

let DEX = [], sel = null, party = [], preview = null, seed = Math.random();
let hydrated = false;
const STATS = ["hp","atk","def","spe","spa","spd"];
let ivs = {}, evs = {}, moveSel = [null,null,null,null], legalMoves = [];

function ivEvUI(){
  $("#ivEv").innerHTML = STATS.map(k=>`
    <div class="ivrow"><b>${k}</b>
      <div class="pair">
        <div style="flex:1"><input data-k="${k}" data-t="iv" type="number" min="0" max="31"
             value="${ivs[k] ?? 31}"><div class="lbl">IV</div></div>
        <div style="flex:1"><input data-k="${k}" data-t="ev" type="number" min="0" max="255"
             value="${evs[k] ?? 0}"><div class="lbl">EV</div></div>
      </div>
    </div>`).join("");
  evTotal();
}
function evTotal(){
  const t = STATS.reduce((a,k)=>a+(+evs[k]||0),0);
  const el = $("#evTotal");
  el.textContent = `EV ${t} / 510`;
  el.classList.toggle("evover", t > 510);
}
$("#ivEv").addEventListener("input", e => {
  const i = e.target; if (!i.dataset.k) return;
  const v = Math.max(0, Math.min(i.dataset.t === "iv" ? 31 : 255, +i.value || 0));
  (i.dataset.t === "iv" ? ivs : evs)[i.dataset.k] = v;
  evTotal(); refresh();
});
$("#ivMaxBtn").addEventListener("click", ()=>{ STATS.forEach(k=>ivs[k]=31); ivEvUI(); refresh(); });
$("#ivRandBtn").addEventListener("click", ()=>{
  STATS.forEach(k=>ivs[k]=Math.floor(Math.random()*32)); ivEvUI(); refresh(); });
$("#evClearBtn").addEventListener("click", ()=>{ STATS.forEach(k=>evs[k]=0); ivEvUI(); refresh(); });

async function loadMoves(natdex){
  legalMoves = await (await fetch(`/api/moves/${natdex}`)).json();
  moveSel = [null,null,null,null];
  const opts = '<option value="">—</option>' +
    legalMoves.map(m=>`<option value="${m.id}">${m.name} (Lv ${m.level})</option>`).join("");
  $("#moveSel").innerHTML = [0,1,2,3].map(i=>`
    <div><label>Move ${i+1}</label><select data-mv="${i}">${opts}</select></div>`).join("");
}
$("#moveSel").addEventListener("change", e => {
  const i = e.target.dataset.mv; if (i === undefined) return;
  moveSel[+i] = e.target.value ? +e.target.value : null;
  refresh();
});

// ---------- dex ----------
function renderDex(filter="") {
  const f = filter.trim().toLowerCase();
  const list = DEX.filter(p => !f || p.name.toLowerCase().includes(f)
                                  || String(p.natdex) === f.replace(/^#/,""));
  $("#dexcount").textContent = `${list.length}`;
  $("#dex").innerHTML = list.map(p => `
    <div class="row${sel && sel.natdex===p.natdex ? " on":""}" data-id="${p.natdex}"
         style="--type:${TYPE_COLOR[p.types[0]]||"#8a8a8a"}">
      <img loading="lazy" src="${sprite(p.natdex,false)}" alt="">
      <div><div class="nm">${p.name}</div><div class="id">#${String(p.natdex).padStart(3,"0")}</div></div>
      <div class="types">${p.types.map(badge).join("")}</div>
    </div>`).join("");
}
$("#dex").addEventListener("click", e => {
  const row = e.target.closest(".row"); if (!row) return;
  sel = DEX.find(p => p.natdex === +row.dataset.id);
  seed = Math.random(); renderDex($("#q").value);
  loadMoves(sel.natdex).then(refresh);
});
$("#q").addEventListener("input", e => renderDex(e.target.value));

// ---------- builder ----------
const shinyOn = () => $("#shinyTog").classList.contains("on");
$("#shinyTog").addEventListener("click", () => { $("#shinyTog").classList.toggle("on"); refresh(); });
$("#lv").addEventListener("input", e => { $("#lvv").textContent = e.target.value; refresh(); });
["nature","nick","ot"].forEach(id => $("#"+id).addEventListener("change", refresh));
$("#ot").addEventListener("input", e => $("#otEcho").textContent = e.target.value || "EMU");
$("#rerollBtn").addEventListener("click", () => { seed = Math.random(); refresh(); });

function params() {
  const chosen = moveSel.filter(Boolean);
  return {natdex: sel.natdex, level: +$("#lv").value, shiny: shinyOn(),
          nature: $("#nature").value || null, nickname: $("#nick").value || null,
          ot: $("#ot").value || "EMU", seed,
          item: +$("#item").value || 0,
          friendship: +$("#friend").value || 70,
          moves: chosen.length ? chosen : null,
          ivs: Object.keys(ivs).length ? ivs : null,
          evs: Object.keys(evs).length ? evs : null};
}

let t = null;
function refresh() {
  if (!sel) return;
  document.documentElement.style.setProperty("--type", TYPE_COLOR[sel.types[0]] || "#8a8a8a");
  $("#art").src = sprite(sel.natdex, shinyOn());
  $("#shinyBadge").hidden = !shinyOn();
  $("#pname").textContent = sel.name;
  $("#ptypes").innerHTML = sel.types.map(badge).join("");
  clearTimeout(t); t = setTimeout(async () => {
    const r = await fetch("/api/preview", {method:"POST",headers:{"Content-Type":"application/json"},
                                           body: JSON.stringify(params())});
    const m = await r.json();
    $("#buildErr").innerHTML = "";
    if (!r.ok) { $("#buildErr").innerHTML = `<div class="err-banner">${m.error}</div>`; return; }
    preview = m;
    $("#pmeta").innerHTML = `#${String(m.natdex).padStart(3,"0")} · internal index ${m.index}
      · Lv ${m.level} · ${m.nature} · PID ${m.pid}` + (m.shiny ? ' · <b style="color:var(--accent-2)">SHINY</b>' : "");
    $("#pmoves").innerHTML = m.moves.map(x=>`<span class="mv">${x}</span>`).join("")
      + (m.item ? `<span class="mv" style="border-color:var(--red);color:var(--red-dk)">@ ${m.item_name}</span>` : "");
    // reflect what the server actually produced (EVs may have been trimmed)
    if (m.evs) { evs = {...m.evs}; evTotal(); }
    const max = {hp:255,atk:190,def:250,spe:200,spa:194,spd:250};
    $("#stats").innerHTML = Object.entries(m.stats).map(([k,v])=>`
      <div class="st"><b>${k}</b><div class="bar"><i style="width:${Math.min(100,v/ (max[k]||255)*100)}%"></i></div><span>${v}</span></div>`).join("");
    $("#addBtn").disabled = party.length >= 6;
    $("#rerollBtn").disabled = false;
    $("#boxBtn").disabled = false;
  }, 120);
}

// ---------- party ----------
function renderParty() {
  $("#partyn").textContent = `${party.length} / 6`;
  // Six fixed sockets, always drawn -- the machine has six whether or not you
  // have filled them, which is the whole point of the object.
  $("#party").innerHTML = Array.from({length:6}, (_, i) => {
    const p = party[i];
    if (!p) return `<div class="socket" data-i="${i}"><span class="lamp"></span></div>`;
    return `<div class="socket full${p.shiny?" shiny":""}" data-i="${i}"
                 style="--type:${TYPE_COLOR[(DEX.find(d=>d.natdex===p.natdex)||{types:["normal"]}).types[0]]}">
        <span class="lamp on"></span>
        <img src="${sprite(p.natdex,p.shiny)}" alt="">
        <button class="x" data-i="${i}" title="remove">×</button>
        <div class="tip"><b>${p.nickname||p.name}</b><span>Lv ${p.level} · ${p.nature}${p.shiny?" · shiny":""}</span></div>
      </div>`;
  }).join("");
  $("#writeBtn").disabled = party.length < 2;
  $("#addBtn").disabled = !sel || party.length >= 6;
}
$("#party").addEventListener("click", e => {
  const b = e.target.closest(".x"); if (!b) return;
  party.splice(+b.dataset.i,1); renderParty();
});
$("#addBtn").addEventListener("click", () => {
  if (!preview || party.length>=6) return;
  party.push({...params(), name:preview.name, nature:preview.nature, shiny:preview.shiny});
  renderParty();
});

// ---------- box ----------
async function renderBox(){
  const list = await (await fetch("/api/box")).json();
  $("#boxn").textContent = list.length;
  $("#boxList").innerHTML = list.length ? list.map(b=>`
    <div class="boxrow"><img src="${sprite(b.natdex,b.shiny)}" alt="">
      <div><div class="nm">${b.slug}${b.shiny?' <span style="color:#f5a623">✦</span>':""}</div>
        <div class="meta">${b.name} Lv${b.level} · ${b.nature}${b.item_name&&b.item_name!=="None"?" @ "+b.item_name:""}</div></div>
      <div class="acts">
        <button data-add="${b.slug}">Add</button>
        <button data-del="${b.slug}">×</button>
      </div></div>`).join("")
    : `<div class="boxrow empty">box is empty — build one and press Save to box</div>`;
  window.__box = list;
}
$("#boxList").addEventListener("click", async e => {
  const del = e.target.dataset.del, add = e.target.dataset.add;
  if (del) { await fetch("/api/box/"+encodeURIComponent(del), {method:"DELETE"}); renderBox(); }
  if (add) {
    const b = (window.__box||[]).find(x=>x.slug===add);
    if (b && party.length < 6) { party.push({...b.spec, name:b.name, nature:b.nature, shiny:b.shiny});
      renderParty(); log(`added ${b.slug} from the box`, "ok"); }
  }
});
$("#boxBtn").addEventListener("click", async () => {
  if (!preview) return;
  const name = prompt("Save as:", `${preview.name}_Lv${preview.level}${preview.shiny?"_shiny":""}`);
  if (!name) return;
  await post("/api/box", {name, spec: params(), ot: $("#ot").value || "EMU"});
  renderBox();
});

// ---------- actions ----------
async function post(url, body) {
  const r = await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},
                             body: JSON.stringify(body||{})});
  const j = await r.json().catch(()=>({}));
  if (!r.ok) log(j.error || `${url} failed`, "err");
  return {ok:r.ok, j};
}
$("#writeBtn").addEventListener("click", async () => {
  $("#writeBtn").disabled = true;
  await post("/api/party", {slots: party, ot: $("#ot").value || "EMU"});
  poll();
});
$("#radioBtn").addEventListener("click", async e => {
  const take = e.target.dataset.mode !== "give-back";
  await post("/api/radio/" + (take ? "take" : "give-back"));
});
$("#scanBtn").addEventListener("click", () => post("/api/scan"));
$("#listenBtn").addEventListener("click", () => post("/api/diag/listen"));
$("#injectBtn").addEventListener("click", () => post("/api/diag/inject"));
$("#startBtn").addEventListener("click", () => post("/api/trade/start", {verbose:true, ot:$("#ot").value||"EMU"}));
$("#stopBtn").addEventListener("click", () => post("/api/trade/stop"));

// ---------- status + logs ----------
function setDot(id, state, text) {
  $("#d-"+id).className = "dot " + state;
  $("#t-"+id).textContent = text;
}
async function poll() {
  const s = await (await fetch("/api/status")).json();
  setDot("keys", s.keys_present ? "ok":"bad", s.keys_present ? "keys loaded":"no prod.keys");
  setDot("radio", s.ready_for_trade ? "ok" : (s.wired_is_default ? "warn":"bad"),
         s.ready_for_trade ? "radio free" : (s.wifi_is_default ? "wifi in use":"switching"));
  setDot("trade", s.trade_running ? "warn":"ok", s.trade_running ? "trading…":"idle");
  const b = $("#radioBtn");
  b.dataset.mode = s.ready_for_trade ? "give-back" : "take";
  b.textContent  = s.ready_for_trade ? "Restore networking" : "Free the radio";
  const why = !s.keys_present ? "keys/prod.keys is empty"
            : !s.ready_for_trade ? "free the radio first"
            : (s.party||[]).length < 2 ? "write at least 2 .pk3 files"
            : s.trade_running ? "a trade is already running" : "";
  const scanWhy = !s.keys_present ? "keys/prod.keys is empty"
                : !s.ready_for_trade ? "free the radio first"
                : s.trade_running ? "busy" : "";
  const scb = $("#scanBtn");
  if (scb) { scb.disabled = Boolean(scanWhy); scb.title = scanWhy || "Look for a broadcasting console"; }
  for (const [id, tip] of [["listenBtn","Raw 802.11 capture per channel — proves whether the console is emitting at all"],
                           ["injectBtn","Can this card transmit action frames? LDN's hard requirement"]]) {
    const el = $("#"+id);
    if (el) { el.disabled = Boolean(scanWhy); el.title = scanWhy || tip; }
  }
  const sendWhy = !s.keys_present ? "keys/prod.keys is empty"
                : party.length < 2 ? "add at least 2 Pokémon to the party"
                : s.trade_running ? "already running" : "";
  const sendB = $("#sendBtn");
  if (sendB) { sendB.disabled = Boolean(sendWhy); sendB.title = sendWhy || "Send to your game"; }
  $("#startWhy").textContent = sendWhy ? "\u2014 " + sendWhy : "";
  const sb = $("#startBtn");
  sb.disabled = Boolean(why);
  sb.title = why || "Start the trade";
  sb.dataset.why = why;
  $("#stopBtn").disabled  = !s.trade_running;
  // Hydrate the bay from disk on first load. Without this the page shows an
  // empty bay while PARTY*.pk3 exist, and the buttons contradict the UI.
  if (!hydrated) {
    hydrated = true;
    if ((s.party_meta||[]).length) {
      party = s.party_meta.map(m => ({
        natdex: m.req?.natdex ?? m.natdex, level: m.req?.level ?? m.level,
        shiny: m.req?.shiny ?? m.shiny, nature: m.req?.nature ?? m.nature,
        nickname: m.req?.nickname || null, name: m.name, ot: $("#ot").value || "EMU",
      }));
      renderParty();
      log(`loaded the party already on disk: ${party.map(x=>x.name).join(", ")}`, "info");
    } else if ((s.party||[]).length) {
      log(`${s.party.length} .pk3 file(s) on disk from an earlier session `
        + `(no details recorded) — rebuild the party to replace them`, "info");
    }
  }
  $("#received").innerHTML = (s.received||[]).length
     ? "Received: " + s.received.map(f=>`<a href="/api/received/${f}" style="color:var(--info)">${f}</a>`).join(" · ")
     : "";
}
function log(line, kind="l") {
  const c = $("#console");
  if (c.dataset.clean !== "1") { c.innerHTML=""; c.dataset.clean="1"; }
  const d = document.createElement("div");
  d.className = kind; d.textContent = line;
  c.appendChild(d); c.scrollTop = c.scrollHeight;
  while (c.children.length > 900) c.removeChild(c.firstChild);
}
new EventSource("/api/logs").onmessage = e => {
  const m = JSON.parse(e.data);
  if (m.kind === "state") {                 // guided-send progress
    let st = {};
    try { st = JSON.parse(m.line); } catch { return; }
    sendPhase = st.phase; sendActive = st.active;
    statusUI(st.phase, st.attempt, st.detail);
    if (st.detail) sendLog(st.detail, "info");
    if (st.phase === "done") {
      $("#sendName").textContent = "Trade complete";
      $("#sendCancel").textContent = "Close";
      $("#sendCancel").onclick = () => { closeModal("mSend"); poll(); };
    }
    poll();
    return;
  }
  const cls = {cmd:"cmd",ok:"ok",info:"info",done:"done",err:"err"}[m.kind] || "l";
  log(m.line, cls);
  sendLog(m.line, cls);
  if (typeof prepLog === "function" && !$("#mPrep").hidden) prepLog(m.line, cls);
  if (m.kind === "done" || m.kind === "ok") poll();
};

(async () => {
  DEX = await (await fetch("/api/dex")).json();
  const nat = await (await fetch("/api/natures")).json();
  $("#nature").innerHTML = '<option value="">Random</option>' + nat.map(n=>`<option>${n}</option>`).join("");
  const items = await (await fetch("/api/items")).json();
  $("#item").innerHTML = items.map(i=>`<option value="${i.id}">${i.name}</option>`).join("");
  ["item","friend"].forEach(id=>$("#"+id).addEventListener("change", refresh));
  STATS.forEach(k=>{ ivs[k]=31; evs[k]=0; });
  ivEvUI();
  renderDex(); renderParty(); renderBox(); poll(); setInterval(poll, 4000);
  document.querySelector('.row[data-id="25"]')?.click();
})();

/* ============================================================================
   Guided send. One button drives the whole sequence; the manual controls stay
   available behind Developer mode for when it goes wrong.
   ========================================================================== */
const PHASE_STEPS = [
  ["radio", "Freeing the wireless card",
   "Moving this machine onto its wired link so the card can be handed to LDN."],
  ["scan",  "Finding your console",
   "Listening on every LDN channel for a FireRed/LeafGreen trade session."],
  ["join",  "Joining the session",
   "Associating with the console and authenticating as a second player."],
  ["trade", "Trading",
   "Follow the steps on your Switch — the trade happens in-game."],
];
let sendPhase = "idle", sendActive = false;

const openModal  = id => { $("#"+id).hidden = false; document.body.style.overflow="hidden"; };
const closeModal = id => { $("#"+id).hidden = true;  document.body.style.overflow=""; };
document.addEventListener("click", e => {
  const c = e.target.dataset?.close; if (c) closeModal(c);
});

// --- developer mode ---------------------------------------------------------
const DEV_KEY = "frlg.devmode";
function applyDev(on) {
  $("#devPanel").hidden = !on;
  try { localStorage.setItem(DEV_KEY, on ? "1" : "0"); } catch {}
}
$("#devMode").addEventListener("change", e => applyDev(e.target.checked));
try {
  const on = localStorage.getItem(DEV_KEY) === "1";
  $("#devMode").checked = on; applyDev(on);
} catch { applyDev(false); }

// --- step 1: prepare --------------------------------------------------------
const PREP_STEPS = [
  "Checking your console keys",
  "Building the Pokémon data",
  "Writing the trade files",
];
function prepStepsUI(done) {
  $("#prepSteps").innerHTML = PREP_STEPS.map((t,i)=>
    `<div class="prepStep${i<done?" on":""}"><span class="tick"></span>${t}</div>`).join("");
}
// How the trade really works: the .pk3 files are the EMULATOR's party (up to
// six, so the fake trainer looks real). Upstream's --slot defaults to 1, so
// PARTY2 is the one offered and the one that ends up in your game. What YOU
// give up is chosen on the console, in-game, from your own party — this side
// has no say in it. Labelling PARTY1 "you send" was simply wrong.
async function tradeCard(p, role, label) {
  if (!p) return `<div class="tcard" data-role="${label}"><div class="hd">
      <div class="art"></div><div><h4>—</h4>
      <div class="meta">add a second Pokémon to the party</div></div></div></div>`;
  const dex = DEX.find(x => x.natdex === p.natdex) || {types:["normal"]};
  let m = null;
  try {
    const r = await fetch("/api/preview", {method:"POST",
      headers:{"Content-Type":"application/json"}, body: JSON.stringify(p)});
    if (r.ok) m = await r.json();
  } catch {}
  const types = (m?.types || dex.types || []).map(badge).join("");
  const moves = (m?.moves || []).map(x=>`<span class="mv">${x}</span>`).join("");
  return `<div class="tcard ${role}" data-role="${label}"
               style="--type:${TYPE_COLOR[(dex.types||["normal"])[0]]}">
    <div class="hd">
      <div class="art"><img src="${sprite(p.natdex, p.shiny)}" alt=""></div>
      <div style="min-width:0">
        <h4>${p.nickname || p.name}${p.shiny?' <span style="color:#f5a623">✦</span>':""}</h4>
        <div class="meta">#${String(p.natdex).padStart(3,"0")} · Lv ${p.level} · ${m?.nature || p.nature || ""}</div>
      </div>
    </div>
    <div class="row">${types}</div>
    <div class="kv">
      <b>Item</b><span>${m?.item_name && m.item_name !== "None" ? m.item_name : "none"}</span>
      <b>OT</b><span>${$("#ot").value || "EMU"}</span>
      ${m?.pid ? `<b>PID</b><span style="font-family:var(--font-m)">${m.pid}</span>` : ""}
    </div>
    <div class="row">${moves}</div>
  </div>`;
}

function pickControls() {
  const n = party.length;
  const many = $("#howMany"), which = $("#whichSlot");
  const prevMany = +many.value || 1, prevWhich = +which.value || Math.min(1, n-1);
  many.innerHTML = Array.from({length:n}, (_,i)=>
    `<option value="${i+1}">${i+1}${i ? " Pokémon" : " Pokémon"}</option>`).join("");
  many.value = Math.min(prevMany, n);
  const count = +many.value;
  // slots are offered ascending from the starting slot, so the start cannot
  // run past the end of the party
  const maxStart = n - count;
  which.innerHTML = Array.from({length:maxStart+1}, (_,i)=>
    `<option value="${i}">slot ${i+1} — ${party[i].nickname || party[i].name}</option>`).join("");
  which.value = Math.min(prevWhich, maxStart);
  const start = +which.value;
  const names = party.slice(start, start+count).map(p=>p.nickname||p.name);
  $("#pickNote").innerHTML = count === 1
    ? `You will receive <b>${names[0]}</b>. A Gen III trade is symmetric — each side
       offers one of its own party — so the simulated trainer nominates this slot,
       and you pick one of yours on the console.`
    : `<b>${count} trades in a row</b>: ${names.join(", ")}. The trade menu stays up
       between them; give up one of your own each time.`;
}
["howMany","whichSlot"].forEach(id => {
  const el = $("#"+id);
  if (el) el.addEventListener("change", () => { pickControls(); renderPartyStrip(); });
});

// All six slots are transmitted: during the party-exchange phase the console
// receives the simulated trainer's whole gPlayerParty and shows it on the trade
// screen, exactly as it would a real partner's. The trade itself is still
// one-for-one per round — each side nominates one of its OWN — so the
// highlighted slots are the ones the simulated trainer will offer.
function renderPartyStrip() {
  const start = +$("#whichSlot").value || 0;
  const count = +$("#howMany").value || 1;
  const offered = new Set(Array.from({length:count}, (_,i)=>start+i));
  $("#prepParty").innerHTML = Array.from({length:6}, (_,i)=>{
    const p = party[i];
    if (!p) return `<div class="pslot empty"><span class="n">${i+1}</span>
                    <div class="ph"></div><div class="lv">empty</div></div>`;
    const dex = DEX.find(x=>x.natdex===p.natdex) || {types:["normal"]};
    const on = offered.has(i);
    return `<div class="pslot ${on?"offered":"dim"}"
                 style="--type:${TYPE_COLOR[dex.types[0]]}">
      <span class="n">${i+1}</span>
      ${on ? `<span class="tag">to you</span>` : ""}
      <img src="${sprite(p.natdex,p.shiny)}" alt="">
      <div class="nm">${p.nickname||p.name}${p.shiny?" ✦":""}</div>
      <div class="lv">Lv ${p.level}</div></div>`;
  }).join("");
  $("#stripHint").textContent =
    `all ${party.length} appear on your console's trade screen · `
    + `${count === 1 ? "1 is offered to you" : `${count} offered across ${count} rounds`}`;
}

$("#sendBtn").addEventListener("click", async () => {
  if (party.length < 2) return;
  const out = party[0], inc = party[1];
  const d = DEX.find(x => x.natdex === inc.natdex) || {types:["normal"]};
  document.documentElement.style.setProperty("--type", TYPE_COLOR[d.types[0]] || "#9aa4b2");
  $("#prepContinue").disabled = true;
  $("#prepLog").textContent = "";
  prepStepsUI(0);
  $("#prepHint").textContent =
    `Preparing a party of ${party.length} for the simulated trainer…`;
  openModal("mPrep");
  pickControls();
  renderPartyStrip();

  // write the .pk3 files while the reveal animates
  const tick = (n) => new Promise(r => setTimeout(() => { prepStepsUI(n); r(); }, 420));
  await tick(1);
  const { ok, j } = await post("/api/party", {slots: party, ot: $("#ot").value || "EMU"});
  await tick(2);
  if (!ok) {
    prepLog(j.error || "could not build the party", "err");
    return;
  }
  (j.party||[]).forEach(m => prepLog(
    `built ${m.file}: ${m.name} Lv${m.level}${m.shiny?" shiny":""}`, "ok"));
  await tick(3);
  $("#prepHint").textContent =
    `Ready — ${party.length} Pokémon in the simulated party. Get your console to the `
    + `Direct Corner trade screen, then press Continue.`;
  $("#prepContinue").disabled = false;
  poll();
});
function prepLog(line, kind="l") {
  const c = $("#prepLog"); const d = document.createElement("div");
  d.className = kind; d.textContent = line; c.appendChild(d); c.scrollTop = c.scrollHeight;
}

// --- step 2: send -----------------------------------------------------------
$("#prepContinue").addEventListener("click", async () => {
  closeModal("mPrep");
  const count = +$("#howMany").value || 1;
  const start = +$("#whichSlot").value || 0;
  const inc = party[start] || party[1];
  $("#sendHead").innerHTML =
    `<div class="mini"><img src="${sprite(inc.natdex,inc.shiny)}" alt="">
       <div style="min-width:0"><div class="nm">Sending ${inc.nickname||inc.name}${
         count>1 ? ` +${count-1} more` : ""}</div>
       <div class="sb">Lv ${inc.level} · you choose what to give on the console</div></div>
     </div>`;
  $("#sendOt").textContent = $("#ot").value || "EMU";
  $("#sendLog").textContent = "";
  statusUI("radio");
  openModal("mSend");
  const { ok, j } = await post("/api/send/start", {
    trades: +$("#howMany").value || 1,
    slot: +$("#whichSlot").value || 0,
  });
  if (!ok) { sendLog(j.error || "could not start", "err"); }
});
$("#sendCancel").addEventListener("click", async () => {
  await post("/api/send/cancel");
  $("#sendCancel").textContent = "Close";
  $("#sendCancel").onclick = () => closeModal("mSend");
});
function statusUI(phase, attempt, detail) {
  const order = PHASE_STEPS.map(p => p[0]);
  const at = order.indexOf(phase);
  const done = phase === "done";
  $("#statuses").innerHTML = PHASE_STEPS.map(([k,label,blurb],i)=>{
    const cls = done || i < at ? "ok" : (i === at ? "doing" : "");
    const ico = cls === "ok" ? "✓" : (i + 1);
    const sub = (cls === "doing" && detail) ? detail : blurb;
    return `<div class="stg ${cls}">
      <div class="lbl"><span class="ico">${ico}</span>${label}</div>
      <div class="track"><i></i></div>
      <div class="sub">${sub}</div></div>`;
  }).join("");
  $("#attemptN").textContent = attempt ? `attempt ${attempt}` : "";
}
function sendLog(line, kind="l") {
  const c = $("#sendLog"); if (!c) return;
  const d = document.createElement("div"); d.className = kind; d.textContent = line;
  c.appendChild(d); c.scrollTop = c.scrollHeight;
  while (c.children.length > 400) c.removeChild(c.firstChild);
}
