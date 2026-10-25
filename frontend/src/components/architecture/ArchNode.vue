<script setup>
// 页面树里的一个节点和它下面的全部：卡片 + 往右长出去的子节点。选中时卡片上方出现工具条（加子项、加同级、上移下移、删除）
import { computed, inject } from 'vue'
import { ChevronDown, ChevronRight, ChevronUp, Plus, Trash2 } from 'lucide-vue-next'
import ArchNode from './ArchNode.vue'
import { CHILD_TYPES, NODE_TYPES, countBelow } from '../../lib/architecture.js'

const props = defineProps({ node: Object })
const s = inject('studio')
const { archSelected, archShowDesc, archQuery, archIssues } = s
const selected = computed(() => archSelected.value?.kind === 'node' && archSelected.value.id === props.node.id)
const kids = computed(() => props.node.children || [])
const childTypes = computed(() => CHILD_TYPES[props.node.type] || [])
const hidden = computed(() => countBelow(props.node))
const hit = computed(() => {
  const q = archQuery.value.trim()
  return !!q && (props.node.name.includes(q) || (props.node.desc || '').includes(q))
})
const warn = computed(() => archIssues.value.filter(i => i.node === props.node.id))
const chips = computed(() => [
  ...(props.node.data || []).map(d => ({ kind: 'data', text: '↗ ' + d })),
  ...(props.node.tags || []).map(d => ({ kind: 'tag', text: d })),
  ...(props.node.req || []).map(d => ({ kind: 'req', text: d })),
])
function addChild(event) {
  const type = event.target.value
  event.target.value = ''
  if (type) s.archAdd(props.node.id, type)
}
</script>

<template>
  <div class="an-row">
    <div class="an-card" :class="[node.type, { selected, hit, leaf: !kids.length, warn: warn.some(w => w.level === 'error') }]" @click.stop="s.archSelect('node', node.id)">
      <div class="an-head"><span class="an-type">{{ $t(NODE_TYPES[node.type].short) }}</span><b>{{ node.name }}</b>
        <span v-if="node.route" class="an-route">#{{ node.route }}</span>
        <span v-if="node.who?.length" class="an-who">{{ node.who.join('·') }}</span>
        <button v-if="kids.length" class="an-fold" :title="node.collapsed ? $t('展开') : $t('收起')" :aria-label="node.collapsed ? $t('展开') : $t('收起')" @click.stop="s.archToggle(node.id)"><ChevronRight v-if="node.collapsed" :size="13" /><ChevronDown v-else :size="13" /></button></div>
      <p v-if="archShowDesc && node.desc" class="an-desc">{{ node.desc }}</p>
      <p v-if="node.type === 'drill' && archShowDesc && node.entry" class="an-entry">{{ $t('从哪进：{0}', [node.entry]) }}</p>
      <div v-if="chips.length" class="an-chips"><span v-for="c in chips" :key="c.kind + c.text" class="an-chip" :class="c.kind">{{ c.text }}</span></div>
      <span v-if="warn.length" class="an-warn" :title="warn.map(w => w.text).join('\n')">⚠ {{ warn.length }}</span>
      <div v-if="selected" class="an-tools" @click.stop>
        <label v-if="childTypes.length" class="an-add"><Plus :size="12" />{{ $t('子项') }}<select :aria-label="$t('加子项')" @change="addChild"><option value="">{{ $t('加什么') }}</option><option v-for="t in childTypes" :key="t" :value="t">{{ $t(NODE_TYPES[t].label) }}</option></select></label>
        <button @click="s.archSibling(node.id)"><Plus :size="12" />{{ $t('同级') }}</button>
        <button :title="$t('上移')" :aria-label="$t('上移')" @click="s.archMove(node.id, -1)"><ChevronUp :size="13" /></button>
        <button :title="$t('下移')" :aria-label="$t('下移')" @click="s.archMove(node.id, 1)"><ChevronDown :size="13" /></button>
        <button class="danger" @click="s.archRemove(node.id)"><Trash2 :size="12" />{{ $t('删除') }}</button>
      </div>
    </div>
    <div v-if="kids.length && !node.collapsed" class="an-kids"><div v-for="child in kids" :key="child.id" class="an-kid"><ArchNode :node="child" /></div></div>
    <button v-else-if="kids.length" class="an-folded" @click.stop="s.archToggle(node.id)">{{ $t('▸ {0} 项', [hidden]) }}</button>
  </div>
</template>
