// 按业务梳理验收原型：梳理里每个对象的每个动作（「派单：待派单→处理中（调度员）」）就是一条验收项。
// 在看不见的副本里真去点（backend/bridge.py 的 accept），用 Store 当裁判：状态真变了、按钮跟着消失才算过。
// 还没做的对象（Store 里没有这类数据）不算没过，单独列出来——不然做了两个模块就要求 AI 把剩下的全做了
import { probeFrame } from './probe.js'

const AUTO = /系统|自动|定时|超时|到期/
const ACTION = /^([^：:（(]+)[：:]\s*(.+?)\s*(?:→|->|—>|=>)\s*([^（(]+?)\s*(?:[（(]([^）)]*)[）)])?\s*$/

// 「派单：待派单→处理中（调度员）」→ { action, from: ['待派单'], to, ui }；写不成这样的跳过
export function parseAction(text, roles = []) {
  const m = String(text || '').trim().match(ACTION)
  if (!m) return null
  const [, action, from, to, note = ''] = m.map(x => (x || '').trim())
  // 括号里第一段才是谁做的，后面是补充说明（「客服，需填原因」）；「客服」也算「物业客服」
  const who = note.split(/[，,；;、\s]/)[0]
  // 先认角色：写全了的算人（系统管理员）；简称（客服 → 物业客服）也算，但简称本身是「系统」这类不算
  const isRole = !!who && roles.some(r => r && (who.includes(r) || (r.includes(who) && !AUTO.test(who))))
  const ui = isRole || (!AUTO.test(who) && !AUTO.test(action) && (!who || !roles.length))
  // 起点写「—」「无」「新建」的是新建一条（生成：—→待核对）
  return { action, from: from.split(/[/、,，|]|或/).map(x => x.trim()).filter(x => x && !/^([—\-–－]+|无|空|新建)$/.test(x)), to, who, ui }
}

export function checklist(spec) {
  if (spec?.status !== 'confirmed') return []
  const roles = (spec.roles || []).map(r => r.name)
  // 同一个动作从同一个状态出发、结果二选一（导入并核对 → 已核对 / 有差异）：合成一条，到哪个都算
  const out = []
  for (const o of spec.objects || []) for (const a of (o.actions || []).map(x => parseAction(x, roles)).filter(Boolean)) {
    const same = out.find(c => c.object === o.name && c.action === a.action && c.from.join() === a.from.join())
    if (same) { if (!same.to.includes(a.to)) same.to.push(a.to) } else out.push({ object: o.name, ...a, to: [a.to] })
  }
  return out
}

const whose = c => c.from.length ? `「${c.from.join('/')}」的${c.object}` : `新建${c.object}：`
export const itemText = c => c.ui ? `${whose(c)}点「${c.action}」→ 变成「${c.to.join('」或「')}」` : `${c.object}「${c.action}」（${c.who || '系统'}做，不在后台点）写进了流转`

// 没过的原因 → 一句人和 AI 都看得懂的话
function failText(c, r) {
  const head = whose(c) + (r.key ? `（${r.key}）` : '')
  const flowHint = r.inFlow === false ? `（Store.flow('${c.object}') 里还没有「${c.action}」）` : ''
  switch (r.why) {
    case 'nofrom': return `${c.object}的演示数据里没有「${c.from.join('/')}」的，演示不了「${c.action}」：Store.define 里补几条${r.states?.length ? `（现在只有：${r.states.join('、')}）` : ''}`
    case 'nokey': return `${c.object}的演示数据没有编号或名称这类能认出是哪一条的字段，页面上也要显示出来`
    case 'nobutton': return `${head}在页面上找不到「${c.action}」按钮：列表这一行或它的详情里要有，按 Store.can 出现${flowHint}`
    case 'error': return `${head}点「${c.action}」报错：${r.error}`
    case 'gone': return `${head}点「${c.action}」后这一条从 Store 里没了：流转要用 Store.move 改状态，不是删掉`
    case 'blocked': return `${head}点「${c.action}」后弹窗确认不了${r.note ? `（${r.note}）` : ''}，状态还是「${r.from}」`
    case 'nostore': return `${head}点「${c.action}」页面变了，但 Store 里的状态还是「${r.from}」：要用 Store.move('${c.object}',id,'${c.action}') 改${flowHint}`
    case 'noreact': return `${head}点「${c.action}」没反应，状态还是「${r.from}」，应该变成「${c.to.join('」或「')}」${flowHint}`
    case 'wrongto': return `${head}点「${c.action}」后变成了「${r.now}」，梳理里应该是「${c.to.join('」或「')}」`
    case 'stays': return `${head}「${c.action}」后已经是「${r.now || c.to[0]}」，这一行的「${c.action}」按钮还在：要按 Store.can 出现`
    case 'noflow': return `「${c.action}」是${c.who || '系统'}做的、后台不用按钮，但 Store.flow('${c.object}') 里也要有这个动作`
    default: return `${head}点「${c.action}」没验过：${r.why || '原因不明'}`
  }
}

// 跑一遍：{ items: [{ text, ok, why }], fails: [文字], missing: [还没做的对象], skipped }
export async function runAccept({ spec, makeDoc, width = 1200, height = 800 }) {
  const checks = checklist(spec)
  if (!checks.length) return { items: [], fails: [], missing: [], skipped: '梳理里没有能验的流转' }
  const frame = probeFrame(makeDoc(''), width, height)
  try {
    await frame.load()
    const reply = await frame.rpc('PA_ACCEPT', { checks }, 70_000)
    if (reply.timeout) return { items: [], fails: [], missing: [], skipped: '验收超时' }
    if (!reply.store) return { items: [], fails: [], missing: [], skipped: '页面里还没有 Store（老页面，下次做页面时会补上）' }
    const items = checks.map((c, i) => {
      const r = reply.results[i] || {}
      return { object: c.object, text: itemText(c), ok: r.ok, why: r.why, fail: r.ok === false ? failText(c, r) : '' }
    })
    const missing = [...new Set(items.filter(it => it.why === 'missing').map(it => it.object))]
    return { items: items.filter(it => it.why !== 'missing'), fails: items.filter(it => it.ok === false).map(it => it.fail), missing, skipped: '' }
  } catch (e) {
    return { items: [], fails: [], missing: [], skipped: String(e?.message || e) }
  } finally { frame.dispose() }
}

export const acceptSummary = r => r.skipped ? '验收没跑：' + r.skipped
  : `按梳理验收：${r.items.length - r.fails.length}/${r.items.length} 条流转走通${r.missing.length ? `，${r.missing.join('、')} 还没做` : ''}`

// 交给 AI 修的那段话
export function acceptRequest(fails) {
  return '【验收】程序按业务梳理把每个流转在页面上真点了一遍（看 Store 里的状态变没变），下面这些没过。逐条修掉，只改有问题的地方，别动其他内容：\n'
    + fails.map((t, i) => `${i + 1}. ${t}`).join('\n')
}
