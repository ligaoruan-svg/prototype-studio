<script setup>
// 业务流程：一条泳道一个角色（或系统、不做的端、外部系统），步骤按箭头从左往右排
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Plus } from 'lucide-vue-next'
import { LANE_KINDS, connector, layoutFlow } from '../../lib/architecture.js'

const s = inject('studio')
const { arch, archSelected, archIssues } = s
const layout = computed(() => layoutFlow(arch.value))
const box = ref(null), rects = ref({}), size = ref({ w: 0, h: 0 })
const cards = {}
const setCard = id => el => { if (el) cards[id] = el; else delete cards[id] }
function measure() {
  if (!box.value) return
  const out = {}
  for (const [id, el] of Object.entries(cards)) out[id] = { x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight }
  rects.value = out
  size.value = { w: box.value.scrollWidth, h: box.value.scrollHeight }
}
const edges = computed(() => layout.value.edges.map(e => connector(rects.value[e.from], rects.value[e.to])).filter(Boolean))
const laneOf = id => arch.value.lanes.find(l => l.id === id)
const dashed = step => ['skip', 'external'].includes(laneOf(step.lane)?.kind)
const isSel = (kind, id) => archSelected.value?.kind === kind && archSelected.value.id === id
const warnOf = id => archIssues.value.filter(i => i.step === id)
let observer = null
onMounted(() => { nextTick(measure); observer = new ResizeObserver(() => measure()); if (box.value) observer.observe(box.value) })
onUnmounted(() => observer?.disconnect())
watch(() => JSON.stringify([arch.value?.steps, arch.value?.lanes]), () => nextTick(measure))
</script>

<template>
  <div class="af-wrap">
    <p class="arch-hint">{{ $t('虚线泳道是本次不做的端或外部系统：不做页面，只生成它们产生的数据。点步骤可以改名、换泳道、连下一步') }}</p>
    <div ref="box" class="af-board" :style="{ '--af-cols': layout.columns, '--af-rows': arch.lanes.length || 1 }">
      <svg class="ad-lines" :width="size.w" :height="size.h" aria-hidden="true">
        <defs><marker id="af-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#8a7f78" /></marker></defs>
        <path v-for="(d, i) in edges" :key="i" :d="d" fill="none" stroke="#a39890" stroke-width="1.5" marker-end="url(#af-arrow)" />
      </svg>
      <template v-for="(lane, li) in arch.lanes" :key="lane.id">
        <div class="af-lane-bg" :class="lane.kind" :style="{ gridRow: li + 1 }"></div>
        <button class="af-lane" :class="[lane.kind, { selected: isSel('lane', lane.id) }]" :style="{ gridRow: li + 1 }" @click.stop="s.archSelect('lane', lane.id)"><b>{{ lane.name }}</b><small>{{ lane.note || $t(LANE_KINDS[lane.kind]) }}</small></button>
        <button class="af-add-step" :style="{ gridRow: li + 1, gridColumn: layout.columns + 2 }" :title="$t('在这条泳道加一步')" :aria-label="$t('在这条泳道加一步')" @click.stop="s.addStep(lane.id)"><Plus :size="14" /></button>
      </template>
      <button v-for="c in layout.cells" :key="c.step.id" :ref="setCard(c.step.id)" class="af-step" :class="{ dashed: dashed(c.step), selected: isSel('step', c.step.id), linked: !!c.step.node, warn: warnOf(c.step.id).length }" :style="{ gridRow: c.row + 1, gridColumn: c.col + 2 }" @click.stop="s.archSelect('step', c.step.id)">
        <b>{{ c.step.name }}</b><small v-if="c.step.desc">{{ c.step.desc }}</small></button>
    </div>
    <button class="ad-add" @click.stop="s.addLane()"><Plus :size="14" />{{ $t('加一条泳道') }}</button>
  </div>
</template>
