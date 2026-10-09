// 展开视图里和 DOM 无关的部分：卡片文档、树结构、缩略图取景、路径描述。
// 单独拿出来，是为了不开浏览器也能测。

const attr = value => String(value ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
const attrs = a => (a?.class ? ` class="${attr(a.class)}"` : '') + (a?.style ? ` style="${attr(a.style)}"` : '')

// 卡片是一张"静态快照"：带上原型的全部样式，但不带任何脚本。
// 动画、过渡关掉，否则拍下来的是淡入的第一帧（半透明、偏移）。
// scroll：放大编辑整页 / 子页面时要能滚到底，不能沿用缩略图的「只看第一屏」；滚动交给原型自己的样式决定，和预览一致
export function cardDocument(styles = {}, body = '', { pickable = false, scroll = false } = {}) {
  const base = /^https?:/i.test(styles.base || '') ? `<base href="${attr(styles.base)}">` : ''
  return '<!doctype html><html' + attrs(styles.html) + '><head><meta charset="utf-8">' + base + (styles.head || '') +
    '<style>' + (scroll ? '' : 'html,body{overflow:hidden!important}') + '*,*::before,*::after{animation:none!important;transition:none!important}' +
    (pickable ? '[data-pa-layer] *{cursor:crosshair!important}*{user-select:none!important;-webkit-user-select:none!important}' : '') + '</style>' +
    '</head><body' + attrs(styles.body) + '>' + body + (pickable ? '<script>' + CARD_SCRIPT + '</scr' + 'ipt>' : '') + '</body></html>'
}

// 卡片里的点选：只有这一小段脚本，原型自己的脚本一行都不跑。
// 点中的元素用「从弹窗这一层往下的路径」上报，宿主拼上这一层在真实页面里的选择器，
// 选中、交给 AI 改，跟在预览里点选走的是同一条路——改的是同一个文件。
// 卡片里的点选 / 拉框：只有这一小段脚本，原型自己的脚本一行都不跑。
// 选中的元素用「从这一层往下的路径」上报，宿主拼上这一层在真实页面里的选择器，
// 选中、交给 AI 改，跟在预览里点选走的是同一条路——改的是同一个文件。
export const CARD_SCRIPT = `(()=>{
const root=document.querySelector('[data-pa-layer]')||document.body;let picked=[],mode='select',drag=null;const boxes=[];
const mk=(c,bg)=>{const d=document.createElement('div');Object.assign(d.style,{position:'fixed',pointerEvents:'none',zIndex:2147483647,border:'2px solid '+c,borderRadius:'2px',boxSizing:'border-box',display:'none',background:bg||''});document.documentElement.appendChild(d);return d};
const hover=mk('#b8532f99'),band=mk('#b8532f','#b8532f12');
const own=t=>t instanceof Element&&root.contains(t)&&t!==root?t:null;
function rel(el){const parts=[];for(let n=el;n&&n!==root;n=n.parentElement){const p=n.parentElement,same=p?[...p.children].filter(c=>c.tagName===n.tagName):[];parts.unshift(n.tagName.toLowerCase()+(same.length>1?':nth-of-type('+(same.indexOf(n)+1)+')':''))}return parts.join(' > ')}
const KEYS=['color','background-color','font-size','border-radius','padding-top','padding-bottom','padding-left','padding-right','display'];
function info(el){const cs=getComputedStyle(el);return {rel:rel(el),tag:el.tagName.toLowerCase(),text:(el.innerText||el.value||el.getAttribute('placeholder')||'').trim().slice(0,500),outer_html:el.outerHTML.slice(0,5000),styles:Object.fromEntries(KEYS.map(k=>[k,cs.getPropertyValue(k)]))}}
function place(b,el){if(!el){b.style.display='none';return}const r=el.getBoundingClientRect();Object.assign(b.style,{display:'block',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'})}
function paint(){while(boxes.length<picked.length)boxes.push(mk('#b8532f','#b8532f14'));boxes.forEach((b,i)=>place(b,picked[i]))}
function report(add){paint();parent.postMessage({source:'pa-card',type:'CARD_PICK',items:picked.map(info),additive:add},'*')}
addEventListener('pointermove',e=>{if(drag){const x=Math.min(drag.x,e.clientX),y=Math.min(drag.y,e.clientY);Object.assign(band.style,{display:'block',left:x+'px',top:y+'px',width:Math.abs(e.clientX-drag.x)+'px',height:Math.abs(e.clientY-drag.y)+'px'});return}place(hover,mode==='select'?own(e.target):null)},true);
document.addEventListener('mouseleave',()=>place(hover,null));
let scrollTimer=0;addEventListener('scroll',e=>{paint();place(hover,null);const t=e.target===document?document.scrollingElement:e.target;if(!(t instanceof Element))return;clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>parent.postMessage({source:'pa-card',type:'CARD_SCROLL',at:[...document.querySelectorAll('*')].indexOf(t),top:t.scrollTop,left:t.scrollLeft},'*'),120)},true);
addEventListener('pointerdown',e=>{e.preventDefault();if(mode==='box'&&e.button===0){drag={x:e.clientX,y:e.clientY};place(hover,null)}},true);
addEventListener('pointerup',e=>{if(!drag)return;const r={l:Math.min(drag.x,e.clientX),t:Math.min(drag.y,e.clientY),r:Math.max(drag.x,e.clientX),b:Math.max(drag.y,e.clientY)};drag=null;band.style.display='none';
if(r.r-r.l<6||r.b-r.t<6)return;
const hit=[...root.querySelectorAll('button,a,input,select,textarea,h1,h2,h3,h4,h5,p,label,th,td,span,li,img')].filter(el=>{const b=el.getBoundingClientRect(),x=b.left+b.width/2,y=b.top+b.height/2;if(!b.width||!b.height||x<r.l||x>r.r||y<r.t||y>r.b)return false;const top=document.elementFromPoint(x,y);return !!top&&(top===el||el.contains(top)||top.contains(el))});
picked=hit.filter(el=>!hit.some(n=>n!==el&&el.contains(n))).slice(0,16);if(picked.length)report(true)},true);
addEventListener('click',e=>{e.preventDefault();e.stopPropagation();if(mode==='box')return;const el=own(e.target);if(!el)return;const add=e.shiftKey||e.metaKey||e.ctrlKey;
if(add){const i=picked.indexOf(el);i>=0?picked.splice(i,1):picked.length<16&&picked.push(el)}else picked=[el];report(add)},true);
for(const t of ['mousedown','submit','dblclick','dragstart'])addEventListener(t,e=>e.preventDefault(),true);
addEventListener('message',e=>{const m=e.data||{};
if(m.type==='CARD_MODE'){mode=m.mode==='box'?'box':'select';document.documentElement.style.cursor=mode==='box'?'crosshair':'';place(hover,null)}
if(m.type==='CARD_PATCH'){if(String(m.prop).startsWith('--'))document.documentElement.style.setProperty(m.prop,m.value);else (m.rels||[]).map(r=>{try{return root.querySelector(':scope > '+r)}catch{return null}}).filter(Boolean).forEach(el=>{if(m.prop==='text')el.textContent=m.value;else el.style.setProperty(m.prop,m.value,'important')});paint()}
if(m.type==='CARD_SCROLL_TO'){const t=document.querySelectorAll('*')[m.at];if(t){t.scrollTop=m.top;t.scrollLeft=m.left}}
if(m.type==='CARD_SHOW'){picked=(m.rels||[]).map(r=>{try{return root.querySelector(':scope > '+r)}catch{return null}}).filter(Boolean);paint();if(m.reveal&&picked[0])picked[0].scrollIntoView({block:'nearest'})}});
})();`

// 卡片里点中的元素 → 和预览里点选一样的选中数据。
// 弹窗卡片：layerSel 是这一层在真实页面里的选择器；页面卡片：从 body 往下的路径。
export function pickToSelection(node, items = [], pageTitle = '') {
  // 子页面（列表点进去的详情）和页面本身一样是整页快照，选择器从 body 往下
  const pageLike = node.isPage || node.kind === 'subpage'
  const prefix = pageLike ? 'body' : node.layerSel
  const modal = pageLike ? '' : node.title
  const place = node.isPage ? pageTitle : `${pageTitle} › ${node.title}`
  // 样式是卡片里实际算出来的（同一套 CSS），属性面板据此显示真实字号、边距；读不到的留空，不当成 0
  const one = item => ({
    selector: prefix ? `${prefix} > ${item.rel}` : item.rel,
    pid: '', tag: item.tag, text: item.text, outer_html: item.outer_html, styles: item.styles || {}, modal,
  })
  const card = { nodeId: node.id, rels: items.map(i => i.rel) }
  const viewKind = node.isPage ? 'page' : node.kind === 'subpage' ? 'subpage' : 'modal'
  if (items.length === 1) return { ...one(items[0]), card, place, viewTitle: node.title, viewKind, pageTitle }
  const targets = items.map(one)
  return { selector: prefix || targets[0]?.selector || '', pid: '', tag: 'div', kind: 'region', modal,
    text: targets.map(t => t.text || t.tag).join(' · ').slice(0, 500), outer_html: targets[0]?.outer_html || '', styles: {}, targets, card, place, viewTitle: node.title, viewKind, pageTitle }
}

// 卡片按「从哪儿打开的」分组：页面上的按钮、表格某一行的操作、弹窗里点下一步打开的
export const ORIGIN_LABEL = { page: '页面本身', button: '页面按钮', row: '列表操作', step: '弹窗里的下一步', subpage: '子页面' }
export function originOf(node) {
  if (node.isPage) return 'page'
  if (node.parent != null) return 'step'
  return /^表格行 · /.test(node.label || '') ? 'row' : 'button'
}
// 卡片上那一行来源：「列表行 → 设为当前版本」「页面按钮 → 新增因子 → 下一步 · 运输因子」
export function crumbOf(nodes = [], node) {
  if (node.isPage) return '当前页面'
  const byId = new Map(nodes.map(n => [n.id, n]))
  let root = node
  for (let guard = 0; root.parent != null && byId.has(root.parent) && guard < 10; guard++) root = byId.get(root.parent)
  const head = /^表格行 · /.test(root.label || '') ? '列表行' : '页面按钮'
  return [head, ...trailOf(nodes, node).split(' › ').map(s => s.replace(/^表格行 · /, ''))].join(' → ')
}

export function buildTree(nodes = []) {
  const byId = new Map(nodes.map(n => [n.id, { ...n, children: [] }]))
  const roots = []
  for (const node of byId.values()) (node.parent != null && byId.has(node.parent) ? byId.get(node.parent).children : roots).push(node)
  return roots
}

// 只框住弹窗本体：按卡片宽度缩放，太高的截断。放大不超过 0.6，免得小弹窗糊成一团。
export function thumbFrame(box, cardWidth = 260, maxHeight = 210, maxScale = 0.6) {
  const w = Math.max(1, box?.w || 1), h = Math.max(1, box?.h || 1)
  const scale = Math.min(cardWidth / w, maxScale)
  return {
    scale,
    width: Math.round(w * scale),
    height: Math.min(Math.round(h * scale), maxHeight),
    transform: `translate(${-(box?.x || 0) * scale}px, ${-(box?.y || 0) * scale}px) scale(${scale})`,
  }
}

// 「新增因子 › 下一步 · 运输因子」：从顶层走到这个节点要点的按钮。
export function trailOf(nodes = [], node) {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const parts = []
  for (let at = node, guard = 0; at && guard < 10; at = byId.get(at.parent), guard++) parts.unshift(at.label)
  return parts.join(' › ')
}

// 进度条上那一行字：太长的按钮文字截一下
export function shortLabel(label = '', max = 14) {
  const text = String(label).replace(/^表格行 · /, '')
  return text.length > max ? text.slice(0, max) + '…' : text
}

// 从顶层到这个节点经过哪些节点：折叠的分支要先把这一路展开，才能定位过去
export function ancestorsOf(nodes = [], id) {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const out = []
  for (let at = byId.get(id), guard = 0; at && at.parent != null && guard < 10; at = byId.get(at.parent), guard++) out.unshift(at.parent)
  return out
}
