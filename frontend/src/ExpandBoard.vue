<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowLeft, Hand, Layers, LoaderCircle, RotateCw, Search, AlertCircle } from 'lucide-vue-next'
import { probePage, probeCache } from './probe.js'
import { ORIGIN_LABEL, crumbOf, originOf, pickToSelection, shortLabel, trailOf } from './probeTree.js'
import SceneCard from './SceneCard.vue'

const props = defineProps({ doc: String, width: Number, cacheKey: String, pageName: String, selection: Object, mode: String, focus: [Number, null] })
const emit = defineEmits(['open', 'leave', 'select', 'update:focus'])

const empty = () => ({ title: '', styles: null, page: '', width: props.width || 1150, height: 800, nodes: [], tried: 0, total: 0, current: '' })
const state = ref(empty())        // 画布上正在显示的结果
const progress = ref(empty())     // 正在跑的这一轮
const status = ref('running')     // running | refreshing | done | error
const failure = ref('')
const filter = ref('all'), query = ref('')
let stop = false, round = 0

const title = computed(() => state.value.title || props.pageName || '当前页面')
// 页面本身也是一张卡：静态元素在这里点选，能直接微调
const pageNode = computed(() => state.value.styles && state.value.page ? { id: 0, isPage: true, title: title.value, html: state.value.page, box: null } : null)
const scenes = computed(() => [...(pageNode.value ? [pageNode.value] : []), ...state.value.nodes].map(node => ({ node, origin: originOf(node), crumb: crumbOf(state.value.nodes, node) })))
const groups = computed(() => {
  const counts = {}
  for (const s of scenes.value) counts[s.origin] = (counts[s.origin] || 0) + 1
  return [{ key: 'all', label: '全部视图', count: scenes.value.length }, ...Object.keys(ORIGIN_LABEL).filter(k => counts[k]).map(k => ({ key: k, label: ORIGIN_LABEL[k], count: counts[k] }))]
})
const shown = computed(() => scenes.value.filter(s => (filter.value === 'all' || s.origin === filter.value) && (!query.value.trim() || `${s.node.title} ${s.crumb}`.includes(query.value.trim()))))
const frame = computed(() => ({ w: state.value.width, h: state.value.height }))
const picked = computed(() => props.selection?.card || null)
const focused = computed(() => props.focus == null ? null : scenes.value.find(s => s.node.id === props.focus) || null)
const busy = computed(() => status.value === 'running' || status.value === 'refreshing')

async function run(force = false) {
  stop = false; failure.value = ''
  const mine = ++round
  if (!force && probeCache.has(props.cacheKey)) { state.value = probeCache.get(props.cacheKey); status.value = 'done'; return }
  // 页面改过之后重新展开：旧卡片先留着，新结果整批换上，不让画布闪成一片空白
  const keep = state.value.nodes.length > 0
  status.value = keep ? 'refreshing' : 'running'
  progress.value = empty()
  if (!keep) state.value = empty()
  try {
    const result = await probePage({ doc: props.doc, width: props.width || 1150, height: 800, cancelled: () => stop || mine !== round,
      onUpdate: update => { if (mine !== round) return; progress.value = update; if (!keep) state.value = update } })
    if (stop || mine !== round) return
    state.value = { ...result, current: '' }
    probeCache.set(props.cacheKey, state.value)
    status.value = 'done'
  } catch (e) {
    if (stop || mine !== round) return
    failure.value = e.message || '展开失败'
    status.value = keep ? 'done' : 'error'
  }
}
function open(node) { if (node.isPage) emit('leave'); else emit('open', { ...node, trail: trailOf(state.value.nodes, node) }) }
function pick({ node, items }) {
  if (!items.length) return
  emit('select', { ...pickToSelection(node, items, title.value), trail: node.isPage ? '' : trailOf(state.value.nodes, node) })
}
watch(() => props.cacheKey, () => run(false))
onMounted(() => run())
onUnmounted(() => { stop = true })
</script>
<template>
  <section class="board" aria-label="展开这一页的所有视图">
    <template v-if="focused">
      <div class="focus-head">
        <button type="button" class="quiet" @click="$emit('update:focus', null)"><ArrowLeft :size="15" />返回展开</button>
        <span class="divider"></span>
        <strong>{{ focused.node.title }}</strong>
        <span class="focus-crumb">{{ focused.crumb }}</span>
        <button type="button" class="outline focus-live" @click="open(focused.node)"><Hand :size="14" />交互预览</button>
      </div>
      <div class="focus-content">
        <SceneCard :key="'focus-' + focused.node.id" :node="focused.node" :styles="state.styles" :frame="frame" :picked="picked" :mode="mode" :crumb="focused.crumb" large @pick="pick" />
        <p class="focus-tip">放大后仍可点选或拉框；修改后保持当前视图与目标</p>
      </div>
    </template>
    <template v-else>
      <div class="board-tools">
        <div class="board-heading-wrap">
          <div class="board-heading"><Layers :size="16" /><strong>{{ title }}</strong><span class="board-count">{{ scenes.length }} 个视图</span></div>
          <p v-if="status === 'running'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />正在试「{{ shortLabel(progress.current) || '准备中' }}」· 已试 {{ progress.tried }} / {{ progress.total || '…' }} · 找到 {{ progress.nodes.length }} 个</p>
          <p v-else-if="status === 'refreshing'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />页面改过了，正在重新展开 · 已试 {{ progress.tried }} / {{ progress.total || '…' }}</p>
          <p v-else class="board-sub">点选要改的地方；太小时可放大编辑</p>
        </div>
        <div class="board-control">
          <label class="search"><Search :size="14" /><input v-model="query" type="search" placeholder="查找弹窗" aria-label="查找弹窗"></label>
          <button type="button" class="icon-button refresh" :disabled="busy" title="重新展开当前页面" aria-label="重新展开当前页面" @click="run(true)"><RotateCw :size="15" :class="{ spin: busy }" /></button>
        </div>
      </div>
      <div class="board-filter" role="tablist" aria-label="按来源筛选">
        <button v-for="g in groups" :key="g.key" type="button" role="tab" :aria-selected="filter === g.key" :class="{ active: filter === g.key }" @click="filter = g.key">{{ g.label }}<span>{{ g.count }}</span></button>
      </div>
      <div v-if="status === 'error'" class="board-error"><AlertCircle :size="15" /><span>{{ failure }}，可以点右上角的刷新再试一次。</span></div>
      <div class="board-scroll">
        <div class="board-grid">
          <SceneCard v-for="s in shown" :key="s.node.id" :node="s.node" :styles="state.styles" :frame="frame" :picked="picked" :mode="mode" :crumb="s.crumb" @pick="pick" @open="open" @focus="$emit('update:focus', $event.id)" />
          <div v-if="status === 'running'" class="scene-ghost" aria-hidden="true"><span></span><span></span><span></span></div>
          <div v-if="status !== 'running' && !shown.length" class="empty-board">
            <template v-if="query || filter !== 'all'"><Search :size="22" /><h3>没有找到对应视图</h3><p>试试其他名称，或者清空当前筛选。</p><button type="button" class="outline" @click="query = ''; filter = 'all'">清空筛选</button></template>
            <template v-else><h3>这一页没有点出弹窗</h3><p>如果弹窗要先切到某个页签、选中某一行才出现，先在预览里切过去，再点右上角的刷新。</p></template>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>
<style scoped>
.board{flex:1;min-height:240px;display:flex;flex-direction:column;border:1px solid #e5e1df;border-radius:13px;background:var(--canvas);overflow:hidden}
.board-tools{flex-shrink:0;display:flex;align-items:center;gap:12px;padding:15px 18px 12px}
.board-heading-wrap{min-width:0;flex:1}
.board-heading{display:flex;align-items:center;gap:8px;min-width:0}
.board-heading svg{color:var(--primary);flex-shrink:0}
.board-heading strong{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.board-count{flex-shrink:0;font-size:11px;color:var(--muted);background:var(--quiet);border:1px solid var(--line);border-radius:20px;padding:1px 8px}
.board-sub{margin-top:3px;font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.board-sub.live{display:flex;align-items:center;gap:6px;color:var(--primary)}
.board-control{display:flex;align-items:center;gap:8px;flex-shrink:0}
.search{display:flex;align-items:center;gap:6px;height:32px;padding:0 9px;background:#fff;border:1px solid var(--line);border-radius:8px;color:var(--muted)}
.search input{width:130px;border:0;padding:0;background:none;font-size:12px;outline-offset:4px}
.board-control .refresh{width:32px;height:32px;background:#fff;border:1px solid var(--line);border-radius:8px}
.board-filter{display:flex;gap:6px;padding:0 18px 12px;flex-shrink:0;overflow-x:auto;scrollbar-width:none}
.board-filter button{gap:6px;font-size:12px;padding:4px 11px;border:1px solid transparent;border-radius:20px;color:var(--muted)}
.board-filter button span{font-variant-numeric:tabular-nums;opacity:.8}
.board-filter button:hover{background:#fff}
.board-filter button.active{color:var(--primary);background:#fff;border-color:#e1cabd}
.board-error{display:flex;align-items:center;gap:8px;margin:0 18px 12px;padding:9px 12px;border-radius:9px;background:var(--danger-bg);color:var(--danger);font-size:12.5px}
.board-scroll{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:0 18px 90px;scrollbar-width:thin}
.board-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;align-items:start}
.empty-board{grid-column:1/-1;padding:56px 20px;text-align:center;color:var(--muted);line-height:2;display:flex;flex-direction:column;align-items:center;gap:2px}
.empty-board h3{font-size:15px;color:var(--ink)}
.empty-board p{font-size:13px;max-width:420px;margin-bottom:10px}
.empty-board .outline{font-size:12px;padding:6px 12px;border:1px solid var(--line);border-radius:9px;background:#fff}
.scene-ghost{display:flex;flex-direction:column;gap:10px;padding:12px;background:#fff;border:1px solid var(--line);border-radius:12px}
.scene-ghost span{display:block;border-radius:8px;background:linear-gradient(90deg,#efece4 0,#f7f5ef 50%,#efece4 100%);background-size:200% 100%;animation:shimmer 1.3s linear infinite}
.scene-ghost span:nth-child(1){height:16px;width:45%}.scene-ghost span:nth-child(2){height:12px;width:70%}.scene-ghost span:nth-child(3){height:170px}
@keyframes shimmer{to{background-position:-200% 0}}
.focus-head{display:flex;align-items:center;gap:10px;padding:11px 18px;background:#fff;border-bottom:1px solid var(--line);flex-shrink:0;min-width:0}
.focus-head .quiet{gap:6px;font-size:12px;padding:5px 8px;border-radius:8px}
.focus-head .quiet:hover{background:var(--quiet)}
.divider{width:1px;height:18px;background:var(--line);flex-shrink:0}
.focus-head strong{font-size:14px;white-space:nowrap}
.focus-crumb{flex:1;min-width:0;font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.focus-live{gap:6px;font-size:12px;padding:6px 11px;border:1px solid var(--line);border-radius:9px;background:#fff}
.focus-content{flex:1;min-height:0;overflow:auto;padding:28px 24px 96px}
.focus-tip{text-align:center;font-size:12px;color:var(--muted);margin-top:18px}
@media (prefers-reduced-motion: reduce){.scene-ghost span{animation:none}}
</style>
