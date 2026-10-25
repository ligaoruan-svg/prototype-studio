<script setup>
// 右边的详情：选中什么就改什么。打字直接改到架构里（停手半秒自动保存），开始改一格之前留一份底给「撤销」
import { computed, inject } from 'vue'
import { Plus, RotateCw, Trash2, X } from 'lucide-vue-next'
import ArchFieldEdit from './ArchFieldEdit.vue'
import { splitOutside } from '../../lib/archFields.js'
import { ACTIONS, CHILD_TYPES, FIELD_KINDS, LANE_KINDS, LAYER_TYPES, NODE_TYPES, SCREEN_TYPES, findNode, sameName, screens, targetsIn } from '../../lib/architecture.js'

const s = inject('studio')
const { arch, archSelected, archIssues, archView, locked, page } = s
const item = computed(() => { void JSON.stringify(archSelected.value); return s.archSelectedItem() })
const kind = computed(() => item.value ? archSelected.value.kind : '')
const entityNames = computed(() => (arch.value?.entities || []).map(e => e.name))
const screenList = computed(() => screens(arch.value))
const parentOf = computed(() => kind.value === 'node' ? findNode(arch.value, item.value.id)?.parents.slice(-1)[0] || null : null)
const typeChoices = computed(() => {
  if (kind.value !== 'node') return []
  const allowed = CHILD_TYPES[parentOf.value?.type || 'root'] || []
  return [...new Set([item.value.type, ...allowed])]
})
const issues = computed(() => archIssues.value.filter(i => item.value && (i.node === item.value.id || i.entity === item.value.id || i.step === item.value.id)))
const isScreen = computed(() => kind.value === 'node' && SCREEN_TYPES.includes(item.value.type))
const targets = computed(() => kind.value === 'node' && item.value.type === 'button' ? targetsIn(arch.value, item.value.id, item.value.action) : [])
// 一行一个（字段、列）：必填在后面加 *
const linesText = value => (value || []).join('\n')
function setLines(target, key, text) {
  const values = splitOutside(text)
  if (values.length) target[key] = values; else delete target[key]
  s.archDirty()
}
function setAction(value) {
  const node = item.value
  s.archChange(() => { if (value) node.action = value; else { delete node.action; delete node.target } })
}
// 点「打开：xx」直接跳到那个弹窗
function gotoTarget(name) {
  const hit = [...(function* w(ns) { for (const n of ns || []) { yield n; yield* w(n.children) } })(arch.value.nodes)].find(n => sameName(n.name, name))
  if (hit) s.archSelect('node', hit.id)
}
const outgoing = computed(() => kind.value === 'entity' ? arch.value.relations.filter(r => r.from === item.value.name) : [])

// 逗号分开的几项（谁用、标签、需求编号、角色、状态）
const listText = (value, sep = '、') => (value || []).join(sep)
function setList(target, key, text, sep = /[,，、;；]/) {
  const values = text.split(sep).map(v => v.trim()).filter(Boolean)
  if (values.length) target[key] = values; else delete target[key]
  s.archDirty()
}
function setText(target, key, value) { if (value) target[key] = value; else delete target[key]; s.archDirty() }
function toggleData(name) {
  const node = item.value
  s.archChange(() => {
    const list = node.data || []
    node.data = list.includes(name) ? list.filter(d => d !== name) : [...list, name]
    if (!node.data.length) delete node.data
  })
}
function rename(event) {
  if (!s.renameEntity(item.value, event.target.value)) event.target.value = item.value.name
}
function addField() { const e = item.value; s.archChange(() => e.fields.push({ name: '新字段', kind: 'plain' })) }
function removeField(i) { const e = item.value; s.archChange(() => e.fields.splice(i, 1)) }
function addRelation() {
  const e = item.value, to = entityNames.value.find(n => n !== e.name)
  if (to) s.archChange(a => a.relations.push({ from: e.name, to, label: '1 → N' }))
}
function removeRelation(rel) { s.archChange(a => { a.relations = a.relations.filter(r => r !== rel) }) }
function toggleNext(id) {
  const st = item.value
  s.archChange(() => { st.next = (st.next || []).includes(id) ? st.next.filter(n => n !== id) : [...(st.next || []), id] })
}
function linkNode(value) { const st = item.value; s.archChange(() => { if (value) st.node = value; else delete st.node }) }
function gotoNode(id) { archView.value = 'tree'; s.archSelect('node', id) }
</script>

<template>
  <aside class="arch-detail" :aria-label="$t('详情')">
    <!-- 系统 -->
    <template v-if="kind === 'root'">
      <div class="ad-head"><span class="an-type">{{ $t('系统') }}</span><button class="icon-button" :aria-label="$t('关闭')" @click="s.archSelect(null)"><X :size="14" /></button></div>
      <label>{{ $t('系统名') }}<input v-model="item.name" @focus="s.archSnapshot()" @input="s.archDirty()"></label>
      <label>{{ $t('一句话介绍') }}<textarea v-model="item.summary" rows="3" :placeholder="$t('给谁用、管什么')" @focus="s.archSnapshot()" @input="s.archDirty()"></textarea></label>
      <label>{{ $t('角色') }}<input :value="listText(item.roles)" :placeholder="$t('用顿号分开，比如：管理员、巡检员')" @focus="s.archSnapshot()" @change="setList(item, 'roles', $event.target.value)"></label>
      <p class="arch-muted">{{ $t('范围：只做电脑端') }}</p>
    </template>

    <!-- 页面树的节点 -->
    <template v-else-if="kind === 'node'">
      <div class="ad-head"><select :value="item.type" :aria-label="$t('类型')" @change="s.archChange(() => { item.type = $event.target.value })"><option v-for="t in typeChoices" :key="t" :value="t">{{ $t(NODE_TYPES[t].label) }}</option></select>
        <span v-if="parentOf" class="arch-muted">{{ parentOf.name }} ›</span><button class="icon-button" :aria-label="$t('关闭')" @click="s.archSelect(null)"><X :size="14" /></button></div>
      <input class="ad-name" v-model="item.name" :aria-label="$t('名称')" @focus="s.archSnapshot()" @input="s.archDirty()">
      <label>{{ $t('一句话介绍') }}<textarea v-model="item.desc" rows="3" :placeholder="$t('这一块干什么、最先要看到什么')" @focus="s.archSnapshot()" @input="s.archDirty()"></textarea></label>
      <!-- 按钮：点了怎样 -->
      <template v-if="item.type === 'button'">
        <div class="ad-two"><label>{{ $t('点了以后') }}<select :value="item.action || ''" @change="setAction($event.target.value)"><option value="">{{ $t('（还没定）') }}</option><option v-for="(label, k) in ACTIONS" :key="k" :value="k">{{ $t(label) }}</option></select></label>
          <label v-if="item.action">{{ item.action === 'open' ? $t('打开哪个') : item.action === 'jump' ? $t('跳到哪页') : item.action === 'run' ? $t('做什么') : $t('提示什么') }}<input :value="item.target || ''" :list="'ad-targets-' + item.id" @focus="s.archSnapshot()" @input="setText(item, 'target', $event.target.value)"><datalist :id="'ad-targets-' + item.id"><option v-for="t in targets" :key="t" :value="t"></option></datalist></label></div>
        <button v-if="item.target && targets.some(t => sameName(t, item.target))" class="quiet ad-link" @click="gotoTarget(item.target)">{{ $t('去看「{0}」 →', [item.target]) }}</button>
        <label>{{ $t('什么时候出现') }}<input :value="item.when || ''" :placeholder="$t('比如：状态是草稿时；勾选了才能点。一直有就空着')" @focus="s.archSnapshot()" @input="setText(item, 'when', $event.target.value)"></label>
      </template>
      <!-- 弹窗 / 抽屉 / 向导 / 区块：里面有哪些字段 -->
      <template v-if="[...LAYER_TYPES, 'block'].includes(item.type)">
        <ArchFieldEdit v-if="item.type !== 'drawer'" :node="item" />
        <label v-else>{{ $t('字段（一行一个）') }}<textarea rows="5" :value="linesText(item.fields)" @focus="s.archSnapshot()" @change="setLines(item, 'fields', $event.target.value)"></textarea></label>
        <label v-if="LAYER_TYPES.includes(item.type)">{{ $t('确认后') }}<input :value="item.after || ''" :placeholder="$t('比如：列表多一行，关联排放源数 +1')" @focus="s.archSnapshot()" @input="setText(item, 'after', $event.target.value)"></label>
      </template>
      <label v-if="item.type === 'table'">{{ $t('列（一行一个）') }}<textarea rows="5" :value="linesText(item.cols)" @focus="s.archSnapshot()" @change="setLines(item, 'cols', $event.target.value)"></textarea></label>
      <label v-if="isScreen">{{ $t('谁用') }}<input :value="listText(item.who)" :placeholder="$t('用顿号分开')" @focus="s.archSnapshot()" @change="setList(item, 'who', $event.target.value)"></label>
      <template v-if="isScreen || item.type === 'jump'">
        <label>{{ $t('怎么进来') }}<input :value="item.entry || ''" :placeholder="item.type === 'drill' ? $t('比如：点列表里的模板编号') : $t('比如：左侧菜单')" @focus="s.archSnapshot()" @input="setText(item, 'entry', $event.target.value)"></label>
        <div class="ad-two"><label>{{ $t('地址') }}<input :value="item.route || ''" placeholder="ops-route" @focus="s.archSnapshot()" @input="setText(item, 'route', $event.target.value.replace(/^#/, ''))"></label>
          <label>{{ $t('带过去') }}<input :value="item.params || ''" :placeholder="$t('比如：模板编号')" @focus="s.archSnapshot()" @input="setText(item, 'params', $event.target.value)"></label></div>
        <label>{{ $t('怎么回去') }}<input :value="item.back || ''" :placeholder="$t('比如：返回列表，菜单仍高亮原来那项')" @focus="s.archSnapshot()" @input="setText(item, 'back', $event.target.value)"></label>
      </template>
      <div v-if="isScreen || ['table', ...LAYER_TYPES].includes(item.type)" class="ad-field"><span>{{ $t('用到的数据') }}</span>
        <div class="ad-chips"><button v-for="name in entityNames" :key="name" :class="{ on: (item.data || []).includes(name) }" @click="toggleData(name)">{{ name }}</button>
          <span v-if="!entityNames.length" class="arch-muted">{{ $t('先在「数据关系」里加数据') }}</span></div></div>
      <label>{{ $t('标签') }}<input :value="listText(item.tags, '；')" :placeholder="$t('复用、联动…几条用分号分开')" @focus="s.archSnapshot()" @change="setList(item, 'tags', $event.target.value, /[;；]/)"></label>
      <label>{{ $t('需求编号') }}<input :value="listText(item.req)" placeholder="#85、#86" @focus="s.archSnapshot()" @change="setList(item, 'req', $event.target.value)"></label>
      <div v-if="issues.length" class="ad-issues"><p v-for="(i, n) in issues" :key="n" :class="i.level">⚠ {{ i.text }}</p></div>
      <div class="ad-actions">
        <button v-if="isScreen && archView !== 'page'" class="outline" @click="archView = 'page'">{{ $t('看页面结构') }}</button>
        <button v-if="isScreen" class="outline" :disabled="locked || !page" :title="$t('只按架构重做这一页，别的页面不动')" @click="s.rebuildNode(item)"><RotateCw :size="14" />{{ $t('只重做这一页') }}</button>
        <button class="quiet danger" @click="s.archRemove(item.id)"><Trash2 :size="14" />{{ $t('删除') }}</button>
      </div>
    </template>

    <!-- 数据 -->
    <template v-else-if="kind === 'entity'">
      <div class="ad-head"><span class="an-type">{{ $t('数据') }}</span><button class="icon-button" :aria-label="$t('关闭')" @click="s.archSelect(null)"><X :size="14" /></button></div>
      <input class="ad-name" :value="item.name" :aria-label="$t('名称')" @change="rename">
      <div class="ad-two"><label>{{ $t('编号样子') }}<input v-model="item.code" placeholder="PT-xxx" @focus="s.archSnapshot()" @input="s.archDirty()"></label>
        <label>{{ $t('角色') }}<input v-model="item.role" :placeholder="$t('模板 / 实例 / 配置…')" @focus="s.archSnapshot()" @input="s.archDirty()"></label></div>
      <label class="ad-inline"><input type="checkbox" v-model="item.external" @change="s.archDirty()">{{ $t('外部系统的数据（只读，不做它的页面）') }}</label>
      <label>{{ $t('介绍') }}<textarea v-model="item.desc" rows="2" @focus="s.archSnapshot()" @input="s.archDirty()"></textarea></label>
      <label>{{ $t('状态') }}<input :value="listText(item.states, ' → ')" :placeholder="$t('待执行 → 执行中 → 已完成')" @focus="s.archSnapshot()" @change="setList(item, 'states', $event.target.value, /→|->|[,，、]/)"></label>
      <div class="ad-field"><span>{{ $t('字段') }}</span>
        <div v-for="(f, i) in item.fields" :key="i" class="ad-row">
          <input v-model="f.name" :aria-label="$t('字段名')" @focus="s.archSnapshot()" @input="s.archDirty()">
          <select v-model="f.kind" :aria-label="$t('字段类型')" @change="s.archDirty()"><option v-for="(label, k) in FIELD_KINDS" :key="k" :value="k">{{ $t(label) }}</option></select>
          <select v-if="f.kind === 'ref'" v-model="f.ref" :aria-label="$t('引用哪类数据')" @change="s.archDirty()"><option value="">{{ $t('引用…') }}</option><option v-for="n in entityNames.filter(n => n !== item.name)" :key="n" :value="n">{{ n }}</option></select>
          <input v-else v-model="f.note" :placeholder="f.kind === 'derived' ? $t('= 怎么算') : $t('备注')" :aria-label="$t('备注')" @focus="s.archSnapshot()" @input="s.archDirty()">
          <button class="icon-button" :aria-label="$t('删掉这个字段')" @click="removeField(i)"><X :size="13" /></button></div>
        <button class="quiet" @click="addField"><Plus :size="13" />{{ $t('加字段') }}</button></div>
      <div class="ad-field"><span>{{ $t('关系（它被谁依赖）') }}</span>
        <div v-for="(r, i) in outgoing" :key="i" class="ad-row"><span class="ad-arrow">→</span>
          <select v-model="r.to" :aria-label="$t('指向')" @change="s.archDirty()"><option v-for="n in entityNames.filter(n => n !== item.name)" :key="n" :value="n">{{ n }}</option></select>
          <input v-model="r.label" :placeholder="$t('1 → N')" :aria-label="$t('关系说明')" @focus="s.archSnapshot()" @input="s.archDirty()">
          <button class="icon-button" :aria-label="$t('删掉这条关系')" @click="removeRelation(r)"><X :size="13" /></button></div>
        <button class="quiet" :disabled="entityNames.length < 2" @click="addRelation"><Plus :size="13" />{{ $t('加关系') }}</button></div>
      <div v-if="issues.length" class="ad-issues"><p v-for="(i, n) in issues" :key="n" :class="i.level">⚠ {{ i.text }}</p></div>
      <div class="ad-actions"><button class="quiet danger" @click="s.removeEntity(item.id)"><Trash2 :size="14" />{{ $t('删除这类数据') }}</button></div>
    </template>

    <!-- 流程步骤 -->
    <template v-else-if="kind === 'step'">
      <div class="ad-head"><span class="an-type">{{ $t('流程步骤') }}</span><button class="icon-button" :aria-label="$t('关闭')" @click="s.archSelect(null)"><X :size="14" /></button></div>
      <input class="ad-name" v-model="item.name" :aria-label="$t('名称')" @focus="s.archSnapshot()" @input="s.archDirty()">
      <label>{{ $t('说明') }}<input v-model="item.desc" @focus="s.archSnapshot()" @input="s.archDirty()"></label>
      <label>{{ $t('在哪条泳道') }}<select v-model="item.lane" @change="s.archDirty()"><option v-for="l in arch.lanes" :key="l.id" :value="l.id">{{ l.name }}</option></select></label>
      <div class="ad-field"><span>{{ $t('下一步') }}</span>
        <div class="ad-chips"><button v-for="st in arch.steps.filter(x => x.id !== item.id)" :key="st.id" :class="{ on: (item.next || []).includes(st.id) }" @click="toggleNext(st.id)">{{ st.name }}</button></div></div>
      <label>{{ $t('对应的页面') }}<select :value="item.node || ''" @change="linkNode($event.target.value)"><option value="">{{ $t('（不对应页面）') }}</option><option v-for="sc in screenList" :key="sc.id" :value="sc.id">{{ sc.path }}</option></select></label>
      <button v-if="item.node" class="quiet" @click="gotoNode(item.node)">{{ $t('在页面树里看 →') }}</button>
      <div v-if="issues.length" class="ad-issues"><p v-for="(i, n) in issues" :key="n" :class="i.level">⚠ {{ i.text }}</p></div>
      <div class="ad-actions"><button class="quiet danger" @click="s.removeStep(item.id)"><Trash2 :size="14" />{{ $t('删除这一步') }}</button></div>
    </template>

    <!-- 泳道 -->
    <template v-else-if="kind === 'lane'">
      <div class="ad-head"><span class="an-type">{{ $t('泳道') }}</span><button class="icon-button" :aria-label="$t('关闭')" @click="s.archSelect(null)"><X :size="14" /></button></div>
      <input class="ad-name" v-model="item.name" :aria-label="$t('名称')" @focus="s.archSnapshot()" @input="s.archDirty()">
      <label>{{ $t('是什么') }}<select v-model="item.kind" @change="s.archDirty()"><option v-for="(label, k) in LANE_KINDS" :key="k" :value="k">{{ $t(label) }}</option></select></label>
      <label>{{ $t('备注') }}<input v-model="item.note" :placeholder="$t('比如：电脑 / 手机端 · 本次不做')" @focus="s.archSnapshot()" @input="s.archDirty()"></label>
      <p v-if="item.kind === 'skip' || item.kind === 'external'" class="arch-muted">{{ $t('这条泳道不做页面，只生成它产生的数据，后面的页面照样有数据看') }}</p>
      <div class="ad-actions"><button class="quiet danger" :disabled="arch.lanes.length < 2" @click="s.removeLane(item.id)"><Trash2 :size="14" />{{ $t('删除泳道') }}</button></div>
    </template>
  </aside>
</template>
