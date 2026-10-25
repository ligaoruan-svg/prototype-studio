<script setup>
// 数据关系：被依赖的数据在左边一列，依赖它的往右排；连线是引用关系（写了关系用关系的说法，没写就用字段名）
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Plus } from 'lucide-vue-next'
import { FIELD_MARKS, connector, layoutData } from '../../lib/architecture.js'

const s = inject('studio')
const { arch, archSelected, archIssues } = s
const layout = computed(() => layoutData(arch.value))
const box = ref(null), rects = ref({}), size = ref({ w: 0, h: 0 })
const cards = {}
const setCard = name => el => { if (el) cards[name] = el; else delete cards[name] }
function measure() {
  if (!box.value) return
  const out = {}
  for (const [name, el] of Object.entries(cards)) out[name] = { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight }
  rects.value = out
  size.value = { w: box.value.scrollWidth, h: box.value.scrollHeight }
}
const edges = computed(() => layout.value.edges.map(e => {
  const a = rects.value[e.from], b = rects.value[e.to]
  if (!a || !b) return null
  const forward = Math.abs(a.x - b.x) >= 20
  const lx = forward ? ((b.x > a.x ? a.x + a.w : a.x) + (b.x > a.x ? b.x : b.x + b.w)) / 2 : a.x + a.w / 2 + 8
  const ly = forward ? (a.y + a.h / 2 + b.y + b.h / 2) / 2 : (a.y + b.y + a.h) / 2
  return { ...e, d: connector(a, b), lx, ly, lw: Math.min(150, 14 + [...e.label].reduce((n, c) => n + (c.charCodeAt(0) > 0x2e80 ? 11 : 6.5), 0)) }
}).filter(Boolean))
const selected = name => archSelected.value?.kind === 'entity' && arch.value.entities.find(e => e.id === archSelected.value.id)?.name === name
const warnOf = id => archIssues.value.filter(i => i.entity === id)
let observer = null
onMounted(() => { nextTick(measure); observer = new ResizeObserver(() => measure()); if (box.value) observer.observe(box.value) })
onUnmounted(() => observer?.disconnect())
watch(() => JSON.stringify([arch.value?.entities, arch.value?.relations]), () => nextTick(measure))
</script>

<template>
  <div class="ad-wrap">
    <p class="arch-hint">{{ $t('所有页面共用这一份数据。箭头从被依赖的数据指向依赖它的；🔑 编号、↗ 引用、ƒ 自动算、🔒 继承不能改') }}</p>
    <div ref="box" class="ad-board">
      <svg class="ad-lines" :width="size.w" :height="size.h" aria-hidden="true">
        <defs><marker id="ad-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#a39890" /></marker></defs>
        <path v-for="(e, i) in edges" :key="'p' + i" :d="e.d" fill="none" stroke="#b9ada3" stroke-width="1.5" marker-end="url(#ad-arrow)" />
        <g v-for="(e, i) in edges" :key="'l' + i"><template v-if="e.label"><rect :x="e.lx - e.lw / 2" :y="e.ly - 10" :width="e.lw" height="19" rx="9" fill="#efe9e3" /><text :x="e.lx" :y="e.ly + 4" text-anchor="middle" font-size="11" fill="#6b625c">{{ e.label.length > 22 ? e.label.slice(0, 21) + '…' : e.label }}</text></template></g>
      </svg>
      <div v-for="(col, ci) in layout.columns" :key="ci" class="ad-col">
        <article v-for="e in col" :key="e.id" :ref="setCard(e.name)" class="ad-card" :class="{ selected: selected(e.name), external: e.external, warn: warnOf(e.id).some(w => w.level === 'error') }" @click.stop="s.archSelect('entity', e.id)">
          <header><b>{{ e.name }}</b><span v-if="e.code" class="ad-code">{{ e.code }}</span><span v-if="e.external" class="ad-role">{{ $t('外部系统') }}</span><span v-else-if="e.role" class="ad-role">{{ e.role }}</span></header>
          <ul><li v-for="f in e.fields" :key="f.name" :class="f.kind"><i>{{ FIELD_MARKS[f.kind] }}</i><span>{{ f.name }}</span><small v-if="f.kind === 'ref' && f.ref">{{ f.ref }}{{ f.note ? ' · ' + f.note : '' }}</small><small v-else-if="f.note">{{ f.note }}</small></li></ul>
          <footer v-if="e.states?.length"><span v-for="(st, i) in e.states" :key="st">{{ st }}<em v-if="i < e.states.length - 1">→</em></span></footer>
          <span v-if="warnOf(e.id).length" class="an-warn" :title="warnOf(e.id).map(w => w.text).join('\n')">⚠ {{ warnOf(e.id).length }}</span>
        </article>
      </div>
      <button class="ad-add" @click.stop="s.addEntity()"><Plus :size="14" />{{ $t('加一类数据') }}</button>
    </div>
  </div>
</template>
