<script setup>
// 页面结构：一次只看一个页面，按页面从上到下的样子排开——区块、表格、按钮、按钮打开的弹窗和弹窗里的字段。
// 左边是全部页面（按模块分组），点哪个看哪个；页面树里选中的节点在哪一页，这里就先打开哪一页
import { computed, inject, nextTick, ref, watch } from 'vue'
import { Plus } from 'lucide-vue-next'
import ArchBlock from './ArchBlock.vue'
import { CHILD_TYPES, NODE_TYPES, findNode, screenOf, screens, walk } from '../../lib/architecture.js'

const s = inject('studio')
const { arch, archSelected } = s
const list = computed(() => screens(arch.value))
const groups = computed(() => {
  const out = []
  for (const sc of list.value) {
    const last = out[out.length - 1]
    if (last && last.module === sc.module) last.items.push(sc)
    else out.push({ module: sc.module, items: [sc] })
  }
  return out
})
const currentId = ref('')
// 选中的东西在哪一页，就看哪一页；没选就看第一页
watch([() => archSelected.value?.id, list], () => {
  const sel = archSelected.value?.kind === 'node' ? screenOf(arch.value, archSelected.value.id) : null
  if (sel) currentId.value = sel.id
  else if (!list.value.some(x => x.id === currentId.value)) currentId.value = list.value[0]?.id || ''
}, { immediate: true })
const current = computed(() => findNode(arch.value, currentId.value)?.node || null)
const crumb = computed(() => {
  const hit = current.value && findNode(arch.value, current.value.id)
  return hit ? hit.parents.map(p => p.name).join(' › ') : ''
})
const box = ref(null)
// 点「打开「xx」」：选中那个弹窗，滚到它那儿
function goto(name) {
  if (!current.value) return
  const target = [...walk(current.value.children)].map(x => x.node).find(n => n.name === name)
    || [...walk(arch.value.nodes)].map(x => x.node).find(n => n.name === name)
  if (!target) return
  s.archSelect('node', target.id)
  nextTick(() => box.value?.querySelector(`[data-node="${target.id}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }))
}
function pickPage(id) { currentId.value = id; s.archSelect('node', id) }
const kidTypes = computed(() => CHILD_TYPES[current.value?.type] || [])
function addChild(event) { const type = event.target.value; event.target.value = ''; if (type && current.value) s.archAdd(current.value.id, type) }
</script>

<template>
  <div class="ap-wrap" @click.stop>
    <nav class="ap-list" :aria-label="$t('页面')">
      <template v-for="g in groups" :key="g.module"><p class="ap-module">{{ g.module || $t('其他页面') }}</p>
        <button v-for="sc in g.items" :key="sc.id" :class="{ active: sc.id === currentId }" @click="pickPage(sc.id)"><span>{{ sc.name }}</span><small v-if="sc.tabs.length">{{ $t('{0} 页签', [sc.tabs.length]) }}</small></button></template>
      <p v-if="!list.length" class="arch-muted">{{ $t('还没有页面') }}</p>
    </nav>
    <section v-if="current" ref="box" class="ap-main">
      <header class="ap-head" @click="s.archSelect('node', current.id)">
        <p class="arch-muted">{{ crumb }}</p>
        <h3><span class="an-type">{{ $t(NODE_TYPES[current.type].short) }}</span>{{ current.name }}</h3>
        <p v-if="current.desc">{{ current.desc }}</p>
        <p class="ap-nav"><span v-if="current.entry">{{ $t('从哪进：{0}', [current.entry]) }}</span><span v-if="current.params">{{ $t('带过去：{0}', [current.params]) }}</span><span v-if="current.back">{{ $t('怎么回去：{0}', [current.back]) }}</span><span v-if="current.route">#{{ current.route }}</span></p>
      </header>
      <div class="ap-body">
        <ArchBlock v-for="child in current.children" :key="child.id" :node="child" @goto="goto" />
        <p v-if="!current.children?.length" class="arch-muted">{{ $t('这一页还没拆：加区块、表格、按钮，写清每个按钮点了打开什么') }}</p>
        <label class="ap-add"><Plus :size="13" />{{ $t('往这一页加') }}<select :aria-label="$t('往这一页加')" @change="addChild"><option value="">{{ $t('加什么') }}</option><option v-for="t in kidTypes" :key="t" :value="t">{{ $t(NODE_TYPES[t].label) }}</option></select></label>
      </div>
    </section>
  </div>
</template>
