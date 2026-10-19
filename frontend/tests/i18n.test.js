// 界面语言：切到英文后整句、拼出来的句子都能翻，模板里写的每句中文都有英文
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import en from '../src/locales/en.js'
import { appSource } from './appSource.js'

globalThis.localStorage = { getItem: () => 'en', setItem() {} }
const { t, setLocale, locale } = await import('../src/lib/i18n.js')

function vueFiles(dir) {
  return readdirSync(dir).flatMap(name => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? vueFiles(path) : name.endsWith('.vue') ? [path] : []
  })
}
const src = new URL('../src', import.meta.url).pathname

test('模板里每一句 $t(\'中文\') 都有英文', () => {
  const missing = new Set()
  for (const file of vueFiles(src)) {
    const text = readFileSync(file, 'utf8')
    for (const m of text.matchAll(/\$t\('((?:[^'\\]|\\.)*)'/g)) {
      const key = m[1].replace(/\\n/g, '\n').replace(/\\'/g, "'").replace(/\\\\/g, '\\')
      if (/[一-鿿]/.test(key) && !(key in en)) missing.add(key)
    }
  }
  assert.deepEqual([...missing], [])
})

test('英文：整句、带变量、后台拼好的句子', () => {
  setLocale('en')
  assert.equal(t('保存'), 'Save')
  assert.equal(t('自检通过：{0} 个页面、{1} 个按钮都点过', [3, 12]), 'Self-check passed: clicked through 3 pages and 12 buttons')
  assert.equal(t('应用 3 处修改'), 'Applying 3 changes')
  assert.equal(t('模型服务忙，5 秒后自动重试（第 2 次）'), 'Model service busy; retrying in 5 s (attempt 2)')
  // 嵌套：后半句也是拼出来的
  assert.match(t('已导出 3 个业务页面、5 个视图；还有 2 个页面没展开，先点「一键展开」可以导出完整的'), /^Exported 3 pages and 5 views; 2 pages/)
})

test('不该翻的不动：英文原文、没收录的中文、只有标点的通配', () => {
  setLocale('en')
  assert.equal(t('hello'), 'hello')
  assert.equal(t('我想做一个巡检系统'), '我想做一个巡检系统')
  assert.equal(t('巡检 · 计划'), '巡检 · 计划')   // 「{0} · {1}」不能当通配吞掉任何句子
})

test('切回中文照原样显示，并记住选择', () => {
  setLocale('zh')
  assert.equal(locale.value, 'zh')
  assert.equal(t('保存'), '保存')
  assert.equal(t('共 {0} 条', [3]), '共 3 条')
})

test('「···」菜单里有语言切换；请求带上界面语言', () => {
  const header = readFileSync(join(src, 'components/layout/AppHeader.vue'), 'utf8')
  assert.match(header, /v-for="l in LANGUAGES"/)
  assert.match(header, /@click="setLocale\(l\.id\)"/)
  assert.match(appSource(), /lang: locale\.value/)
})
