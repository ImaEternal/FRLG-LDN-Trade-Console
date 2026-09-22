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
  const sb = $("#startBtn");
  sb.disabled = Boolean(why);
  sb.title = why || "Start the trade";
  $("#startWhy").textContent = why ? "\u2014 " + why : "";
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
  log(m.line, {cmd:"cmd",ok:"ok",info:"info",done:"done",err:"err"}[m.kind] || "l");
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
