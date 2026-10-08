// 展开视图里和 DOM 无关的部分：卡片文档、树结构、缩略图取景、路径描述。
// 单独拿出来，是为了不开浏览器也能测。

const attr = value => String(value ?? '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
const attrs = a => (a?.class ? ` class="${attr(a.class)}"` : '') + (a?.style ? ` style="${attr(a.style)}"` : '')

// 卡片是一张"静态快照"：带上原型的全部样式，但不带任何脚本。
// 动画、过渡关掉，否则拍下来的是淡入的第一帧（半透明、偏移）。
export function cardDocument(styles = {}, body = '') {
  const base = /^https?:/i.test(styles.base || '') ? `<base href="${attr(styles.base)}">` : ''
  return '<!doctype html><html' + attrs(styles.html) + '><head><meta charset="utf-8">' + base + (styles.head || '') +
    '<style>html,body{overflow:hidden!important}*,*::before,*::after{animation:none!important;transition:none!important}</style>' +
    '</head><body' + attrs(styles.body) + '>' + body + '</body></html>'
}

// 平铺的节点列表 → 按「谁打开了谁」挂成树。父节点不在列表里的当作顶层。
export function buildTree(nodes = []) {
  const byId = new Map(nodes.map(n => [n.id, { ...n, children: [] }]))
  const roots = []
  for (const node of byId.values()) (node.parent != null && byId.has(node.parent) ? byId.get(node.parent).children : roots).push(node)
  return roots
}

// 只框住弹窗本体：按卡片宽度缩放，太高的截断。放大不超过 0.6，免得小弹窗糊成一团。
export function thumbFrame(box, cardWidth = 260, maxHeight = 210) {
  const w = Math.max(1, box?.w || 1), h = Math.max(1, box?.h || 1)
  const scale = Math.min(cardWidth / w, 0.6)
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
