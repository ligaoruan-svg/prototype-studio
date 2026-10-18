// 界面语言：源码里直接写中文，显示时按当前语言查翻译表。
// - 翻译表以中文原文为键（src/locales/en.js），没翻到的照原样显示中文，不会空白
// - 带变量的写成 {0} {1}：t('共 {0} 条', [n])；后台、AI 流程里拼好的整句（「自检发现 3 个问题」）
//   也能翻：翻译表里的 {n} 会当成通配去匹配
// - 加一种语言 = 加一份 locales/xx.js，再在 LANGUAGES 里登记
// - AI 的回复、生成的页面跟着用户提问用的语言走，不归这里管（见 prompts）
import { ref } from 'vue'
import en from '../locales/en.js'

export const LANGUAGES = [
  { id: 'zh', label: '中文', html: 'zh-CN', dict: null },
  { id: 'en', label: 'English', html: 'en', dict: en },
]
const KEY = 'pa-language'
function initial() {
  try { const saved = localStorage.getItem(KEY); if (LANGUAGES.some(l => l.id === saved)) return saved } catch { /* 读不到就按浏览器 */ }
  const nav = (typeof navigator !== 'undefined' && navigator.language) || 'zh'
  return /^zh/i.test(nav) ? 'zh' : 'en'
}
export const locale = ref(initial())
export const current = () => LANGUAGES.find(l => l.id === locale.value) || LANGUAGES[0]
export function setLocale(id) {
  if (!LANGUAGES.some(l => l.id === id)) return
  locale.value = id
  try { localStorage.setItem(KEY, id) } catch { /* 存不下就只管这次 */ }
  syncDocument()
}
export function syncDocument() {
  if (typeof document !== 'undefined') document.documentElement.lang = current().html
}

const CJK = /[　-〿一-鿿＀-￯]/
const CJK_ALL = /[一-鿿]/g
// 带 {xxx} 的键编译成正则，翻译拼好的整句。
// 固定部分至少要有两个汉字，否则「{0} · {1}」这种会把什么都吞掉
const patterns = new WeakMap()
function compiled(dict) {
  if (!patterns.has(dict)) {
    const list = []
    for (const [key, value] of Object.entries(dict)) {
      if (!/\{\w+\}/.test(key)) continue
      if ((key.replace(/\{\w+\}/g, '').match(CJK_ALL) || []).length < 2) continue
      const names = []
      const source = key.split(/(\{\w+\})/).map(part => {
        const m = part.match(/^\{(\w+)\}$/)
        if (m) { names.push(m[1]); return '([\\s\\S]+?)' }
        return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
      }).join('')
      list.push({ re: new RegExp('^' + source + '$'), names, value, size: key.length })
    }
    list.sort((a, b) => b.size - a.size)   // 先试更具体的
    patterns.set(dict, list)
  }
  return patterns.get(dict)
}
const fill = (text, vars) => vars == null ? text
  : String(text).replace(/\{(\w+)\}/g, (all, k) => vars[k] ?? all)

export function t(text, vars) {
  if (text == null || text === '') return text
  const raw = String(text)
  const dict = current().dict
  if (!dict || !CJK.test(raw)) return fill(raw, vars)
  if (Object.prototype.hasOwnProperty.call(dict, raw)) return fill(dict[raw], vars)
  if (vars == null && raw.length <= 600) {
    for (const p of compiled(dict)) {
      const m = raw.match(p.re)
      if (m) return p.value.replace(/\{(\w+)\}/g, (all, k) => { const i = p.names.indexOf(k); return i >= 0 ? t(m[i + 1]) : all })
    }
  }
  return fill(raw, vars)
}
// 日期、数字跟着语言走
export const dateLocale = () => current().html
