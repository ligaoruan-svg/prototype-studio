// 导出架构：画布上的页面树写成 Markdown 大纲（贴进需求文档；XMind、幕布能直接导入成脑图），
// 或者一张表（CSV，Excel / WPS 直接打开，一行一个节点）。只看画布，不碰原型
import { ACTIONS, NODE_TYPES, protoState } from './architecture.js'

const HEADING = ['module', 'page', 'tab', 'drill']      // 这几种写成标题，别的写成标题下面的列表
const PROTO = { in: '有', planned: '还没有', gone: '已经没有' }
const label = n => NODE_TYPES[n.type]?.label || ''
const action = n => n.action ? `${ACTIONS[n.action] || n.action}${n.target ? `「${n.target}」` : ''}` : ''

function lines(node, tracked) {
  const out = []
  if (node.desc) out.push(node.desc)
  if (node.fields?.length) out.push('字段：' + node.fields.join('、'))
  if (node.cols?.length) out.push('列：' + node.cols.join('、'))
  if (action(node)) out.push('点了：' + action(node))
  if (node.when) out.push('出现：' + node.when)
  if (tracked && protoState(node) !== 'in') out.push(`（原型里${PROTO[protoState(node)]}）`)
  return out
}

// tracked：导入过原型的（有 base），才标「原型里还没有」
export function toMarkdown(arch, { tracked = false } = {}) {
  const out = [`# ${arch?.name || '未命名系统'}`]
  if (arch?.summary) out.push('', '> ' + arch.summary)
  const visit = (nodes, depth, indent) => {
    for (const node of nodes || []) {
      const info = lines(node, tracked)
      if (HEADING.includes(node.type) && indent < 0) {
        out.push('', `${'#'.repeat(Math.min(depth + 2, 6))} ${label(node)}：${node.name}`)
        const [desc, ...rest] = node.desc ? info : ['', ...info]
        if (desc) out.push('', desc)
        if (rest.length) out.push('', ...rest.map(x => '- ' + x))
        visit(node.children, depth + 1, -1)
        continue
      }
      const pad = '  '.repeat(Math.max(indent, 0))
      if (indent < 0) out.push('')
      out.push(`${pad}- **${label(node)}** ${node.name}`)
      for (const x of info) out.push(`${pad}  - ${x}`)
      visit(node.children, depth + 1, Math.max(indent, 0) + 1)
    }
  }
  visit(arch?.nodes, 0, -1)
  return out.join('\n').replace(/\n{3,}/g, '\n\n') + '\n'
}

const cell = v => /[",\n]/.test(v = String(v ?? '')) ? `"${v.replace(/"/g, '""')}"` : v
export function toCsv(arch, { tracked = false } = {}) {
  const head = ['模块', '菜单页', '页签 / 下钻页', '类型', '名称', '介绍', '字段 / 列', '点了以后', '什么时候出现', ...(tracked ? ['原型里'] : [])]
  const rows = [head]
  const visit = (nodes, ctx) => {
    for (const node of nodes || []) {
      const here = { ...ctx }
      if (node.type === 'module') here.module = node.name
      else if (node.type === 'page') here.page = node.name
      else if (node.type === 'tab' || node.type === 'drill') here.tab = node.name
      rows.push([here.module || '', here.page || '', here.tab || '', label(node), node.name, node.desc || '',
        [...(node.fields || []), ...(node.cols || [])].join('、'), action(node), node.when || '', ...(tracked ? [PROTO[protoState(node)]] : [])])
      visit(node.children, here)
    }
  }
  visit(arch?.nodes, {})
  // 开头的 BOM：Excel 才认得出是 UTF-8，不然中文全是乱码
  return '﻿' + rows.map(r => r.map(cell).join(',')).join('\r\n') + '\r\n'
}

export function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
