<script setup>
// 页面树里的一个节点和它下面的全部：卡片 + 往右长出去的子节点。选中时卡片上方出现工具条（加子项、加同级、上移下移、删除）
import { computed, inject, nextTick, ref, watch } from 'vue'
import { ChevronDown, ChevronRight, ChevronUp, Plus, Sparkles, Trash2 } from 'lucide-vue-next'
import ArchNode from './ArchNode.vue'
import { ACTIONS, CHILD_TYPES, LAYER_TYPES, NODE_TYPES, countBelow, protoState } from '../../lib/architecture.js'
import ArchFields from './ArchFields.vue'

const props = defineProps({ node: Object, depth: { type: Number, default: 0 }, siblings: { type: Array, default: () => [] }, parentState: { type: String, default: 'in' } })
const s = inject('studio')
const { archSelected, archShowDesc, archShowFields, archQuery, archIssues, archRenaming, archExpand, archLevel, archFlash } = s
// 和原型对不对得上：虚线 = 你规划了、原型里还没有；淡掉 = 原型里已经没有。只在最上面那一层标字（下面的跟着虚线就够了）
const state = computed(() => protoState(props.node))
const tagged = computed(() => state.value !== 'in' && state.value !== props.parentState)
// 改过、还没同步到原型的（改名、改字段、挪了位置）：卡片右上角一个小点
const changed = computed(() => s.archChanges.value.some(c => c.id === props.node.id && c.kind !== 'add'))
// 弹窗、抽屉、向导、区块、表格：卡片里带上字段 / 列
const hasForm = computed(() => [...LAYER_TYPES, 'block', 'table'].includes(props.node.type))
// 搜索时，命中的节点上面几层自动展开
const hasHit = node => !!archQuery.value.trim() && [...(node.children || [])].some(c => c.name.includes(archQuery.value.trim()) || hasHit(c))
const open = computed(() => { void archExpand.value; void archLevel.value; return hasHit(props.node) || s.nodeOpen(props.node, props.depth) })
// 点卡片：选中它，还没展开的顺便往下展开一层
function pick() {
  s.archSelect('node', props.node.id)
  if (kids.value.length && !open.value) s.openNode(props.node, props.depth, props.siblings, true)
}
// 原地改名：双击卡片、按 F2，或者回车 / Tab 刚加出来的那一个
const renaming = computed(() => archRenaming.value === props.node.id)
const nameInput = ref(null)
watch(renaming, on => { if (on) nextTick(() => { nameInput.value?.focus(); nameInput.value?.select() }) }, { immediate: true })
function commitName(event) { if (renaming.value) s.renameNode(props.node.id, event.target.value) }
function cancelName() { archRenaming.value = '' }
const selected = computed(() => archSelected.value?.kind === 'node' && archSelected.value.id === props.node.id)
const kids = computed(() => props.node.children || [])
const childTypes = computed(() => CHILD_TYPES[props.node.type] || [])
const hidden = computed(() => countBelow(props.node))
const hit = computed(() => {
  const q = archQuery.value.trim()
  return !!q && (props.node.name.includes(q) || (props.node.desc || '').includes(q))
})
const warn = computed(() => archIssues.value.filter(i => i.node === props.node.id))
// 卡片上只留一行小字：地址 · 谁用 · 需求编号；标签这些在右边详情里看（用到哪些数据是内部的，不放卡片上）
const meta = computed(() => [props.node.route ? '#' + props.node.route : '', (props.node.who || []).join('·'), (props.node.req || []).join(' ')].filter(Boolean).join(' · '))
function addChild(event) {
  const type = event.target.value
  event.target.value = ''
  if (type) s.archAdd(props.node.id, type)
}
</script>

<template>
  <div class="an-row">
    <div class="an-card" :class="[node.type, state, { selected, hit, leaf: !kids.length, form: hasForm, flash: archFlash.has(node.id), changed, warn: warn.some(w => w.level === 'error') }]" @click.stop="pick" @dblclick.stop="archRenaming = node.id">
      <div class="an-head"><span class="an-type">{{ $t(NODE_TYPES[node.type].short) }}</span><input v-if="renaming" ref="nameInput" class="an-rename" :value="node.name" :aria-label="$t('名称')" @click.stop @keydown.enter.prevent="commitName" @keydown.esc.stop.prevent="cancelName" @blur="commitName"><b v-else>{{ node.name }}</b>
        <button v-if="kids.length" class="an-fold" :title="open ? $t('收起') : $t('展开')" :aria-label="open ? $t('收起') : $t('展开')" @click.stop="s.openNode(node, depth, siblings)"><ChevronDown v-if="open" :size="13" /><ChevronRight v-else :size="13" /></button></div>
      <p v-if="tagged" class="an-proto" @click.stop><span>{{ state === 'planned' ? $t('原型里还没有') : $t('原型里已经没有') }}</span>
        <button v-if="state === 'planned'" class="quiet" :title="$t('把话填进输入框、切到「自动」，你看一眼再发')" @click="s.makeInPrototype(node)"><Sparkles :size="11" />{{ $t('让 AI 做出来') }}</button></p>
      <p v-if="archShowDesc && node.desc" class="an-desc">{{ node.desc }}</p>
      <p v-if="node.type === 'drill' && archShowDesc && node.entry" class="an-entry">{{ $t('从哪进：{0}', [node.entry]) }}</p>
      <p v-if="node.action" class="an-act" :class="node.action">↳ {{ $t(ACTIONS[node.action]) }}<template v-if="node.target">「{{ node.target }}」</template></p>
      <p v-if="node.when" class="an-when">{{ $t('出现：{0}', [node.when]) }}</p>
      <ArchFields v-if="hasForm" :node="node" :open="archShowFields" @click.stop @edit="s.archSelect('node', node.id)" />
      <p v-if="meta" class="an-meta">{{ meta }}</p>
      <!-- 卡片上只标要改的；建议（还没写介绍这类）不影响生成，在右边详情和「建议」里看 -->
      <span v-if="warn.some(w => w.level === 'error')" class="an-warn" :title="warn.filter(w => w.level === 'error').map(w => w.text).join('\n')">⚠ {{ warn.filter(w => w.level === 'error').length }}</span>
      <div v-if="selected" class="an-tools" @click.stop>
        <label v-if="childTypes.length" class="an-add"><Plus :size="12" />{{ $t('子项') }}<select :aria-label="$t('加子项')" @change="addChild"><option value="">{{ $t('加什么') }}</option><option v-for="t in childTypes" :key="t" :value="t">{{ $t(NODE_TYPES[t].label) }}</option></select></label>
        <button @click="s.archSibling(node.id)"><Plus :size="12" />{{ $t('同级') }}</button>
        <button :title="$t('上移')" :aria-label="$t('上移')" @click="s.archMove(node.id, -1)"><ChevronUp :size="13" /></button>
        <button :title="$t('下移')" :aria-label="$t('下移')" @click="s.archMove(node.id, 1)"><ChevronDown :size="13" /></button>
        <button class="danger" @click="s.archRemove(node.id)"><Trash2 :size="12" />{{ $t('删除') }}</button>
      </div>
    </div>
    <div v-if="kids.length && open" class="an-kids"><div v-for="child in kids" :key="child.id" class="an-kid"><ArchNode :node="child" :depth="depth + 1" :siblings="kids" :parent-state="state" /></div></div>
    <button v-else-if="kids.length" class="an-folded" @click.stop="s.openNode(node, depth, siblings, true)">{{ $t('▸ {0} 项', [hidden]) }}</button>
  </div>
</template>
