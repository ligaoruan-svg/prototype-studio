// 字段是什么控件：括号里写明的照写的算，没写按名字猜；写回去和后台 arch_fields.py 一样
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fieldText, guessType, parseField, splitOutside } from '../src/lib/archFields.js'
import { sameName } from '../src/lib/architecture.js'

test('括号里写的控件和选项，选项里还能再套括号', () => {
  assert.deepEqual(parseField('报修人*（下拉：张三（YZ-001）/李四）'), { name: '报修人', must: true, locked: false, type: 'select', options: ['张三（YZ-001）', '李四'], guessed: false })
  assert.equal(parseField('金额（元）').name, '金额（元）')          // 不是控件名的括号是名字的一部分
  assert.equal(parseField('金额（元）').type, 'money')
  assert.deepEqual([parseField('工单编号（自动生成）').locked, parseField('联系电话🔒').locked], [true, true])
})

test('没写按名字猜，猜得和写的一样就不写', () => {
  assert.deepEqual(['报修分类', '预计上门时间', '问题描述', '现场照片', '联系电话', '报修事项'].map(guessType), ['select', 'datetime', 'textarea', 'image', 'phone', 'text'])
  assert.equal(fieldText({ name: '报修分类', must: true, type: 'select' }), '报修分类*')
  assert.equal(fieldText({ name: '报修分类', must: true, type: 'select', options: ['给排水', '电气照明'] }), '报修分类*（下拉：给排水/电气照明）')
  assert.equal(fieldText({ name: '报修事项', type: 'select' }), '报修事项（下拉）')
  assert.equal(fieldText(parseField('报修分类*（下拉：A/B）')), '报修分类*（下拉：A/B）')
  assert.deepEqual(splitOutside('类型（下拉：A、B）、备注'), ['类型（下拉：A、B）', '备注'])
})

test('按钮写的目标带括号补充也认得', () => {
  assert.ok(sameName('新增报修工单（业主来电代录）', '新增报修工单'))
  assert.ok(sameName('报修详情抽屉', '报修详情'))
  assert.ok(!sameName('派单', '催单'))
})
