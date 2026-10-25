// 弹窗、表单里的字段是什么控件。字段还是一行字，类型写在最后的括号里，选项用斜杠分开：
//   报修分类*（下拉：给排水/电气照明）   预计上门时间*（日期时间）   联系电话🔒（自动带出）
// 没写类型就按名字猜，界面上标出是猜的。后台 backend/arch_fields.py 是同一套规则，两边要一起改。

export const FIELD_TYPES = {
  text: '文本', textarea: '多行', select: '下拉', multi: '多选', radio: '单选', check: '勾选',
  date: '日期', datetime: '日期时间', daterange: '日期范围', time: '时间', number: '数字', money: '金额',
  phone: '手机号', upload: '上传', image: '图片', switch: '开关', person: '选人', cascade: '级联', note: '提示文字',
}
const TYPE_WORDS = {
  ...Object.fromEntries(Object.entries(FIELD_TYPES).map(([k, v]) => [v, k])),
  输入框: 'text', 文本框: 'text', 单行: 'text', 单行文本: 'text', 多行文本: 'textarea', 文本域: 'textarea', 长文本: 'textarea',
  下拉框: 'select', 下拉选择: 'select', 选择: 'select', 多选框: 'multi', 复选: 'multi', 单选框: 'radio', 复选框: 'check',
  勾选框: 'check', 日期选择: 'date', 时间范围: 'daterange', 日期区间: 'daterange', 数值: 'number', 整数: 'number',
  电话: 'phone', 附件: 'upload', 文件: 'upload', 照片: 'image', 人员: 'person', 人员选择: 'person', 省市区: 'cascade',
  地区: 'cascade', 说明: 'note', 提示: 'note',
}
// 有选项的控件：编辑时给一格写选项
export const WITH_OPTIONS = ['select', 'multi', 'radio']
const GUESS = [
  ['textarea', /备注|说明|描述|内容|原因|意见/],
  ['image', /照片|图片|头像/],
  ['upload', /附件|文件|凭证|合同扫描/],
  ['daterange', /时间段|起止|有效期|周期/],
  ['datetime', /时间$/],
  ['date', /日期|月份|年度|年份/],
  ['phone', /电话|手机|联系方式/],
  ['money', /金额|费用|价格|单价|总价/],
  ['number', /数量|次数|个数|天数|时长|面积|年限|排序|比例|系数/],
  ['switch', /^是否|启用|开启/],
  ['person', /负责人|处理人|审批人|执行人|经办人|维修工|指派/],
  ['cascade', /所在地区|省市区/],
  ['select', /类型|分类|类别|状态|等级|级别|程度|方式|来源|性别|所属|部门|楼栋|小区|区域|模板|行业/],
]
const OPTION_SPLIT = /\s*[/／、,，|]\s*/

export function guessType(name = '') {
  for (const [kind, re] of GUESS) if (re.test(name)) return kind
  return 'text'
}

// 最后面那对括号（里面可以再套括号），后面只许跟 * 🔒 空格
function tailGroup(text) {
  const chars = [...text]
  let end = chars.length
  while (end && ['*', '🔒', ' '].includes(chars[end - 1])) end--
  if (!end || !'）)'.includes(chars[end - 1])) return null
  let depth = 0
  for (let i = end - 1; i >= 0; i--) {
    if ('）)'.includes(chars[i])) depth++
    if ('（('.includes(chars[i])) depth--
    if (depth === 0) return { inner: chars.slice(i + 1, end - 1).join(''), rest: chars.slice(0, i).join('') + chars.slice(end).join('') }
  }
  return null
}

export function parseField(raw = '') {
  let text = String(raw).trim(), type = '', options = [], locked = false
  const group = tailGroup(text)
  if (group) {
    const [head, ...more] = group.inner.split(/[：:]/)
    const word = head.trim()
    if (TYPE_WORDS[word]) { type = TYPE_WORDS[word]; options = more.join('：').split(OPTION_SPLIT).map(o => o.trim()).filter(Boolean); text = group.rest }
    else if (word.startsWith('自动')) { locked = true; text = group.rest }
  }
  locked = locked || /🔒|自动带出/.test(text)
  const must = text.includes('*')
  const name = text.replace(/[*]|🔒|自动带出/g, '').trim()
  return { name, must, locked, type: type || guessType(name), options, guessed: !type }
}

// 反过来写成一行：类型和按名字猜的一样就不写
export function fieldText({ name = '', must = false, locked = false, type = '', options = [] }) {
  let out = name.trim() + (must ? '*' : '') + (locked ? '🔒' : '')
  const opts = (options || []).map(o => String(o).trim()).filter(Boolean)
  if (type && !locked && (opts.length || type !== guessType(name))) out += `（${FIELD_TYPES[type]}${opts.length ? '：' + opts.join('/') : ''}）`
  return out
}

// 按顿号、逗号、换行切开，括号里的不切：「类型（下拉：A、B）、备注」是两项
export function splitOutside(text = '', seps = '、,，;；\n') {
  const out = []
  let depth = 0, cur = ''
  for (const ch of String(text)) {
    if ('（([［【'.includes(ch)) depth++
    else if ('）)]］】'.includes(ch)) depth = Math.max(0, depth - 1)
    if (seps.includes(ch) && depth === 0) { out.push(cur); cur = '' } else cur += ch
  }
  out.push(cur)
  return out.map(x => x.trim()).filter(Boolean)
}
