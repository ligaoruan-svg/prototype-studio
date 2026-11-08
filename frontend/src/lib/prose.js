// AI 回复的正文排版（参照 Claude）：段落、「- 」列表、「1. 」编号、**加粗**、`代码`、### 小标题。
// 先整段转义再加标签，模型写的 HTML 一律当字显示
const esc = s => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
// 模型转义过的 \* \_ 照字显示；整段都加粗的「**结论：……**」只粗冒号前那几个字（不然一大段黑字压着）
const inline = s => esc(s.replace(/^\*\*([^*：:]{1,10})([：:])(.{20,})\*\*$/, '**$1**$2$3'))
  .replace(/\\([*_`#\-])/g, (_, c) => `&#${c.charCodeAt(0)};`)
  .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>')

export function prose(text) {
  const out = []
  let list = null
  const close = () => { if (list) { out.push(`<${list.tag}>${list.items.map(i => `<li>${i}</li>`).join('')}</${list.tag}>`); list = null } }
  for (const raw of String(text || '').split('\n')) {
    const line = raw.trimEnd()
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/), num = line.match(/^\s*\d+[.、)]\s+(.*)$/), head = line.match(/^\s*#{1,4}\s+(.*)$/)
    if (bullet || num) {
      const tag = bullet ? 'ul' : 'ol'
      if (list?.tag !== tag) { close(); list = { tag, items: [] } }
      const item = (bullet || num)[1], lead = !item.includes('**') && item.match(/^([^：:。，,]{2,16})[：:](.+)$/)
      list.items.push(lead ? `<strong>${inline(lead[1])}</strong>：${inline(lead[2].trim())}` : inline(item))
    } else {
      close()
      if (head) out.push(`<h4>${inline(head[1])}</h4>`)
      else if (line.trim()) out.push(`<p>${inline(line)}</p>`)
    }
  }
  close()
  return out.join('')
}
