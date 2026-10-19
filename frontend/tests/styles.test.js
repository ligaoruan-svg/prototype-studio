// 风格：新建原型时选一套（内置 / 我的 / 不选 / 导入），设计规范里能换
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = path => readFileSync(new URL('../src/' + path, import.meta.url), 'utf8')

test('选风格的卡片：内置、我的、不选风格、导入风格', () => {
  const picker = read('components/settings/StylePicker.vue')
  assert.match(picker, /'builtin:' \+ s\.folder/)
  assert.match(picker, /'mine:' \+ s\.folder/)
  assert.match(picker, /value: 'none', name: '不选风格'/)
  assert.match(picker, /emit\('import'\)/)
  assert.match(picker, /!card\.has_shell/)   // 没外壳的「我的」要说清楚只能当规矩用
})

test('新建原型带上选的风格；设计规范里有「风格」一栏', () => {
  const app = read('App.vue'), dialog = read('components/layout/StudioDialog.vue')
  assert.match(app, /post\('\/api\/projects\/new', \{ name: projectName\.value, style: newStyle\.value \}\)/)
  assert.match(app, /\/api\/projects\/\$\{project\.value\.id\}\/style/)
  assert.match(dialog, /<StylePicker v-model="newStyle"/)
  assert.match(dialog, /specTab === 'style'/)
  // 导入用的文件框在所有弹窗分支外面：新建和设计规范里都点得到
  assert.ok(dialog.indexOf('ref="styleInput"') < dialog.indexOf('<FileManager'))
})
