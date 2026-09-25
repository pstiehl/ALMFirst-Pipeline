"""Build a single self-contained HTML report: docs/report.html.

    python scripts/build_report.py

Open the file in any browser (no server, no install). Map tiles and the Leaflet
library load from public CDNs; the credit-union data is embedded in the page.
Public data only: nothing from data/private/ is ever written into the report.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from almpipe.scoring import add_priority, load_products, score  # noqa: E402

OUT = ROOT / "docs" / "report.html"


def main() -> None:
    d = pd.read_csv(ROOT / "data/processed/credit_unions.csv.gz", dtype={"cu_number": str, "zip": str})
    products = load_products(ROOT / "config/products.yaml")
    terr = yaml.safe_load((ROOT / "config/territory.yaml").read_text())
    known = yaml.safe_load((ROOT / "config/known_relationships.yaml").read_text()).get("known", [])
    d = score(d, products)
    m = d["state"].isin(terr["states"]) & (d["assets_m"] >= terr["min_assets_m"])
    d = add_priority(d, m)
    s = d[m].copy()

    kn = {str(k["cu_number"]): k for k in known}
    s["relationship"] = s["cu_number"].map(lambda c: kn[c]["source"] if c in kn else "")
    s["rel_url"] = s["cu_number"].map(lambda c: kn[c].get("url", "") if c in kn else "")

    pk = list(products)
    cols = ["cu_number", "name", "city", "state", "assets_m", "members", "employees", "loan_to_share",
            "nw_ratio", "roa", "liquid_pct", "inv_pct", "long_asset_pct", "afs_loss_to_nw", "borrow_pct",
            "asset_growth_yoy", "share_growth_yoy", "emp_benefit_m", "lat", "lon", "top_product",
            "expected_value", "priority", "relationship", "rel_url", "peer_group"]
    for k in pk:
        cols += [f"fit_{k}", f"why_{k}", f"fee_{k}"]
    out = s[cols].replace({np.nan: None})
    rows = []
    for r in out.to_dict("records"):
        rows.append({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})

    meta = {
        "quarter": str(d["quarter"].iloc[0]) if "quarter" in d else "",
        "built": date.today().isoformat(),
        "states": terr["states"],
        "min_assets_m": terr["min_assets_m"],
        "products": {k: {"label": p["label"], "gate": p.get("gate", {}),
                         "signals": [{"reason": x["reason"], "points": x["points"]} for x in p.get("signals", [])],
                         "base": p.get("base", 0), "fee": p.get("fee", {})} for k, p in products.items()},
        "national_count": int(len(d)),
    }
    html = TEMPLATE.replace("/*DATA*/", json.dumps(rows, separators=(",", ":"))).replace(
        "/*META*/", json.dumps(meta, separators=(",", ":")))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} credit unions, {OUT.stat().st_size/1e6:.2f} MB")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ALM First · Southeast Credit Union Targets</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{--ink:#14213d;--mut:#6b7280;--bg:#f6f7fb;--card:#fff;--line:#e5e7eb;--acc:#0b6e4f}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
header{background:var(--ink);color:#fff;padding:18px 28px}header h1{margin:0;font-size:22px}header p{margin:4px 0 0;color:#cbd5e1}
main{padding:20px 28px;max-width:1500px;margin:auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.kpi b{display:block;font-size:22px}.kpi span{color:var(--mut);font-size:12px}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:16px;position:sticky;top:0;z-index:1000}
.bar label{font-size:12px;color:var(--mut)}.bar select,.bar input{font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px}
.grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:16px}@media(max-width:1000px){.grid{grid-template-columns:1fr}}
.card{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:16px}.card h2{margin:0 0 10px;font-size:16px}
#map{height:560px;border-radius:8px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{position:sticky;top:0;background:#f1f5f9;cursor:pointer;user-select:none}td.n,th.n{text-align:right}tr.row:hover{background:#f0fdf4;cursor:pointer}tr.sel{background:#dcfce7}
.tw{max-height:560px;overflow:auto}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;color:#fff}
.fit{display:inline-block;height:8px;border-radius:4px;background:var(--acc);vertical-align:middle}
#detail{white-space:normal}td{white-space:nowrap}#detail h3{margin:0}#detail .sub{color:var(--mut);margin-bottom:10px}.prod{border-top:1px solid var(--line);padding:8px 0}.prod ul{margin:4px 0 0 18px;padding:0}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:6px 14px;margin:8px 0}.metrics div span{color:var(--mut);font-size:11px;display:block}
.rel{background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;padding:6px 8px;margin:6px 0;font-size:12px}
.legend span{margin-right:12px;font-size:12px}.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}
details summary{cursor:pointer;font-weight:600}.muted{color:var(--mut)}code{background:#f1f5f9;padding:1px 4px;border-radius:4px}
</style></head><body>
<header><h1>Southeast Credit Union Targets · ALM First</h1>
<p id="sub"></p></header>
<main>
<div class="kpis" id="kpis"></div>
<div class="bar">
 <label>State <select id="fState"><option value="">All</option></select></label>
 <label>Min assets ($M) <input id="fMin" type="number" value="50" step="50" style="width:90px"></label>
 <label>Max assets ($M) <input id="fMax" type="number" placeholder="any" style="width:90px"></label>
 <label>Top product <select id="fProd"><option value="">Any</option></select></label>
 <label>Must fit <select id="fFit"><option value="">(no filter)</option></select></label>
 <label>Color map by <select id="fColor"><option value="top">Top product</option><option value="size">Asset size</option><option value="pri">Priority</option></select></label>
 <label>Search <input id="fQ" placeholder="name or city" style="width:150px"></label>
 <span class="muted" id="count"></span>
</div>
<div class="grid">
 <div>
  <div class="card"><h2>Map</h2><div id="map"></div><div class="legend" id="legend" style="margin-top:6px"></div></div>
  <div class="card"><h2>Ranked targets <span class="muted" style="font-weight:400;font-size:12px">click a column to sort · click a row for detail</span></h2>
   <div class="tw"><table id="tbl"><thead></thead><tbody></tbody></table></div></div>
 </div>
 <div>
  <div class="card" id="detail"><h2>Credit union detail</h2><p class="muted">Click a dot on the map or a row in the table.</p></div>
  <div class="card"><h2>By state</h2><table id="st"><thead></thead><tbody></tbody></table></div>
  <div class="card"><h2>By top product</h2><table id="pt"><thead></thead><tbody></tbody></table></div>
  <div class="card"><h2>How the scoring works</h2><div id="rules"></div></div>
 </div>
</div>
<div class="card"><h2>Sources &amp; assumptions</h2>
<ul>
<li><b>NCUA 5300 Call Report</b> (quarterly bulk data, every federally insured credit union). Balance-sheet ratios and YoY growth come from the current and year-ago quarters. Peer percentiles are national within each NCUA peer group.</li>
<li><b>Census 2024 Gazetteer</b> ZIP/place centroids for the map, so dots show the city, not the street address.</li>
<li><b>CPST = Capital Planning &amp; Stress Testing.</b> Under NCUA Part 702 Subpart C, credit unions with $10B+ in assets must do this. Those CUs score as required, and $5B to $10B scores as the prep market.</li>
<li><b>ALM First's fee model</b> (from its Form ADV Part 2A, filed 3/30/2026): advisory and non-discretionary services are generally <i>fixed annual fees</i>, and discretionary management is <i>asset-based with declining rates</i>. Most fees are negotiable. The firm reports $73.9B in non-discretionary and $2.3B in discretionary AUM across 189 clients. The dollar figures here follow that structure, but the actual levels are estimates, not ALM First's rate card.</li>
<li><b>Existing relationships</b> are flagged only when they're publicly documented (see <code>config/known_relationships.yaml</code>). They show as cross-sell accounts, not cold prospects.</li>
<li>Every threshold, weight and fee is set in <code>config/products.yaml</code>. Change it and run <code>python scripts/build_report.py</code> to rebuild this page.</li>
</ul></div>
</main>
<script>
const D=/*DATA*/;const M=/*META*/;
const P=Object.keys(M.products);const PL=k=>M.products[k]?M.products[k].label:'No fit yet (below size gates)';
const COL={alm_advisory:'#0b6e4f',investment_advisory:'#2563eb',model_validation:'#9333ea',cpst:'#dc2626',discretionary:'#ea580c'};
const $=id=>document.getElementById(id);
const fm=v=>v==null?'—':'$'+(v>=1000?(v/1000).toFixed(1)+'B':Math.round(v)+'M');
const fk=v=>v==null?'—':'$'+(v>=1e6?(v/1e6).toFixed(2)+'M':Math.round(v/1000)+'K');
const pc=(v,d=1)=>v==null?'—':(v*100).toFixed(d)+'%';
const nf=v=>v==null?'—':Math.round(v).toLocaleString();
$('sub').textContent=`NCUA call report ${M.quarter} · ${D.length} credit unions ≥ $${M.min_assets_m}M in ${M.states.join(', ')} · built ${M.built}`;
M.states.forEach(s=>$('fState').add(new Option(s,s)));const SL=k=>PL(k).split(' (')[0];P.forEach(k=>{$('fProd').add(new Option(SL(k),k));$('fFit').add(new Option(SL(k)+' ≥ 50',k))});
const map=L.map('map').setView([32.5,-84],5);
L.tileLayer('https://{s}.basemap.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{attribution:'© OpenStreetMap © CARTO',maxZoom:18}).addTo(map);
const layer=L.layerGroup().addTo(map);let sortK='expected_value',sortD=-1,sel=null;
function filt(){const st=$('fState').value,mn=+$('fMin').value||0,mx=+$('fMax').value||1e12,pr=$('fProd').value,ft=$('fFit').value,q=$('fQ').value.toLowerCase();
 return D.filter(r=>(!st||r.state==st)&&r.assets_m>=mn&&r.assets_m<=mx&&(!pr||r.top_product==pr)&&(!ft||r['fit_'+ft]>=50)&&(!q||(r.name+' '+r.city).toLowerCase().includes(q)))}
function color(r){const c=$('fColor').value;if(c=='top')return COL[r.top_product]||'#9ca3af';
 if(c=='pri'){const p=r.priority||0;return p>=90?'#b91c1c':p>=70?'#f97316':p>=40?'#facc15':'#9ca3af'}
 const a=r.assets_m;return a>=10000?'#7f1d1d':a>=5000?'#dc2626':a>=1000?'#f97316':a>=250?'#facc15':'#9ca3af'}
function legend(){const c=$('fColor').value;let items=c=='top'?P.map(k=>[COL[k],PL(k).split(' (')[0]]):c=='pri'?[['#b91c1c','Top 10%'],['#f97316','70–90'],['#facc15','40–70'],['#9ca3af','<40']]:[['#7f1d1d','$10B+'],['#dc2626','$5–10B'],['#f97316','$1–5B'],['#facc15','$250M–1B'],['#9ca3af','<$250M']];
 $('legend').innerHTML=items.map(([c,l])=>`<span><i style="background:${c}"></i>${l}</span>`).join('')+'<span class="muted">· bubble size = total assets · ★ outline = known ALM First relationship</span>'}
const HEAD=[['#',null],['Credit union','name'],['City','city'],['St','state'],['Assets','assets_m',1],['Top product','top_product'],['Est. $/yr','expected_value',1],['Priority','priority',1],['Loan/share','loan_to_share',1],['Net worth','nw_ratio',1],['YoY growth','asset_growth_yoy',1]];
function render(){const f=filt().sort((a,b)=>{const x=a[sortK],y=b[sortK];return (x==null)-(y==null)||(x>y?1:x<y?-1:0)*sortD});
 $('count').textContent=`${f.length} shown`;
 const tot=f.reduce((s,r)=>s+r.assets_m,0),ev=f.reduce((s,r)=>s+r.expected_value,0);
 $('kpis').innerHTML=[[f.length,'credit unions'],[fm(tot),'total assets'],[f.filter(r=>r.assets_m>=10000).length,'≥ $10B (CPST required)'],[f.filter(r=>r.assets_m>=5000&&r.assets_m<10000).length,'$5–10B (CPST prep)'],[f.filter(r=>r.assets_m>=1000).length,'≥ $1B'],[fk(ev),'est. annual revenue pool']].map(([b,s])=>`<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join('');
 layer.clearLayers();f.forEach(r=>{if(r.lat==null)return;const c=L.circleMarker([r.lat,r.lon],{radius:Math.min(28,Math.max(3,Math.sqrt(r.assets_m)/5)),color:r.relationship?'#111':color(r),weight:r.relationship?2.5:1,fillColor:color(r),fillOpacity:.7});
  c.bindTooltip(`<b>${r.name}</b><br>${r.city}, ${r.state} · ${fm(r.assets_m)}<br>${PL(r.top_product)}`);c.on('click',()=>show(r.cu_number,true));c.addTo(layer)});
 $('tbl').tHead.innerHTML='<tr>'+HEAD.map(([l,k,n])=>`<th class="${n?'n':''}" data-k="${k||''}">${l}${k==sortK?(sortD<0?' ▼':' ▲'):''}</th>`).join('')+'</tr>';
 $('tbl').tBodies[0].innerHTML=f.slice(0,500).map((r,i)=>`<tr class="row ${r.cu_number==sel?'sel':''}" data-id="${r.cu_number}"><td>${i+1}</td><td>${r.relationship?'★ ':''}${r.name}</td><td>${r.city}</td><td>${r.state}</td><td class="n">${fm(r.assets_m)}</td><td><span class="pill" style="background:${COL[r.top_product]||'#9ca3af'}">${PL(r.top_product).split(' (')[0]}</span></td><td class="n">${fk(r.expected_value)}</td><td class="n">${r.priority??'—'}</td><td class="n">${pc(r.loan_to_share,0)}</td><td class="n">${pc(r.nw_ratio)}</td><td class="n">${pc(r.asset_growth_yoy)}</td></tr>`).join('');
 const by=(key,lab)=>{const g={};f.forEach(r=>{const k=r[key]||'—';g[k]=g[k]||{n:0,a:0,e:0,b:0};g[k].n++;g[k].a+=r.assets_m;g[k].e+=r.expected_value;if(r.assets_m>=1000)g[k].b++});
  return '<thead><tr><th>'+lab+'</th><th class="n">CUs</th><th class="n">≥$1B</th><th class="n">Assets</th><th class="n">Est. $/yr</th></tr></thead><tbody>'+Object.entries(g).sort((a,b)=>b[1].e-a[1].e).map(([k,v])=>`<tr><td>${key=='top_product'?PL(k):k}</td><td class="n">${v.n}</td><td class="n">${v.b}</td><td class="n">${fm(v.a)}</td><td class="n">${fk(v.e)}</td></tr>`).join('')+'</tbody>'};
 $('st').innerHTML=by('state','State');$('pt').innerHTML=by('top_product','Product');legend()}
function show(id,scroll){sel=id;const r=D.find(x=>x.cu_number==id);if(!r)return;
 const prods=P.map(k=>({k,fit:r['fit_'+k]||0,why:r['why_'+k],fee:r['fee_'+k]})).sort((a,b)=>b.fit-a.fit);
 $('detail').innerHTML=`<h2>Credit union detail</h2><h3>${r.name}</h3><div class="sub">${r.city}, ${r.state} · NCUA charter ${r.cu_number} · ${nf(r.members)} members · ${nf(r.employees)} staff</div>
 ${r.relationship?`<div class="rel">★ Known ALM First relationship: ${r.relationship} ${r.rel_url?`<a href="${r.rel_url}" target="_blank">source</a>`:''}. Treat as cross-sell.</div>`:''}
 <div class="metrics">${[['Total assets',fm(r.assets_m)],['Priority',r.priority??'—'],['Est. $/yr',fk(r.expected_value)],['Loan / share',pc(r.loan_to_share,0)],['Net worth',pc(r.nw_ratio)],['ROA',pc(r.roa,2)],['Liquidity',pc(r.liquid_pct)],['Investments / assets',pc(r.inv_pct)],['Long assets',pc(r.long_asset_pct)],['AFS loss / NW',pc(r.afs_loss_to_nw)],['Borrowings',pc(r.borrow_pct)],['Asset growth YoY',pc(r.asset_growth_yoy)],['Share growth YoY',pc(r.share_growth_yoy)],['Benefit-plan assets',r.emp_benefit_m?fm(r.emp_benefit_m):'—']].map(([l,v])=>`<div><span>${l}</span>${v}</div>`).join('')}</div>
 ${prods.map(p=>`<div class="prod"><b style="color:${COL[p.k]}">${PL(p.k)}</b> — fit ${p.fit} <span class="fit" style="width:${p.fit}px;background:${COL[p.k]}"></span> <span class="muted">· est. fee ${fk(p.fee)}</span>${p.why?'<ul>'+p.why.split('; ').map(w=>`<li>${w}</li>`).join('')+'</ul>':p.fit?'<div class="muted">Size fit only</div>':'<div class="muted">Outside the size gate</div>'}</div>`).join('')}
 <p><a target="_blank" href="https://mapping.ncua.gov/ResearchCreditUnion?charterNumber=${r.cu_number}">NCUA profile ↗</a> · <a target="_blank" href="https://www.google.com/search?q=${encodeURIComponent(r.name+' credit union '+r.city+' '+r.state)}">Search web ↗</a></p>`;
 if(r.lat!=null)map.setView([r.lat,r.lon],Math.max(map.getZoom(),8));render();if(scroll){const tr=document.querySelector(`tr[data-id="${id}"]`);tr&&tr.scrollIntoView({block:'center'})}}
$('rules').innerHTML=P.map(k=>{const p=M.products[k],g=p.gate;return `<details><summary style="color:${COL[k]}">${p.label}</summary><div class="muted">Size gate: ${g.min_assets_m?'$'+g.min_assets_m+'M':'any'} – ${g.max_assets_m?'$'+g.max_assets_m+'M':'no cap'} · base ${p.base} pts</div><ul>${p.signals.map(s=>`<li>+${s.points}: ${s.reason}</li>`).join('')}</ul></details>`}).join('')+'<p class="muted">Fit = base + signal points (max 100). Est. $/yr = Σ fit/100 × estimated fee per product.</p>';
document.addEventListener('click',e=>{const th=e.target.closest('th[data-k]');if(th&&th.dataset.k){const k=th.dataset.k;sortD=k==sortK?-sortD:-1;sortK=k;render()}const tr=e.target.closest('tr.row');if(tr)show(tr.dataset.id)});
['fState','fMin','fMax','fProd','fFit','fColor','fQ'].forEach(i=>$(i).addEventListener('input',render));
render();
</script></body></html>"""

if __name__ == "__main__":
    main()
