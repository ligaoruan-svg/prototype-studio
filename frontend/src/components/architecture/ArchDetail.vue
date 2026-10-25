<script setup>
// 右边的详情：选中什么就改什么。打字直接改到页面树里（停手半秒自动保存），开始改一格之前留一份底给「撤销」。
// 改了的地方会记成「还没同步」，点底下的「同步到原型」让 AI 改进原型
import { computed, inject } from 'vue'
import { Trash2, X } from 'lucide-vue-next'
import ArchFieldEdit from './ArchFieldEdit.vue'
import { splitOutside } from '../../lib/archFields.js'
import { ACTIONS, CHILD_TYPES, LAYER_TYPES, NODE_TYPES, findNode, isScreenNode, sameName, targetsIn } from '../../lib/architecture.js'

const s = inject('studio')
const { arch, archSelected, archIssues } = s
const item = computed(() => { void JSON.stringify(archSelected.value); return s.archSelectedItem() })
const kind = computed(() => item.value ? archSelected.value.kind : '')
const parentOf = computed(() => kind.value === 'node' ? findNode(arch.value, item.value.id)?.parents.slice(-1)[0] || null : null)
const typeChoices = computed(() => {
  if (kind.value !== 'node') return []
  const allowed = CHILD_TYPES[parentOf.value?.type || 'root'] || []
  return [...new Set([item.value.type, ...allowed])]
})
const issues = computed(() => archIssues.value.filter(i => item.value && i.node === item.value.id))
const isScreen = computed(() => kind.value === 'node' && isScreenNode(item.value))
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
// 逗号分开的几项（谁用、标签、需求编号、角色）
const listText = (value, sep = '、') => (value || []).join(sep)
function setList(target, key, text, sep = /[,，、;；]/) {
  const values = text.split(sep).map(v => v.trim()).filter(Boolean)
  if (values.length) target[key] = values; else delete target[key]
  s.archDirty()
}
function setText(target, key, value) { if (value) target[key] = value; else delete target[key]; s.archDirty() }
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
      <label>{{ $t('标签') }}<input :value="listText(item.tags, '；')" :placeholder="$t('复用、联动…几条用分号分开')" @focus="s.archSnapshot()" @change="setList(item, 'tags', $event.target.value, /[;；]/)"></label>
      <label>{{ $t('需求编号') }}<input :value="listText(item.req)" placeholder="#85、#86" @focus="s.archSnapshot()" @change="setList(item, 'req', $event.target.value)"></label>
      <div v-if="issues.length" class="ad-issues"><p v-for="(i, n) in issues" :key="n" :class="i.level">{{ i.level === 'error' ? '⚠' : '💡' }} {{ i.text }}</p></div>
      <div class="ad-actions">
        <button class="quiet danger" @click="s.archRemove(item.id)"><Trash2 :size="14" />{{ $t('删除') }}</button>
      </div>
    </template>

  </aside>
</template>
