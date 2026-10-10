// 把「展开」导出成一个独立的 HTML 文件：按业务页面分节，每页一棵「谁打开谁」的树，
// 卡片是真实界面的静态快照（不是截图，文字能选），不带原型自己的脚本。
// 发给别人双击就能看，不需要原型工坊；要 PDF 就用浏览器「打印 → 存储为 PDF」。
import { buildTree, cardDocument, thumbFrame } from './probeTree.js'

// 树里的卡片要小：一页十几个视图横着排得下；看不清就点卡片放大
const PAGE_W = 300, MODAL_W = 320, MAX_H = 440
const esc = v => String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const clean = label => String(label || '').replace(/^表格行 · /, '')
const BODY = '\u0000PA_BODY\u0000'

// 哪些意见落在这张卡上：和展开视图里「已记 N」同一个口径，再按记下时所在的业务页面过滤
function notesFor(notes, route, node) {
  return notes.filter(a => (!a.view_route || a.view_route === route) &&
    (node.isPage ? !a.in_modal && !a.in_subpage : (a.in_modal || a.in_subpage) === node.title))
}

export function buildExpandExport({ projectName = '', fileName = '', version = '', routes = [], entries = {}, currentHash = '', notes = [], now = new Date() }) {
  // 有页面清单就按清单（侧栏顺序）；从没「一键展开」过就导出手上已有的
  const list = routes.length ? routes.map(r => ({ hash: r.hash, title: r.title }))
    : Object.keys(entries).map(hash => ({ hash, title: entries[hash]?.result?.title || hash || '当前页面' }))
  const styleSets = [], styleKey = new Map(), bodies = [], cards = []
  const styleOf = (styles, scroll) => {
    const key = JSON.stringify(styles || {}) + (scroll ? '|s' : '')
    if (!styleKey.has(key)) { const [a, b] = cardDocument(styles || {}, BODY, { scroll }).split(BODY); styleKey.set(key, styleSets.length); styleSets.push([a, b]) }
    return styleKey.get(key)
  }
  // 一张卡：只在导出文件里留个占位，打开时滚到附近才真正渲染，几十张卡也不卡
  function card(result, node, title) {
    const frame = { w: result.width || 1150, h: result.height || 800 }
    const pageLike = node.isPage || node.kind === 'subpage'
    const box = pageLike ? { x: 0, y: 0, w: frame.w, h: frame.h } : (node.box || { x: 0, y: 0, ...frame })
    const t = thumbFrame(box, pageLike ? PAGE_W : MODAL_W, MAX_H, 0.6)
    const i = cards.length
    bodies.push(node.html || '')
    cards.push({ s: styleOf(result.styles, pageLike), w: frame.w, h: frame.h, t: t.transform, b: [box.x, box.y, box.w, box.h], p: pageLike ? 1 : 0, n: title })
    const cut = Math.round(box.h * t.scale) > t.height
    return `<button type="button" class="thumb${cut ? ' cut' : ''}" style="width:${t.width}px;height:${t.height}px" data-card="${i}" title="点击放大查看"></button>`
  }
const kind = node => node.isPage ? '页面' : node.kind === 'subpage' ? '子页面' : '弹窗'
  // 横向树：页面在最左，从它的按钮出发一条条往右长；同一层的视图上下排，连线画在 CSS 里
  function block(route, result, node) {
    const own = notesFor(notes, route.hash, node)
    const head = `<header class="card-head"><span class="tag ${node.isPage ? 'page' : node.kind === 'subpage' ? 'sub' : 'modal'}">${kind(node)}</span><h3 title="${esc(node.title)}">${esc(node.title)}</h3>${own.length ? `<span class="badge">意见 ${own.length}</span>` : ''}</header>`
    const warn = node.stale ? '<p class="stale">按原路径已打不开，显示的是旧样子</p>' : ''
    const list = own.length ? `<ol class="notes">${own.map(a => `<li>${esc(a.note || '')}${a.text ? `<small>「${esc(String(a.text).slice(0, 30))}」</small>` : ''}</li>`).join('')}</ol>` : ''
    const edge = node.isPage ? '' : `<span class="edge" title="${esc(clean(node.label))}">${node.parent == null && /^表格行 · /.test(node.label || '') ? '<i>列表行</i>' : ''}${esc(clean(node.label))}</span>`
    const kids = (node.children || []).map(c => `<div class="kid">${block(route, result, c)}</div>`).join('')
    return `<div class="branch">${edge}<article class="card${node.isPage ? ' root' : ''}">${head}${card(result, node, node.title)}${warn}${list}</article>${kids ? `<div class="kids">${kids}</div>` : ''}</div>`
  }

  const sections = [], toc = [], side = []
  let total = 0, missing = 0
  list.forEach((route, i) => {
    const entry = entries[route.hash]
    const result = entry?.result
    if (!result?.styles) { missing++; toc.push(`<tr><td>${esc(route.title)}</td><td>—</td><td class="muted">未展开</td></tr>`); side.push(`<span class="off">${esc(route.title)}<em>未展开</em></span>`); return }
    const state = entry.partial ? '没展开完' : entry.hash !== currentHash ? '不是最新版本' : ''
    const nodes = result.nodes || []
    const views = nodes.length + 1
    total += views
    const pageNode = { id: 0, isPage: true, title: route.title, html: result.page, children: buildTree(nodes) }
    side.push(`<a href="#p${i}" data-sec="p${i}"${state ? ` title="${state}"` : ''}><span>${esc(route.title)}</span>${state ? '<i class="dot"></i>' : ''}<b>${views}</b></a>`)
    toc.push(`<tr><td><a href="#p${i}">${esc(route.title)}</a></td><td>${views}</td><td class="${state ? 'warn' : 'ok'}">${state || '已展开'}</td></tr>`)
    sections.push(`<section id="p${i}" class="route"><h2><button type="button" class="fold" aria-expanded="true" title="收起 / 展开这棵树">▾</button><span class="rt">${esc(route.title)}</span><small>${views} 个视图${route.hash ? ' · ' + esc(route.hash) : ''}${state ? ` · <b class="warn">${state}</b>` : ''}</small></h2><div class="tree">${block(route, result, pageNode)}</div></section>`)
  })

  const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  const title = `${projectName || '原型'} · 展开图`
  // 数据放进 JSON 脚本块：</script> 之类的字样要转义，否则会把外面的脚本提前截断
  const data = JSON.stringify({ styleSets, bodies, cards }).replace(/</g, '\\u003c')
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(title)}</title><style>${CSS}</style></head><body>
<header class="top"><div><p class="eyebrow">原型工坊 · 展开图</p><h1>${esc(projectName)}</h1><p class="meta">${esc(fileName)}${version ? ' · v' + esc(version) : ''} · 导出于 ${stamp} · ${sections.length} 个业务页面 · ${total} 个视图${missing ? ` · ${missing} 个页面未展开` : ''}</p></div><div class="top-actions"><button type="button" id="print">打印 / 存为 PDF</button></div></header>
<aside class="side" id="side" aria-label="目录"><div class="side-head"><b>目录</b><span>${sections.length} 页 · ${total} 视图</span><button type="button" id="side-close" title="收起目录" aria-label="收起目录">»</button></div><div class="side-search"><input id="q" type="search" autocomplete="off" placeholder="搜弹窗、按钮、字段名" aria-label="搜索视图"><span id="q-count" aria-live="polite"></span></div><div class="side-results" id="results" hidden></div><div class="side-tools"><button type="button" id="fold-all">全部收起</button><button type="button" id="unfold-all">全部展开</button></div><nav class="side-list">${side.join('')}</nav><p class="side-hint">点任意卡片放大查看；页面和子页面放大后能滚动。橙点表示导出时不是最新版本。</p></aside>
<button type="button" id="side-open" class="side-tab" title="展开目录" aria-label="展开目录">目录</button>
<main><nav class="toc"><h2>目录</h2><table><thead><tr><th>业务页面</th><th>视图</th><th>状态</th></tr></thead><tbody>${toc.join('')}</tbody></table><p class="hint">每个业务页面一棵树：最左是页面本身，往右是点了哪个按钮打开的弹窗 / 子页面，再往右是弹窗里继续点开的。点任意卡片放大查看，页面和子页面放大后可以滚动。卡片下的编号列表是当时记下、还没处理的修改意见。</p></nav>${sections.join('') || '<p class="empty">还没有展开过任何页面。</p>'}</main>
<script type="application/json" id="pa-data">${data}</script>
<script>${RUNTIME}</script></body></html>`
  return { html, pages: sections.length, views: total, missing }
}

const CSS = `
:root{--ink:#141413;--muted:#6f6e69;--line:#e5e2d6;--shell:#faf9f5;--canvas:#f0eee6;--primary:#b8532f;--soft:#f6e9e2;--warn:#8a5a0b;--wire:#d3ccbd}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.top{position:sticky;top:0;z-index:5;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 28px;background:var(--shell);border-bottom:1px solid var(--line)}
.eyebrow{margin:0;font-size:12px;color:var(--primary);font-weight:600}h1{margin:0;font-size:20px;line-height:1.4}.meta{margin:0;color:var(--muted);font-size:12.5px}
#print{flex-shrink:0;border:1px solid #e2ded3;background:#fff;border-radius:10px;padding:8px 14px;font:inherit;cursor:pointer}#print:hover{border-color:#c9c1b4}
main{padding:20px 28px 60px}
.toc{max-width:760px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin-bottom:28px}.toc h2{margin:0 0 8px;font-size:15px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:500}
td a{color:var(--ink)}td.ok{color:#4c7a52}td.warn,.warn{color:var(--warn)}td.muted{color:var(--muted)}.hint{margin:10px 0 0;font-size:12px;color:var(--muted)}
.route{margin:0 0 22px;background:#f7f5ef;border:1px solid var(--line);border-radius:14px}
.route h2{position:sticky;left:0;display:flex;align-items:baseline;gap:12px;margin:0;padding:14px 18px 0;font-size:17px}.route h2 small{font-size:12px;font-weight:400;color:var(--muted)}
.tree{overflow-x:auto;padding:16px 18px 20px}
/* 树：branch 一行 = [按钮][卡片][下一层]；kid 左边的竖线把兄弟串起来，横线接到自己的按钮上 */
.branch{display:flex;align-items:flex-start;width:max-content}
.kids{position:relative;display:flex;flex-direction:column;gap:18px;margin-left:30px}
.kids::before{content:'';position:absolute;left:-30px;top:22px;width:30px;border-top:2px solid var(--wire)}
.kid{position:relative;padding-left:26px}
.kid::before{content:'';position:absolute;left:0;top:22px;width:26px;border-top:2px solid var(--wire)}
.kid::after{content:'';position:absolute;left:0;top:-9px;bottom:-9px;border-left:2px solid var(--wire)}
.kid:first-child::after{top:22px}.kid:last-child::after{bottom:auto;top:-9px;height:31px}.kid:only-child::after{display:none}
.edge{flex-shrink:0;max-width:150px;margin:10px 8px 0 0;padding:2px 10px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;font-size:12px;line-height:20px;color:#55504a;background:#fff;border:1px solid var(--line);border-radius:20px}
.edge i{font-style:normal;color:var(--muted);margin-right:4px}
.card{flex-shrink:0;background:#fff;border:1px solid #dfddd5;border-radius:12px;overflow:hidden;box-shadow:0 1px 2px #2b33200a}
.card.root{border-color:#e4c9bc}
.card-head{display:flex;align-items:center;gap:7px;height:44px;padding:0 12px;border-bottom:1px solid var(--line)}.card-head h3{margin:0;font-size:13px;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tag{flex-shrink:0;font-size:11px;padding:1px 7px;border-radius:20px;background:#eef0f3;color:#55606e}.tag.page{background:var(--soft);color:var(--primary)}.tag.sub{background:#eef4ec;color:#4c7a52}
.badge{flex-shrink:0;font-size:11px;color:#fff;background:var(--primary);border-radius:20px;padding:1px 7px}
.thumb{position:relative;display:block;margin:10px;padding:0;overflow:hidden;border:0;border-radius:6px;background:#f5f7fa;box-shadow:0 1px 4px #2b33200f;cursor:zoom-in}
.thumb.cut::after{content:'点击看全部';position:absolute;left:0;right:0;bottom:0;padding:18px 0 6px;text-align:center;font-size:11px;color:var(--muted);background:linear-gradient(#fff0,#fffffff0)}
.thumb iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0;background:#fff;pointer-events:none}
.stale{margin:0 12px 8px;font-size:11.5px;color:var(--warn)}
.notes{max-width:340px;margin:0;padding:8px 12px 10px 30px;border-top:1px dashed var(--line);font-size:12px;background:#fffaf6}.notes li{margin:2px 0}.notes small{margin-left:4px;color:var(--muted)}
.empty{color:var(--muted)}
/* 搜索：命中的卡片描边，其余变淡；结果列表点一下跳过去 */
.side-search{position:relative;padding:10px 10px 6px}
.side-search input{width:100%;height:34px;padding:0 64px 0 12px;border:1px solid #ddd8cc;border-radius:9px;background:#fbfaf7;font:inherit;font-size:13px;color:var(--ink);outline:none}
.side-search input:focus{border-color:var(--primary);background:#fff;box-shadow:0 0 0 3px #b8532f1a}
#q-count{position:absolute;right:42px;top:17px;font-size:11.5px;color:var(--muted);pointer-events:none}
.side-results{flex:1;overflow:auto;padding:4px 6px 6px}
.side-results .res{display:block;width:100%;padding:7px 10px;border:0;border-radius:8px;background:transparent;text-align:left;font:inherit;cursor:pointer;color:var(--ink)}
.side-results .res:hover,.side-results .res.on{background:var(--soft)}
.res b{display:block;font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.res b mark{background:#f7d9c6;color:inherit;border-radius:2px}
.res small{display:block;font-size:11.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.res small em{font-style:normal;color:var(--primary)}
.side-results .none{padding:14px 10px;font-size:12.5px;color:var(--muted)}
body.searching .side-list{display:none}
body.searching .card{opacity:.32;transition:opacity .15s}body.searching .card.hit{opacity:1;border-color:var(--primary);box-shadow:0 0 0 2px #b8532f33}
.card.flash{animation:flash 1.4s ease}@keyframes flash{0%,40%{box-shadow:0 0 0 6px #b8532f55}100%{box-shadow:0 0 0 2px #b8532f33}}
/* 右侧目录：可收起，跟着滚动高亮当前页面；屏幕上代替顶部的目录表（目录表只在打印时出现） */
.toc{display:none}
.route{scroll-margin-top:96px}
.fold{width:24px;height:24px;margin-right:-4px;border:0;border-radius:6px;background:transparent;color:var(--muted);font-size:14px;line-height:1;cursor:pointer;transition:transform .15s}
.fold:hover{background:var(--canvas);color:var(--ink)}
.route.folded .fold{transform:rotate(-90deg)}.route.folded .tree{display:none}.route.folded h2{padding-bottom:14px}
.route h2{cursor:pointer;user-select:none}
.side-tools{display:flex;gap:6px;padding:2px 10px 6px}.side-tools button{flex:1;height:28px;border:1px solid var(--line);border-radius:8px;background:#fff;font:inherit;font-size:12px;color:var(--muted);cursor:pointer}.side-tools button:hover{color:var(--ink);border-color:#c9c1b4}
body.searching .side-tools{display:none}
.side-list a.folded span{color:var(--muted)}
body.side-on main{padding-right:300px}
.side{position:fixed;z-index:6;top:96px;right:16px;bottom:16px;width:264px;display:none;flex-direction:column;background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:0 8px 28px #2b332014;overflow:hidden}
body.side-on .side{display:flex}
.side-head{display:flex;align-items:center;gap:8px;padding:12px 10px 10px 16px;border-bottom:1px solid var(--line)}.side-head b{font-size:14px}.side-head span{flex:1;font-size:12px;color:var(--muted)}
.side-head button{width:28px;height:28px;border:0;border-radius:8px;background:transparent;color:var(--muted);font-size:16px;cursor:pointer}.side-head button:hover{background:var(--canvas);color:var(--ink)}
.side-list{flex:1;overflow:auto;padding:6px}
.side-list a,.side-list .off{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;font-size:13px;color:var(--ink);text-decoration:none}
.side-list a span{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.side-list a b{font-weight:500;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.side-list a:hover{background:var(--canvas)}.side-list a.on{background:var(--soft);color:var(--primary)}.side-list a.on b{color:var(--primary)}
.side-list .dot{width:7px;height:7px;border-radius:50%;background:#d9902f}
.side-list .off{color:var(--muted)}.side-list .off em{margin-left:auto;font-style:normal;font-size:11.5px}
.side-hint{margin:0;padding:10px 16px 12px;border-top:1px solid var(--line);font-size:11.5px;line-height:1.6;color:var(--muted)}
.side-tab{position:fixed;z-index:6;top:50%;right:0;transform:translateY(-50%);padding:12px 7px;border:1px solid var(--line);border-right:0;border-radius:10px 0 0 10px;background:#fff;color:var(--ink);font:inherit;font-size:13px;writing-mode:vertical-rl;letter-spacing:2px;cursor:pointer;box-shadow:-4px 4px 16px #2b332012}
.side-tab:hover{color:var(--primary)}body.side-on .side-tab{display:none}
@media (max-width:900px){body.side-on main{padding-right:28px}.side{top:auto;right:12px;left:12px;bottom:12px;width:auto;max-height:60vh}}
/* 放大查看 */
.zoom{position:fixed;inset:0;z-index:20;display:none;align-items:center;justify-content:center;padding:28px;background:#1a161299}
.zoom.open{display:flex}.zoom-box{position:relative;display:flex;flex-direction:column;max-width:100%;max-height:100%;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 20px 60px #0004}
.zoom-head{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid var(--line);font-weight:600}.zoom-head button{margin-left:auto;border:0;background:var(--canvas);border-radius:8px;padding:4px 10px;font:inherit;font-weight:400;cursor:pointer}
.zoom-stage{position:relative;overflow:hidden}.zoom-stage iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0;background:#fff}
@media (max-width:700px){main,.top{padding-left:14px;padding-right:14px}}
@page{size:A4 landscape;margin:12mm}
@media print{.top{position:static}#print,.zoom,.side,.side-tab,.fold{display:none!important}body.searching .card{opacity:1}.route.folded .tree{display:block}.toc{display:block}body.side-on main{padding-right:0}body{background:#fff}.card,.edge{break-inside:avoid}.route{break-before:page;border:0;background:#fff}.toc{break-after:page}.tree{overflow:visible}.thumb.cut::after{display:none}.thumb{cursor:auto}}
`

// 导出文件里唯一的脚本：滚到附近再把卡片渲染出来；打印前全部渲染好
const RUNTIME = `(()=>{const D=JSON.parse(document.getElementById('pa-data').textContent);
const doc=i=>{const c=D.cards[i],s=D.styleSets[c.s];return s[0]+D.bodies[i]+s[1]};
function frame(i,w,h,t){const f=document.createElement('iframe');f.setAttribute('sandbox','');f.title='界面快照';f.style.width=w+'px';f.style.height=h+'px';f.style.transform=t;f.srcdoc=doc(i);return f}
function show(el){if(el.firstChild)return;const i=+el.dataset.card,c=D.cards[i];el.appendChild(frame(i,c.w,c.h,c.t))}
const all=[...document.querySelectorAll('[data-card]')];
if('IntersectionObserver' in window){const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){show(e.target);io.unobserve(e.target)}}),{root:null,rootMargin:'600px'});all.forEach(el=>io.observe(el))}else all.forEach(show);
// 放大：弹窗按弹窗本身放到最大；页面 / 子页面按原尺寸铺满宽度，可以在里面滚动
const z=document.createElement('div');z.className='zoom';z.innerHTML='<div class="zoom-box"><div class="zoom-head"><span></span><button type="button">关闭 Esc</button></div><div class="zoom-stage"></div></div>';document.body.appendChild(z);
const close=()=>{z.classList.remove('open');z.querySelector('.zoom-stage').innerHTML=''};
z.addEventListener('click',e=>{if(e.target===z||e.target.closest('.zoom-head button'))close()});addEventListener('keydown',e=>{if(e.key==='Escape')close()});
document.addEventListener('click',e=>{const el=e.target.closest('[data-card]');if(!el)return;const i=+el.dataset.card,c=D.cards[i],[x,y,w,h]=c.b;
const maxW=innerWidth-56,maxH=innerHeight-56-46,stage=z.querySelector('.zoom-stage');stage.innerHTML='';z.querySelector('.zoom-head span').textContent=c.n;
if(c.p){const k=Math.min(1,maxW/c.w),f=frame(i,c.w,maxH/k,'scale('+k+')');stage.style.width=Math.round(c.w*k)+'px';stage.style.height=Math.round(maxH)+'px';stage.appendChild(f)}
else{const k=Math.min(1.2,maxW/w,maxH/h),f=frame(i,c.w,c.h,'translate('+(-x*k)+'px,'+(-y*k)+'px) scale('+k+')');stage.style.width=Math.round(w*k)+'px';stage.style.height=Math.round(h*k)+'px';stage.appendChild(f)}
z.classList.add('open')});
// 打印：先全部渲染；树太宽就整棵缩小到一页宽
const fit=()=>{all.forEach(show);document.querySelectorAll('.tree').forEach(t=>{t.style.zoom='';const k=Math.min(1,1040/t.scrollWidth);if(k<1)t.style.zoom=k})};
addEventListener('beforeprint',fit);addEventListener('afterprint',()=>document.querySelectorAll('.tree').forEach(t=>t.style.zoom=''));
// 右侧目录：记住收起 / 展开；滚动时高亮当前业务页面
const KEY='pa-expand-side',sideOn=v=>{document.body.classList.toggle('side-on',v);try{localStorage.setItem(KEY,v?'1':'0')}catch(e){}};
let saved=null;try{saved=localStorage.getItem(KEY)}catch(e){}
sideOn(saved?saved==='1':innerWidth>=1100);
document.getElementById('side-close').onclick=()=>sideOn(false);document.getElementById('side-open').onclick=()=>sideOn(true);
const links=new Map([...document.querySelectorAll('.side-list a[data-sec]')].map(a=>[a.dataset.sec,a]));
if('IntersectionObserver' in window){const spy=new IntersectionObserver(es=>es.forEach(e=>{if(!e.isIntersecting)return;links.forEach(a=>a.classList.remove('on'));const a=links.get(e.target.id);if(a){a.classList.add('on');a.scrollIntoView({block:'nearest'})}}),{rootMargin:'-120px 0px -65% 0px'});document.querySelectorAll('.route').forEach(r=>spy.observe(r))}
document.querySelectorAll('.side-list a').forEach(a=>a.addEventListener('click',()=>{if(innerWidth<900)sideOn(false)}));
// 折叠：每棵树单独收起；目录里收起的页面变灰，点它会先展开再跳过去
function fold(sec,v){if(!sec)return;sec.classList.toggle('folded',v);sec.querySelector('.fold').setAttribute('aria-expanded',String(!v));const a=links.get(sec.id);if(a)a.classList.toggle('folded',v)}
document.querySelectorAll('.route').forEach(sec=>sec.querySelector('h2').addEventListener('click',()=>fold(sec,!sec.classList.contains('folded'))));   // 点整行标题都能收起 / 展开
document.getElementById('fold-all').onclick=()=>document.querySelectorAll('.route').forEach(sec=>fold(sec,true));
document.getElementById('unfold-all').onclick=()=>document.querySelectorAll('.route').forEach(sec=>fold(sec,false));
links.forEach((a,id)=>a.addEventListener('click',()=>fold(document.getElementById(id),false)));
addEventListener('beforeprint',()=>document.querySelectorAll('.route.folded [data-card]').forEach(show));
// 搜索：按卡片名称 / 打开它的按钮 / 所在页面 / 意见 / 界面上的文字找，名字命中的排前面
const qi=document.getElementById('q'),qc=document.getElementById('q-count'),res=document.getElementById('results');
const idx=all.map(el=>{const art=el.closest('.card'),edge=art.parentElement.querySelector(':scope > .edge'),sec=el.closest('.route');
  return {el,art,i:+el.dataset.card,page:sec.querySelector('h2 .rt').textContent.trim(),title:D.cards[+el.dataset.card].n||'',edge:edge?edge.textContent.trim():'',kind:(art.querySelector('.tag')||{}).textContent||'',notes:((art.querySelector('.notes')||{}).textContent||'')}});
let bodyText=null;const plain=i=>{if(!bodyText)bodyText=D.bodies.map(h=>h.replace(/<(style|script)[\\s\\S]*?<\\/\\1>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&nbsp;|&#160;/g,' ').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&').replace(/\\s+/g,' '));return bodyText[i]};
const escH=t=>t.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const mark=(t,q)=>{const k=t.toLowerCase().indexOf(q);return k<0?escH(t):escH(t.slice(0,k))+'<mark>'+escH(t.slice(k,k+q.length))+'</mark>'+escH(t.slice(k+q.length))};
let hits=[],at=-1;
function jump(n){if(!hits.length)return;at=(n+hits.length)%hits.length;const h=hits[at];fold(h.el.closest('.route'),false);show(h.el);
  res.querySelectorAll('.res').forEach((b,k)=>b.classList.toggle('on',k===at));res.children[at]?.scrollIntoView({block:'nearest'});
  h.art.scrollIntoView({behavior:'smooth',block:'center',inline:'center'});h.art.classList.remove('flash');void h.art.offsetWidth;h.art.classList.add('flash');
  if(innerWidth<900)sideOn(false)}
function search(){const q=qi.value.trim().toLowerCase();document.querySelectorAll('.card.hit').forEach(a=>a.classList.remove('hit'));
  if(!q){document.body.classList.remove('searching');res.hidden=true;qc.textContent='';hits=[];at=-1;return}
  hits=idx.map(x=>{const name=(x.title+' '+x.edge+' '+x.page).toLowerCase().includes(q)?0:x.notes.toLowerCase().includes(q)?1:plain(x.i).toLowerCase().includes(q)?2:-1;return {...x,rank:name}}).filter(x=>x.rank>=0).sort((a,b)=>a.rank-b.rank);
  hits.forEach(h=>h.art.classList.add('hit'));document.body.classList.add('searching');res.hidden=false;at=-1;qc.textContent=hits.length?hits.length+' 个':'';
  const why=['','意见里提到','界面上有这几个字'];
  res.innerHTML=hits.length?hits.slice(0,80).map((h,k)=>'<button type="button" class="res" data-k="'+k+'"><b>'+mark(h.title,q)+'</b><small>'+(h.rank?'<em>'+why[h.rank]+'</em> · ':'')+escH(h.page)+(h.edge?' › 点「'+mark(h.edge,q)+'」':'')+'</small></button>').join(''):'<p class="none">没有找到。可以试试弹窗标题、按钮文字，或者界面上的字段名。</p>'}
let timer=0;qi.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(search,120)});
qi.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();jump(e.shiftKey?at-1:at+1)}if(e.key==='Escape'){qi.value='';search()}});
res.addEventListener('click',e=>{const b=e.target.closest('.res');if(b)jump(+b.dataset.k)});
// 按 / 直接开始搜（目录收起时会先打开）
addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement!==qi&&!e.metaKey&&!e.ctrlKey){e.preventDefault();sideOn(true);qi.focus()}});
document.getElementById('print').onclick=()=>{fit();const b=document.getElementById('print');b.textContent='准备中…';setTimeout(()=>{b.textContent='打印 / 存为 PDF';print()},1500)};})();`
