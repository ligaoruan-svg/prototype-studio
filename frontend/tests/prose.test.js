import test from 'node:test'
import assert from 'node:assert/strict'
import { prose } from '../src/lib/prose.js'

test('AI 回复排版：段落、列表、加粗；模型写的 HTML 当字显示', () => {
  assert.equal(prose('结论：缺两类功能。\n\n- **改派**：没有入口\n- 没法接'), '<p>结论：缺两类功能。</p><ul><li><strong>改派</strong>：没有入口</li><li>没法接</li></ul>')
  assert.equal(prose('1. 第一\n2. 第二'), '<ol><li>第一</li><li>第二</li></ol>')
  assert.equal(prose('- 改派入口没有：派单只能派一次'), '<ul><li><strong>改派入口没有</strong>：派单只能派一次</li></ul>')   // 冒号前的小标题加粗
  assert.equal(prose('<img src=x onerror=alert(1)>'), '<p>&lt;img src=x onerror=alert(1)&gt;</p>')
})
