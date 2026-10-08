<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Layers, LoaderCircle, RotateCw, X, AlertCircle } from 'lucide-vue-next'
import { probePage, probeCache } from './probe.js'
import { buildTree, cardDocument, pickToSelection, shortLabel, thumbFrame, trailOf } from './probeTree.js'
import BoardNode from './BoardNode.vue'

const props = defineProps({ doc: String, width: Number, cacheKey: String, pageName: String, selection: Object })
const emit = defineEmits(['open', 'close', 'select'])

const empty = () => ({ title: '', styles: null, page: '', width: props.width || 1150, height: 800, nodes: [], tried: 0, total: 0, current: '' })
const state = ref(empty())        // 画布上正在显示的结果
const progress = ref(empty())     // 正在跑的这一轮
const status = ref('running')     // running | refreshing | done | error
const failure = ref('')
let stop = false, round = 0

// 卡片大小：小档一眼看全，中、大档方便直接在卡片里点选
const SIZES = { s: 264, m: 420, l: 620 }
const size = ref((() => { try { return localStorage.getItem('pf-board-size') || 'm' } catch { return 'm' } })())
watch(size, value => { try { localStorage.setItem('pf-board-size', value) } catch {} })
const cardWidth = computed(() => SIZES[size.value] || SIZES.m)

const tree = computed(() => buildTree(state.value.nodes))
const frame = computed(() => ({ w: state.value.width, h: state.value.height }))
const pageDoc = computed(() => state.value.styles && state.value.page ? cardDocument(state.value.styles, state.value.page) : '')
const pageThumb = computed(() => thumbFrame({ x: 0, y: 0, w: state.value.width, h: state.value.height }, 300, 260))
const picked = computed(() => props.selection?.card || null)
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
function open(node) { emit('open', { ...node, trail: trailOf(state.value.nodes, node) }) }
function pick({ node, items }) {
  if (!items.length) return
  emit('select', { ...pickToSelection(node, items), trail: trailOf(state.value.nodes, node) })
}
watch(() => props.cacheKey, () => run(false))
onMounted(() => run())
onUnmounted(() => { stop = true })
</script>
<template>
  <section class="board" aria-label="展开这一页的弹窗">
    <header class="board-head">
      <div class="board-title"><Layers :size="16" /><strong>{{ state.title || pageName || '当前页面' }}</strong><span v-if="status === 'done'" class="board-count">{{ state.nodes.length }} 个弹窗</span></div>
      <p v-if="status === 'running'" class="board-status" aria-live="polite"><LoaderCircle :size="13" class="spin" />正在试「{{ shortLabel(progress.current) || '准备中' }}」<span>已试 {{ progress.tried }} / {{ progress.total || '…' }} · 找到 {{ progress.nodes.length }} 个</span></p>
      <p v-else-if="status === 'refreshing'" class="board-status" aria-live="polite"><LoaderCircle :size="13" class="spin" />页面改过了，正在重新展开<span>已试 {{ progress.tried }} / {{ progress.total || '…' }}</span></p>
      <p v-else-if="status === 'done'" class="board-status quiet-text">直接在卡片里点选要改的地方，按住 Shift 可多选；改完卡片会自动更新</p>
      <div class="board-actions">
        <div class="board-size" role="group" aria-label="卡片大小"><button v-for="(label, key) in { s: '小', m: '中', l: '大' }" :key="key" type="button" :class="{ active: size === key }" :aria-pressed="size === key" @click="size = key">{{ label }}</button></div>
        <button type="button" class="quiet" :disabled="busy" @click="run(true)"><RotateCw :size="14" />重新查找</button>
        <button type="button" class="icon-button" aria-label="收起展开视图" title="收起 · E" @click="$emit('close')"><X :size="16" /></button>
      </div>
    </header>
    <div v-if="status === 'error'" class="board-error"><AlertCircle :size="15" /><span>{{ failure }}，可以点「重新查找」再试一次。</span></div>
    <div class="board-body">
      <div class="board-root">
        <button type="button" class="board-page" title="回到预览" @click="$emit('close')">
          <span class="thumb" :style="{ height: pageThumb.height + 'px' }">
            <iframe v-if="pageDoc" sandbox="" tabindex="-1" aria-hidden="true" :srcdoc="pageDoc" :style="{ width: frame.w + 'px', height: frame.h + 'px', transform: pageThumb.transform }"></iframe>
          </span>
          <span class="card-title">{{ state.title || pageName || '当前页面' }}</span>
          <small>页面本身</small>
        </button>
      </div>
      <div class="board-branches">
        <BoardNode v-for="node in tree" :key="node.id" :node="node" :styles="state.styles" :frame="frame" :card-width="cardWidth" :picked="picked" @open="open" @pick="pick" />
        <div v-if="status === 'running'" class="board-ghost" aria-hidden="true"><span></span><span></span></div>
        <p v-if="status === 'done' && !state.nodes.length" class="board-empty">这一页没有点出弹窗。如果弹窗要先切到某个页签、选中某一行才出现，先在预览里切过去，再点「重新查找」。</p>
      </div>
    </div>
  </section>
</template>
<style scoped>
.board{flex:1;min-height:240px;display:flex;flex-direction:column;border:1px solid #e5e1df;border-radius:13px;background:var(--shell);overflow:hidden}
.board-head{display:flex;align-items:center;gap:14px;padding:12px 14px 12px 16px;background:#fff;border-bottom:1px solid var(--line)}
.board-title{display:flex;align-items:center;gap:8px;min-width:0;flex:0 1 auto;color:var(--ink)}
.board-title svg{color:var(--primary)}
.board-title strong{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.board-count{font-size:12px;color:var(--muted);padding:2px 8px;border-radius:999px;background:var(--quiet);white-space:nowrap;flex-shrink:0}
.board-status{flex:1 1 0;display:flex;align-items:center;gap:6px;min-width:0;font-size:12px;color:var(--primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.board-status span{color:var(--muted);margin-left:4px}
.board-status.quiet-text{display:block;color:var(--muted)}
.board-actions{display:flex;align-items:center;gap:4px;margin-left:auto}
.board-actions .quiet{font-size:12px;padding:6px 9px;border-radius:9px}
.board-actions .quiet:hover:not(:disabled){background:var(--quiet)}
.board-error{display:flex;align-items:center;gap:8px;margin:12px 16px 0;padding:9px 12px;border-radius:9px;background:var(--danger-bg);color:var(--danger);font-size:12.5px}
.board-body{flex:1;min-height:0;overflow:auto;display:flex;align-items:flex-start;gap:22px;padding:22px 22px 90px}
.board-root{position:sticky;left:0;top:0;z-index:1;flex-shrink:0}
.board-page{display:flex;flex-direction:column;align-items:stretch;gap:6px;width:316px;padding:8px 8px 10px;background:#fff;border:1px solid var(--line);border-radius:13px;text-align:left;box-shadow:0 4px 14px #3722170d}
.board-page:hover{border-color:#d6cfc4}
.board-page small{padding:0 3px;font-size:11.5px;color:var(--muted)}
.thumb{display:block;position:relative;overflow:hidden;border-radius:8px;background:var(--quiet)}
.thumb iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0;pointer-events:none}
.card-title{padding:0 3px;font-size:13px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.board-branches{display:flex;flex-direction:column;gap:18px;padding-left:16px;border-left:1.5px solid var(--line);min-width:0}
.board-empty{max-width:420px;font-size:12.5px;line-height:1.75;color:var(--muted);padding:8px 2px}
.board-ghost{display:flex;gap:10px;align-items:flex-start}
.board-ghost span{display:block;border-radius:12px;background:linear-gradient(90deg,#efece4 0,#f7f5ef 50%,#efece4 100%);background-size:200% 100%;animation:shimmer 1.3s linear infinite}
.board-ghost span:first-child{width:90px;height:24px;margin-top:14px;border-radius:999px}
.board-ghost span:last-child{width:264px;height:150px}
@keyframes shimmer{to{background-position:-200% 0}}
@media (prefers-reduced-motion: reduce){.board-ghost span{animation:none}}
.board-size{display:flex;gap:2px;padding:2px;border-radius:9px;background:var(--quiet);margin-right:4px}
.board-size button{min-width:30px;height:26px;padding:0 8px;border-radius:7px;font-size:12px;color:var(--muted)}
.board-size button.active{background:#fff;color:var(--ink);box-shadow:0 1px 2px #37221714}
</style>
