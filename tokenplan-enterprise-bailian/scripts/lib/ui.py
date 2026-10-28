#!/usr/bin/env python3
"""Shared CSS/JS for the department + group reports."""
CSS = r"""
:root{
  --ink:#0a0b0d; --ink2:#101216; --panel:#14171c; --panel2:#191d23;
  --line:#252a32; --line2:#343b45;
  --tx:#e9e5db; --dim:#8d887e; --dim2:#5f5b54;
  --amber:#e8b44a; --ember:#ff7a45; --sea:#5fc9a5; --sky:#7aa7d8; --violet:#c792ea;
  --serif:"Iowan Old Style","Hoefler Text","Songti SC","Noto Serif CJK SC",Georgia,serif;
  --sans:"Avenir Next",Avenir,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --r:3px; --accent:var(--amber);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  margin:0;background:var(--ink);color:var(--tx);font-family:var(--sans);
  font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased;
  background-image:
    radial-gradient(1100px 600px at 82% -8%, color-mix(in srgb, var(--accent) 12%, transparent), transparent 62%),
    radial-gradient(900px 500px at 4% 4%, rgba(122,167,216,.06), transparent 60%),
    repeating-linear-gradient(0deg, rgba(255,255,255,.022) 0 1px, transparent 1px 64px);
}
body::after{
  content:"";position:fixed;inset:0;pointer-events:none;z-index:9;opacity:.28;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)' opacity='.35'/%3E%3C/svg%3E");
}
.wrap{max-width:1240px;margin:0 auto;padding:0 28px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.dim{color:var(--dim2)}
.strong{color:var(--accent)}

header.mast{padding:64px 0 32px;border-bottom:1px solid var(--line)}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.2em;text-transform:uppercase;
  color:var(--dim);display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:24px}
.eyebrow b{color:var(--accent);font-weight:500}
.eyebrow .dot{width:5px;height:5px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px var(--accent)}
h1{font-family:var(--serif);font-weight:400;letter-spacing:-.02em;line-height:1.04;
  font-size:clamp(38px,6vw,76px);margin:0 0 6px}
h1 em{font-style:italic;color:var(--accent)}
h1 .arrow{font-family:var(--mono);font-size:.52em;vertical-align:.18em;color:var(--dim);margin:0 .12em}
.lede{max-width:66ch;color:var(--dim);font-size:15.5px;margin:16px 0 0}
.lede b{color:var(--tx);font-weight:500}

.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:0;margin-top:34px;border-top:1px solid var(--line)}
.stat{padding:18px 20px 4px 0;border-right:1px solid var(--line)}
.stat:last-child{border-right:0}
.stat .k{font-family:var(--mono);font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--dim2)}
.stat .v{font-family:var(--mono);font-size:clamp(20px,2.3vw,29px);letter-spacing:-.02em;margin-top:6px;line-height:1.15}
.stat .v small{font-size:.44em;letter-spacing:.06em;color:var(--dim);margin-left:5px;font-family:var(--sans)}
.stat .v .slash{color:var(--dim2);font-size:.72em;margin:0 .1em;vertical-align:.06em}

nav.toc{position:sticky;top:0;z-index:8;background:rgba(10,11,13,.9);backdrop-filter:blur(14px);
  border-bottom:1px solid var(--line)}
nav.toc .wrap{display:flex;gap:4px;overflow-x:auto;padding-top:0;padding-bottom:0;scrollbar-width:none}
nav.toc .wrap::-webkit-scrollbar{display:none}
nav.toc a{font-size:12.5px;color:var(--dim);padding:13px 11px 12px;white-space:nowrap;
  border-bottom:2px solid transparent;transition:color .2s,border-color .2s}
nav.toc a:hover,nav.toc a.on{color:var(--tx);border-bottom-color:var(--accent);text-decoration:none}

section{padding:54px 0;border-bottom:1px solid var(--line);scroll-margin-top:52px}
.sec-head{display:flex;align-items:baseline;gap:15px;margin-bottom:8px;flex-wrap:wrap}
.sec-num{font-family:var(--mono);font-size:11px;color:var(--accent);letter-spacing:.16em}
h2{font-family:var(--serif);font-weight:400;font-size:clamp(23px,2.9vw,33px);margin:0;letter-spacing:-.01em}
.sec-note{color:var(--dim);max-width:76ch;margin:10px 0 24px;font-size:14.3px}
.sec-note b{color:var(--tx);font-weight:500}
code.hint{font-family:var(--mono);font-size:12px;color:var(--sky);background:rgba(122,167,216,.08);
  padding:1px 5px;border-radius:2px}

.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:0 0 16px}
input.search{background:var(--panel);border:1px solid var(--line2);color:var(--tx);border-radius:var(--r);
  padding:9px 13px;font-family:var(--mono);font-size:12.5px;min-width:220px;outline:none;transition:border-color .2s}
input.search:focus{border-color:var(--accent)}
input.search::placeholder{color:var(--dim2)}
.seg{display:inline-flex;border:1px solid var(--line2);border-radius:var(--r);overflow:hidden}
.seg button{background:transparent;border:0;color:var(--dim);font-family:var(--mono);font-size:12px;
  padding:9px 14px;cursor:pointer;transition:.18s;letter-spacing:.03em}
.seg button+button{border-left:1px solid var(--line2)}
.seg button[aria-pressed="true"]{background:var(--accent);color:#141005;font-weight:600}
.seg button:hover:not([aria-pressed="true"]){color:var(--tx);background:var(--panel2)}
.hint{font-size:12px;color:var(--dim2);font-family:var(--mono)}

.tbl-wrap{border:1px solid var(--line);border-radius:var(--r);overflow:auto;max-height:74vh;background:var(--panel);
  scrollbar-width:thin;scrollbar-color:#3a414c transparent}
.tbl-wrap::-webkit-scrollbar{width:9px;height:9px}
.tbl-wrap::-webkit-scrollbar-thumb{background:#2f353f;border-radius:9px;border:2px solid var(--panel)}
.tbl-wrap::-webkit-scrollbar-thumb:hover{background:#454d59}
.tbl-wrap::-webkit-scrollbar-track{background:transparent}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:13.3px}
thead th{position:sticky;top:0;z-index:2;background:var(--panel2);text-align:right;
  font-family:var(--mono);font-size:10px;letter-spacing:.11em;text-transform:uppercase;color:var(--dim);
  padding:12px 13px;border-bottom:1px solid var(--line2);white-space:nowrap;font-weight:500}
thead th:nth-child(-n+3),thead th.l{text-align:left}
tbody td{padding:10px 13px;border-bottom:1px solid rgba(255,255,255,.045);text-align:right;white-space:nowrap}
tbody td.l,tbody td:nth-child(-n+3){text-align:left}
tbody tr{transition:background .16s}
tbody tr:hover{background:color-mix(in srgb, var(--accent) 7%, transparent)}
tbody tr:hover td:first-child{box-shadow:inset 2px 0 0 var(--accent)}
td.m{font-family:var(--serif);font-size:14.5px;color:var(--tx)}
td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.ctx{font-family:var(--mono);font-size:11px;color:var(--sky);border:1px solid rgba(122,167,216,.3);
  background:rgba(122,167,216,.08);padding:2px 6px;border-radius:2px}
.chip{font-family:var(--mono);font-size:9.5px;letter-spacing:.09em;padding:3px 6px;border-radius:2px;border:1px solid;white-space:nowrap}
.chip.peak{color:var(--ember);border-color:rgba(255,122,69,.35);background:rgba(255,122,69,.09)}
.chip.offpeak{color:var(--sea);border-color:rgba(95,201,165,.35);background:rgba(95,201,165,.09)}
.chip.flat{color:var(--dim);border-color:var(--line2);background:rgba(255,255,255,.03)}
.chip.full{color:var(--ember);border-color:rgba(255,122,69,.4);background:rgba(255,122,69,.1)}
.chip.warn{color:var(--amber);border-color:rgba(232,180,74,.4);background:rgba(232,180,74,.1)}
.chip.ok{color:var(--sea);border-color:rgba(95,201,165,.35);background:rgba(95,201,165,.08)}
.chip.none{color:var(--dim2);border-color:var(--line);background:rgba(255,255,255,.02)}

.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.grid2{display:grid;grid-template-columns:1.02fr .98fr;gap:26px;align-items:start}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);padding:20px 21px 18px;position:relative;overflow:hidden}
.card::before{content:"";position:absolute;left:0;top:0;width:100%;height:2px;background:var(--line2)}
.card.hot::before{background:var(--ember)}
.card.cool::before{background:var(--sea)}
.card.warm::before{background:var(--amber)}
.card h3{margin:0 0 7px;font-family:var(--sans);font-size:14px;font-weight:600}
.card p{margin:0;color:var(--dim);font-size:13.4px;line-height:1.7}
.card .big{font-family:var(--mono);font-size:25px;color:var(--tx);display:block;margin:2px 0 9px}
.card .big span{font-size:.48em;color:var(--dim);margin-left:6px}

.chart{display:flex;align-items:flex-end;gap:6px;height:220px;padding:24px 4px 28px;border-bottom:1px solid var(--line)}
.bar-wrap{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%;position:relative}
.bar{width:100%;max-width:44px;background:linear-gradient(180deg,var(--accent),color-mix(in srgb, var(--accent) 25%, transparent));
  border-radius:1px 1px 0 0;transition:filter .2s;transform-origin:bottom}
.bar-wrap:hover .bar{filter:brightness(1.35)}
.bar-v{position:absolute;top:-18px;left:50%;transform:translateX(-50%);font-family:var(--mono);
  font-size:9.5px;color:var(--dim2);opacity:0;transition:opacity .2s;white-space:nowrap}
.bar-wrap:hover .bar-v{opacity:1}
.bar-x{position:absolute;bottom:-22px;font-family:var(--mono);font-size:10px;color:var(--dim2)}
.chart-foot{display:flex;gap:24px;margin-top:12px;font-family:var(--mono);font-size:11.5px;color:var(--dim2)}
.chart-foot b{color:var(--tx);font-weight:400}

.rank{display:grid;gap:8px;margin-top:6px}
.rank-row{display:grid;grid-template-columns:120px 1fr 96px 52px;gap:11px;align-items:center;font-size:13px}
.rank-name{font-family:var(--serif);font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rank-track{height:7px;background:rgba(255,255,255,.05);border-radius:1px;overflow:hidden}
.rank-fill{display:block;height:100%;background:linear-gradient(90deg,color-mix(in srgb, var(--accent) 42%, transparent),var(--accent))}
.rank-val{font-family:var(--mono);text-align:right}
.rank-pct{font-family:var(--mono);text-align:right;color:var(--dim2);font-size:11.5px}

.kv{display:grid;grid-template-columns:200px 1fr;gap:0;border-top:1px solid var(--line);margin-top:8px}
.kv div{padding:11px 14px;border-bottom:1px solid rgba(255,255,255,.045);font-size:13.5px}
.kv div:nth-child(odd){font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--dim);text-transform:uppercase}

.files{display:grid;gap:9px;margin-top:16px}
.file{display:flex;gap:14px;align-items:baseline;padding:12px 15px;border:1px solid var(--line);
  border-radius:var(--r);background:var(--panel);transition:border-color .2s,transform .2s}
.file:hover{border-color:var(--line2);transform:translateX(3px)}
.file .ext{font-family:var(--mono);font-size:10px;letter-spacing:.1em;color:var(--accent);min-width:40px}
.file .nm{font-family:var(--mono);font-size:12.8px;color:var(--tx)}
.file .ds{color:var(--dim);font-size:12.4px;margin-left:auto;text-align:right}

.bars-stack{display:flex;height:8px;border-radius:1px;overflow:hidden;background:rgba(255,255,255,.05)}
.bars-stack i{display:block;height:100%}
.lg{display:flex;gap:16px;flex-wrap:wrap;margin-top:9px;font-family:var(--mono);font-size:11px;color:var(--dim)}
.lg span i{display:inline-block;width:8px;height:8px;border-radius:1px;margin-right:5px;vertical-align:middle}

.matrix{width:100%;border-collapse:separate;border-spacing:2px;font-size:12px}
.matrix th{font-family:var(--mono);font-size:10px;letter-spacing:.06em;color:var(--dim);padding:6px 8px;
  text-transform:uppercase;font-weight:500;text-align:right;white-space:nowrap}
.matrix th:first-child{text-align:left}
.matrix td{font-family:var(--mono);padding:8px;text-align:right;border-radius:2px;color:var(--tx)}
.matrix td:first-child{font-family:var(--serif);text-align:left;font-size:13.5px;color:var(--tx);background:none!important}
.matrix td.z{color:var(--dim2)}
.shared{display:inline-block;margin-left:6px;font-family:var(--mono);font-size:9px;letter-spacing:.06em;
  color:var(--sky);border:1px solid rgba(122,167,216,.32);background:rgba(122,167,216,.08);
  padding:1px 5px;border-radius:2px;vertical-align:1px}
tbody tr.hl{background:color-mix(in srgb, var(--ember) 6%, transparent)}
tbody tr.hl td:first-child{box-shadow:inset 2px 0 0 var(--ember)}
.panel-warn{border:1px solid rgba(255,122,69,.3);background:rgba(255,122,69,.05);border-radius:var(--r);padding:18px 20px;margin-top:20px}
.panel-ok{border:1px solid rgba(95,201,165,.28);background:rgba(95,201,165,.05);border-radius:var(--r);padding:16px 20px;margin-top:20px}
.pw-head{display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap}
.pw-k{font-size:13.5px;font-weight:600;color:var(--tx)}
.pw-v{font-family:var(--mono);font-size:22px;color:var(--ember)}
.pw-note{margin:8px 0 0;font-size:12.8px;color:var(--dim);line-height:1.7}
.pr{display:grid;grid-template-columns:220px 1fr 64px 1fr 64px;gap:10px;align-items:center;
  padding:7px 2px;border-bottom:1px solid rgba(255,255,255,.045)}
.pr:hover{background:color-mix(in srgb,var(--accent) 5%,transparent)}
.pr .pn{font-family:var(--serif);font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pr .pt{height:8px;background:rgba(255,255,255,.05);border-radius:1px;overflow:hidden}
.pr .pt i{display:block;height:100%;border-radius:1px}
.pr .pv{font-family:var(--mono);font-size:12px;text-align:right;font-variant-numeric:tabular-nums}
.pr-h{display:grid;grid-template-columns:220px 1fr 64px 1fr 64px;gap:10px;padding:0 2px 8px;
  border-bottom:1px solid var(--line);font-family:var(--mono);font-size:10px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--dim2)}
@media (max-width:920px){.pr,.pr-h{grid-template-columns:118px 1fr 50px 1fr 50px;gap:6px}}

/* ---- 热力网格（7×24 / 人×24 / 日×24 通用） ---- */
.heat{display:grid;grid-template-columns:var(--roww,64px) repeat(var(--cols,24),var(--cell,15px));
  gap:var(--gap,2px);align-items:stretch;font-family:var(--mono);overflow-x:auto;padding-bottom:4px}
.heat>.hgl{font-size:10.5px;color:var(--dim);white-space:nowrap;align-self:center;padding-right:6px;text-align:right}
.heat>.hgl.hx{border:0}
.heat>.hgx{font-size:9px;color:var(--dim2);text-align:center;align-self:end;padding-bottom:2px}
.heat>.hgx.b{color:var(--dim)}
.heat>i{display:block;height:var(--cell,15px);border-radius:1px;min-width:var(--cell,15px)}
.heat-wrap{margin:14px 0 6px}
.heat-cap{font-family:var(--mono);font-size:10.5px;letter-spacing:.08em;color:var(--dim2);text-transform:uppercase;margin-bottom:8px}

/* ---- 24h 细柱 ---- */
.hbars{display:grid;align-items:stretch;gap:3px;border-bottom:1px solid var(--line)}
.hbars .hcol{position:relative;height:100%}
.hbars .hcol i{position:absolute;bottom:0;left:0;width:100%;border-radius:1px 1px 0 0;transition:filter .2s}
.hbars .hcol:hover i{filter:brightness(1.45)}
.haxis{display:grid;gap:3px;font-family:var(--mono);font-size:9px;color:var(--dim2);margin-top:5px;text-align:center}
.haxis .b{color:var(--dim);font-weight:400}

/* ---- 分位条 ---- */
.pctx{display:grid;grid-template-columns:170px 1fr 110px 52px;gap:12px;align-items:center;
  padding:9px 2px;border-bottom:1px solid rgba(255,255,255,.045)}
.pctx:hover{background:color-mix(in srgb,var(--accent) 5%,transparent)}
.pctx .pn{font-family:var(--serif);font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pctx .pt{position:relative;height:8px;background:rgba(255,255,255,.05);border-radius:1px;overflow:visible}
.pctx .pt i{display:block;height:100%;border-radius:1px}
.pctx .pt i.mk{position:absolute;top:-3px;width:2px;height:14px;background:var(--tx);border-radius:0}
.pctx .pv{font-family:var(--mono);font-size:12px;text-align:right;font-variant-numeric:tabular-nums}

@media (max-width:920px){.pctx{grid-template-columns:110px 1fr 84px 42px;gap:7px}}

footer{padding:38px 0 66px;color:var(--dim2);font-size:12.4px;font-family:var(--mono);letter-spacing:.04em}
footer .wrap{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}

.rv{opacity:0;transform:translateY(14px);transition:opacity .7s cubic-bezier(.2,.7,.3,1),transform .7s cubic-bezier(.2,.7,.3,1)}
.rv.in{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){.rv{opacity:1;transform:none;transition:none}html{scroll-behavior:auto}}

@media (max-width:920px){
  .stats{grid-template-columns:repeat(2,1fr)}
  .stat:nth-child(2n){border-right:0}
  .grid3,.grid2{grid-template-columns:1fr}
  .rank-row{grid-template-columns:96px 1fr 84px 44px}
  .kv{grid-template-columns:130px 1fr}
  header.mast{padding-top:42px}
  .wrap{padding:0 18px}
}
@media print{
  body{background:#fff;color:#111}
  body::after,nav.toc{display:none}
  .tbl-wrap{max-height:none;border-color:#ccc}
  thead th{background:#eee;color:#333}
  section{page-break-inside:avoid}
  .card,.file{background:#fff;border-color:#ddd}
}
"""

JS = r"""
(function(){
  const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}})},{threshold:.1});
  document.querySelectorAll('.rv').forEach(el=>io.observe(el));
  const links=[...document.querySelectorAll('nav.toc a')];
  const secs=links.map(a=>document.querySelector(a.getAttribute('href'))).filter(Boolean);
  if(secs.length){
    const spy=new IntersectionObserver(es=>{es.forEach(e=>{
      if(e.isIntersecting) links.forEach(a=>a.classList.toggle('on',a.getAttribute('href')==='#'+e.target.id));
    })},{rootMargin:'-18% 0px -70% 0px'});
    secs.forEach(s=>spy.observe(s));
  }
  const q=document.getElementById('q');
  if(q){
    const rows=[...document.querySelectorAll('[data-filterable] tbody tr')];
    const cnt=document.getElementById('cnt');
    const f=()=>{const v=q.value.trim().toLowerCase();let n=0;
      rows.forEach(tr=>{const hit=!v||tr.innerText.toLowerCase().includes(v);tr.style.display=hit?'':'none';if(hit)n++;});
      if(cnt)cnt.textContent=n+' / '+rows.length+' 行';};
    q.addEventListener('input',f);f();
  }
  /* 通用：带 data-target 的搜索框只过滤本节内指定表格；缺省过滤本节第一个可过滤表格 */
  document.querySelectorAll('input.search[data-target]').forEach(inp=>{
    const scope=inp.closest('section')||document;
    const wrap=scope.querySelector(inp.dataset.target);
    if(!wrap)return;
    const rows=[...wrap.querySelectorAll('tbody tr')];
    const cnt=inp.parentElement.querySelector('.hint');
    const f=()=>{const v=inp.value.trim().toLowerCase();let n=0;
      rows.forEach(tr=>{const hit=!v||tr.innerText.toLowerCase().includes(v);tr.style.display=hit?'':'none';if(hit)n++;});
      if(cnt)cnt.textContent=n+' / '+rows.length+' 行';};
    inp.addEventListener('input',f);f();
  });
  const u1=document.getElementById('u1'),u2=document.getElementById('u2');
  if(u1&&u2){
    const set=m=>{u1.setAttribute('aria-pressed',m==='c');u2.setAttribute('aria-pressed',m==='t');
      document.querySelectorAll('[data-c]').forEach(el=>{
        el.textContent = m==='c' ? Number(el.dataset.c).toLocaleString('en-US',{maximumFractionDigits:2})
                                 : el.dataset.i;});
    };
    u1.addEventListener('click',()=>set('c'));u2.addEventListener('click',()=>set('t'));
  }
})();
"""