from pathlib import Path

TEMPLATE = Path("docs/dashboard_multi_source.html")
MARKER = "<!-- FETCH_STATUS_WIDGET -->"

STYLE = """
.fetch-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:14px 0}.fetch-card{background:#101c2d;border:1px solid #20334d;border-radius:14px;padding:12px}.fetch-name{font-weight:800;font-size:13px}.fetch-time{font-size:11px;color:#91a2b9;margin-top:6px}.fetch-ok{color:#8ff0ae;font-weight:900}.fetch-fail{color:#ff8d8d;font-weight:900}.fetch-unknown{color:#ffd98a;font-weight:900}@media(max-width:900px){.fetch-grid{grid-template-columns:repeat(2,1fr)}}
"""

HTML = """
<!-- FETCH_STATUS_WIDGET -->
<section class="fetch-grid" id="fetchStatusGrid">
  <div class="fetch-card"><div class="fetch-name">🇴🇲 Tender Board</div><div class="fetch-time" id="fetch-Oman-Tender-Board">Checking…</div></div>
  <div class="fetch-card"><div class="fetch-name">🏛 SQU</div><div class="fetch-time" id="fetch-SQU">Checking…</div></div>
  <div class="fetch-card"><div class="fetch-name">♻️ be'ah</div><div class="fetch-time" id="fetch-BEAH">Checking…</div></div>
  <div class="fetch-card"><div class="fetch-name">📡 Omantel</div><div class="fetch-time" id="fetch-OMANTEL">Checking…</div></div>
  <div class="fetch-card"><div class="fetch-name">🛒 JAGGAER</div><div class="fetch-time" id="fetch-JAGGAER">Checking…</div></div>
</section>
<script>
async function loadFetchStatus(){
  const ids={"Oman Tender Board":"fetch-Oman-Tender-Board",SQU:"fetch-SQU",BEAH:"fetch-BEAH",OMANTEL:"fetch-OMANTEL",JAGGAER:"fetch-JAGGAER"};
  try{
    const r=await fetch("./fetch_status.json?v="+Date.now(),{cache:"no-store"});
    if(!r.ok) throw Error("HTTP "+r.status);
    const j=await r.json();
    for(const [name,id] of Object.entries(ids)){
      const el=document.getElementById(id),s=(j.sources||{})[name]||{};
      const status=String(s.status||"unknown").toLowerCase();
      const label=status==="success"?"✅ SUCCESS":status==="failed"?"❌ FAILED":"⚠️ UNKNOWN";
      el.className="fetch-time "+(status==="success"?"fetch-ok":status==="failed"?"fetch-fail":"fetch-unknown");
      const t=s.fetched_at?new Date(s.fetched_at).toLocaleString("en-IN",{dateStyle:"medium",timeStyle:"short",timeZone:"Asia/Muscat"})+" (Oman)":"No fetch yet";
      el.textContent=label+" • "+t;
    }
  }catch(e){
    for(const id of Object.values(ids)){const el=document.getElementById(id);if(el){el.textContent="⚠️ Status unavailable";el.className="fetch-time fetch-unknown";}}
  }
}
loadFetchStatus();
</script>
"""


def patch(path: Path):
    text = path.read_text(encoding="utf-8")
    # The redesigned dashboard owns its own source-health UI. Keep the legacy
    # injector for older templates, but never add a duplicate block to the new one.
    if MARKER in text or 'id="sources"' in text:
        return False
    text = text.replace("</style>", STYLE + "</style>", 1)
    anchor = '<div id="updateStatus" class="update-status">'
    pos = text.find(anchor)
    if pos == -1:
        raise SystemExit(f"Dashboard anchor not found in {path}")
    text = text[:pos] + HTML + text[pos:]
    path.write_text(text, encoding="utf-8")
    return True


if __name__ == "__main__":
    changed = patch(TEMPLATE)
    print("Fetch status dashboard injected" if changed else "Fetch status dashboard already present")
