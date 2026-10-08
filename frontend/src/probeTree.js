// 展开视图里和 DOM 无关的部分：卡片文档、树结构、缩略图取景、路径描述。
// 单独拿出来，是为了不开浏览器也能测。

const attr = value => String(value ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
const attrs = a => (a?.class ? ` class="${attr(a.class)}"` : '') + (a?.style ? ` style="${attr(a.style)}"` : '')

// 卡片是一张"静态快照"：带上原型的全部样式，但不带任何脚本。
// 动画、过渡关掉，否则拍下来的是淡入的第一帧（半透明、偏移）。
export function cardDocument(styles = {}, body = '', { pickable = false } = {}) {
  const base = /^https?:/i.test(styles.base || '') ? `<base href="${attr(styles.base)}">` : ''
  return '<!doctype html><html' + attrs(styles.html) + '><head><meta charset="utf-8">' + base + (styles.head || '') +
    '<style>html,body{overflow:hidden!important}*,*::before,*::after{animation:none!important;transition:none!important}' +
    (pickable ? '[data-pa-layer] *{cursor:crosshair!important}' : '') + '</style>' +
    '</head><body' + attrs(styles.body) + '>' + body + (pickable ? '<script>' + CARD_SCRIPT + '</scr' + 'ipt>' : '') + '</body></html>'
}

// 卡片里的点选：只有这一小段脚本，原型自己的脚本一行都不跑。
// 点中的元素用「从弹窗这一层往下的路径」上报，宿主拼上这一层在真实页面里的选择器，
// 选中、交给 AI 改，跟在预览里点选走的是同一条路——改的是同一个文件。
export const CARD_SCRIPT = `(()=>{
const root=document.querySelector('[data-pa-layer]')||document.body;let picked=[];const boxes=[];
const mk=c=>{const d=document.createElement('div');Object.assign(d.style,{position:'fixed',pointerEvents:'none',zIndex:2147483647,border:'2px solid '+c,borderRadius:'2px',boxSizing:'border-box',display:'none'});document.documentElement.appendChild(d);return d};
const hover=mk('#b8532f99');
const own=t=>t instanceof Element&&root.contains(t)&&t!==root?t:null;
function rel(el){const parts=[];for(let n=el;n&&n!==root;n=n.parentElement){const p=n.parentElement,same=p?[...p.children].filter(c=>c.tagName===n.tagName):[];parts.unshift(n.tagName.toLowerCase()+(same.length>1?':nth-of-type('+(same.indexOf(n)+1)+')':''))}return parts.join(' > ')}
function info(el){return {rel:rel(el),tag:el.tagName.toLowerCase(),text:(el.innerText||el.value||el.getAttribute('placeholder')||'').trim().slice(0,500),outer_html:el.outerHTML.slice(0,5000)}}
function place(b,el){if(!el){b.style.display='none';return}const r=el.getBoundingClientRect();Object.assign(b.style,{display:'block',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'})}
function paint(){while(boxes.length<picked.length)boxes.push(mk('#b8532f'));boxes.forEach((b,i)=>{place(b,picked[i]);b.style.background='#b8532f14'})}
addEventListener('mousemove',e=>place(hover,own(e.target)),true);
document.addEventListener('mouseleave',()=>place(hover,null));
addEventListener('click',e=>{e.preventDefault();e.stopPropagation();const el=own(e.target);if(!el)return;const add=e.shiftKey||e.metaKey||e.ctrlKey;
if(add){const i=picked.indexOf(el);i>=0?picked.splice(i,1):picked.length<16&&picked.push(el)}else picked=[el];
paint();parent.postMessage({source:'pa-card',type:'CARD_PICK',items:picked.map(info),additive:add},'*')},true);
for(const t of ['mousedown','pointerdown','submit','dblclick'])addEventListener(t,e=>e.preventDefault(),true);
addEventListener('message',e=>{const m=e.data||{};if(m.type!=='CARD_SHOW')return;picked=(m.rels||[]).map(r=>{try{return root.querySelector(':scope > '+r)}catch{return null}}).filter(Boolean);paint()});
})();`

// 卡片里点中的元素 → 和预览里点选一样的选中数据。layerSel 是这一层弹窗在真实页面里的选择器。
export function pickToSelection(node, items = []) {
  const one = item => ({
    selector: node.layerSel ? `${node.layerSel} > ${item.rel}` : item.rel,
    pid: '', tag: item.tag, text: item.text, outer_html: item.outer_html, styles: {}, modal: node.title,
  })
  const card = { nodeId: node.id, rels: items.map(i => i.rel) }
  if (items.length === 1) return { ...one(items[0]), card }
  const targets = items.map(one)
  return { selector: node.layerSel || targets[0]?.selector || '', pid: '', tag: 'div', kind: 'region', modal: node.title,
    text: targets.map(t => t.text || t.tag).join(' · ').slice(0, 500), outer_html: targets[0]?.outer_html || '', styles: {}, targets, card }
}

// 平铺的节点列表 → 按「谁打开了谁」挂成树。父节点不在列表里的当作顶层。
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
