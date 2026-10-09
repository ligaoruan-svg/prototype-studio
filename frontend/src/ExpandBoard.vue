<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Hand, Layers, LoaderCircle, RotateCw, Search, AlertCircle, ChevronDown } from 'lucide-vue-next'
import { expand, expandAll, isFresh, requestRoute, touch } from './expandStore.js'
import { ORIGIN_LABEL, crumbOf, originOf, pickToSelection, shortLabel, trailOf } from './probeTree.js'
import SceneCard from './SceneCard.vue'
import BoardBranch from './BoardBranch.vue'
import LiveScene from './LiveScene.vue'
import { buildTree } from './probeTree.js'

const props = defineProps({ route: { type: String, default: '' }, pageName: String, selection: Object, mode: String, focus: [Number, null], notes: { type: Array, default: () => [] } })
const emit = defineEmits(['open', 'leave', 'select', 'update:focus', 'update:route'])

const empty = { title: '', styles: null, page: '', width: 1150, height: 800, nodes: [] }
const filter = ref('all'), query = ref(''), live = ref(null)
const entry = computed(() => expand.entries[props.route] || null)
const job = computed(() => expand.jobs[props.route] || null)
const state = computed(() => entry.value?.result || empty)
const progress = computed(() => job.value?.progress || {})
// running：第一次展开这一页；refreshing：重新查找；syncing：改过一版在同步；queued：排着队
const status = computed(() => job.value ? (job.value.kind === 'sync' ? 'syncing' : entry.value && !entry.value.partial ? 'refreshing' : 'running')
  : expand.queued.includes(props.route) ? 'queued' : entry.value ? 'done' : 'idle')
const busy = computed(() => status.value !== 'done' && status.value !== 'idle')
const staleCount = computed(() => state.value.nodes.filter(n => n.stale).length)

// 全部页面：导航里的每个路由一项
const routeTitle = route => expand.routes.find(r => r.hash === route)?.title
const pages = computed(() => expand.routes.map(r => ({ ...r, count: expand.entries[r.hash]?.result?.nodes?.length,
  state: expand.jobs[r.hash] ? '展开中' : isFresh(r.hash) ? '' : expand.entries[r.hash] ? '待同步' : expand.queued.includes(r.hash) ? '排队中' : '未展开' })))
const allDone = computed(() => expand.routes.length > 0 && expand.routes.every(r => isFresh(r.hash)))
const allProgress = computed(() => ({ done: expand.routes.filter(r => isFresh(r.hash)).length, total: expand.routes.length }))
const allRunning = computed(() => expand.discovering || (expand.routes.length > 0 && !allDone.value && (Object.keys(expand.jobs).length > 0 || expand.queued.length > 0)))

// 导航里的菜单名最准（「碳排核算模板配置」）；原型页面里取到的常常是整站标题
const title = computed(() => routeTitle(props.route) || state.value.title || props.pageName || '当前页面')
// 页面本身也是一张卡：静态元素在这里点选，能直接微调
const pageNode = computed(() => state.value.styles && state.value.page ? { id: 0, isPage: true, title: title.value, html: state.value.page, box: null } : null)
const scenes = computed(() => [...(pageNode.value ? [pageNode.value] : []), ...state.value.nodes].map(node => ({ node, origin: originOf(node), crumb: crumbOf(state.value.nodes, node) })))
// 一棵树：页面在左边，从它的按钮出发一条条链，链上是依次打开的弹窗
const tree = computed(() => buildTree(state.value.nodes.map(n => ({ ...n, crumb: crumbOf(state.value.nodes, n), notes: notesOf(n) }))))
const matches = node => !query.value.trim() || `${node.title} ${node.label}`.includes(query.value.trim()) || node.children.some(matches)
const roots = computed(() => tree.value.filter(n => (filter.value === 'all' || originOf(n) === filter.value) && matches(n)))
const groups = computed(() => {
  const counts = {}
  for (const n of tree.value) counts[originOf(n)] = (counts[originOf(n)] || 0) + 1
  return [{ key: 'all', label: '全部视图', count: scenes.value.length }, ...['button', 'row'].filter(k => counts[k]).map(k => ({ key: k, label: ORIGIN_LABEL[k], count: counts[k] }))]
})
const frame = computed(() => ({ w: state.value.width || 1150, h: state.value.height || 800 }))
const picked = computed(() => props.selection?.card?.route === props.route ? props.selection.card : null)
const focused = computed(() => props.focus == null ? null : scenes.value.find(s => s.node.id === props.focus) || null)

function notesOf(node) { return props.notes.filter(a => (a.in_modal || '') === (node.isPage ? '' : node.title)).length }
function open(node) { if (node.isPage) emit('leave'); else emit('open', { ...node, route: props.route, trail: trailOf(state.value.nodes, node) }) }
function pick({ node, items }) {
  if (!items.length) return
  touch(props.route, node.id)
  const sel = pickToSelection(node, items, title.value)
  emit('select', { ...sel, card: { ...sel.card, route: props.route }, trail: node.isPage ? '' : trailOf(state.value.nodes, node) })
}
// 记过意见的卡：改完同步时先拍
watch(() => props.notes, notes => { for (const n of state.value.nodes) if (notes.some(a => a.in_modal && a.in_modal === n.title)) touch(props.route, n.id) }, { immediate: true })
watch(() => [props.route, expand.hash, expand.scope], () => requestRoute(props.route))
onMounted(() => requestRoute(props.route))
</script>
<template>
  <section class="board" aria-label="展开这一页的所有视图">
    <template v-if="focused">
      <div class="focus-head">
        <button type="button" class="quiet" @click="$emit('update:focus', null)"><ArrowLeft :size="15" />返回展开</button>
        <span class="divider"></span>
        <strong>{{ focused.node.title }}</strong>
        <span class="focus-crumb">{{ focused.crumb }}</span>
        <span v-if="mode === 'interact'" class="live-tag">试玩中 · 改动不会保存</span>
        <button v-if="mode === 'interact'" type="button" class="outline focus-live" @click="live?.restart()"><RotateCw :size="14" />重新开始</button>
        <button type="button" class="outline focus-live" @click="open(focused.node)"><Hand :size="14" />交互预览</button>
      </div>
      <div class="focus-content">
        <LiveScene v-if="mode === 'interact'" ref="live" :key="'live-' + focused.node.id" :node="focused.node" :route="route" :frame="frame" />
        <SceneCard v-else :key="'focus-' + focused.node.id" :node="focused.node" :styles="state.styles" :frame="frame" :picked="picked" :mode="mode" :crumb="focused.crumb" large @pick="pick" />
        <p class="focus-tip">{{ mode === 'interact' ? '这里是真的在跑的原型，可以随便点；切回点选或拉框就能选中要改的地方' : '放大后仍可点选或拉框；修改后保持当前视图与目标' }}</p>
      </div>
    </template>
    <template v-else>
      <div class="board-tools">
        <div class="board-heading-wrap">
          <div class="board-heading">
            <Layers :size="16" />
            <label v-if="pages.length" class="page-switch" title="切换要展开的页面"><select :value="route" aria-label="切换页面" @change="$emit('update:route', $event.target.value); $emit('update:focus', null)"><option v-if="!pages.some(p => p.hash === route)" :value="route">{{ title }}</option><option v-for="p in pages" :key="p.hash" :value="p.hash">{{ p.title }}{{ p.count != null ? ' · ' + p.count : '' }}{{ p.state ? '（' + p.state + '）' : '' }}</option></select><strong>{{ title }}</strong><ChevronDown :size="14" /></label>
            <strong v-else>{{ title }}</strong>
            <span class="board-count">{{ scenes.length }} 个视图</span>
          </div>
          <p v-if="status === 'running'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />正在试「{{ shortLabel(progress.current) || '准备中' }}」· 已试 {{ progress.tried || 0 }} / {{ progress.total || '…' }} · 找到 {{ progress.nodes?.length || 0 }} 个</p>
          <p v-else-if="status === 'refreshing'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />正在重新查找 · 已试 {{ progress.tried || 0 }} / {{ progress.total || '…' }}</p>
          <p v-else-if="status === 'syncing'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />正在同步改动 · {{ progress.done || 0 }} / {{ progress.total || state.nodes.length }}</p>
          <p v-else-if="status === 'queued'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />排队中，马上轮到这一页</p>
          <p v-else-if="staleCount" class="board-sub warn">有 {{ staleCount }} 张卡点不开了，可能按钮改了名——点右上角重新查找</p>
          <p v-else class="board-sub">点选要改的地方；太小时可放大编辑。多处一起改：每处「先记下」，最后一次修改</p>
        </div>
        <div class="board-control">
          <button v-if="!allDone" type="button" class="expand-all" :disabled="allRunning" :title="allRunning ? '后台正在展开，预览和展开视图照常能用' : '把原型里的每个页面都展开一遍，之后改动会自动同步'" @click="expandAll(route)"><LoaderCircle v-if="allRunning" :size="13" class="spin" /><Layers v-else :size="13" />{{ allRunning ? (expand.discovering ? '正在找页面…' : `全部页面 ${allProgress.done} / ${allProgress.total}`) : '一键展开全部页面' }}</button>
          <span v-else class="all-done" title="所有页面都已展开，改动会自动同步">全部 {{ allProgress.total }} 页已展开</span>
          <label class="search"><Search :size="14" /><input v-model="query" type="search" placeholder="查找弹窗" aria-label="查找弹窗"></label>
          <button type="button" class="icon-button refresh" :disabled="busy" title="重新查找这一页的所有弹窗（新加了按钮时用）" aria-label="重新查找这一页的所有弹窗" @click="requestRoute(route, { force: true })"><RotateCw :size="15" :class="{ spin: busy }" /></button>
        </div>
      </div>
      <div class="board-filter" role="tablist" aria-label="按来源筛选">
        <button v-for="g in groups" :key="g.key" type="button" role="tab" :aria-selected="filter === g.key" :class="{ active: filter === g.key }" @click="filter = g.key">{{ g.label }}<span>{{ g.count }}</span></button>
      </div>
      <div v-if="expand.error" class="board-error"><AlertCircle :size="15" /><span>{{ expand.error }}，可以点右上角的刷新再试一次。</span></div>
      <div class="board-scroll">
        <div class="board-tree">
          <div class="tree-root">
            <SceneCard v-if="pageNode" :node="pageNode" :styles="state.styles" :frame="frame" :picked="picked" :mode="mode" crumb="当前页面" :notes="notesOf(pageNode)" compact @pick="pick" @open="open" @focus="$emit('update:focus', $event.id)" @play="$emit('update:focus', $event.id)" />
            <div v-else class="scene-ghost" aria-hidden="true"><span></span><span></span><span></span></div>
          </div>
          <div class="tree-branches">
            <BoardBranch v-for="node in roots" :key="node.id" :node="node" :styles="state.styles" :frame="frame" :picked="picked" :mode="mode" @pick="pick" @open="open" @focus="$emit('update:focus', $event.id)" @play="$emit('update:focus', $event.id)" />
            <div v-if="status === 'running' || status === 'queued'" class="branch-ghost" aria-hidden="true"><span></span><div class="scene-ghost"><span></span><span></span><span></span></div></div>
            <div v-if="!busy && !roots.length" class="empty-board">
              <template v-if="query || filter !== 'all'"><Search :size="22" /><h3>没有找到对应视图</h3><p>试试其他名称，或者清空当前筛选。</p><button type="button" class="outline" @click="query = ''; filter = 'all'">清空筛选</button></template>
              <template v-else><h3>这一页没有点出弹窗</h3><p>如果弹窗要先切到某个页签、选中某一行才出现，先在预览里切过去，再点右上角的刷新。</p></template>
            </div>
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
.board-sub.warn{color:#9a6a1b}
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
.board-scroll{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:0 18px 24px;scrollbar-width:thin}
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
.focus-content{flex:1;min-height:0;overflow:auto;padding:28px 24px 32px}
.focus-tip{text-align:center;font-size:12px;color:var(--muted);margin-top:18px}
@media (prefers-reduced-motion: reduce){.scene-ghost span{animation:none}}
.page-switch{position:relative;display:flex;align-items:center;gap:4px;min-width:0;border-radius:7px;padding:2px 4px;margin:-2px -4px;cursor:pointer}
.page-switch:hover{background:#fff}
.page-switch strong{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.page-switch svg{color:var(--muted);flex-shrink:0}
.page-switch select{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%}
.expand-all{gap:6px;height:32px;padding:0 11px;font-size:12px;border-radius:8px;color:#fff;background:var(--primary)}
.expand-all:hover:not(:disabled){background:var(--primary-hover)}
.expand-all:disabled{opacity:1;background:#fff;color:var(--primary);border:1px solid #e1cabd}
.all-done{font-size:12px;color:var(--success);white-space:nowrap}
.board-tree{display:flex;align-items:flex-start;gap:22px;min-width:max-content}
.tree-root{position:sticky;left:0;top:0;z-index:3;width:340px;flex-shrink:0}
.tree-branches{display:flex;flex-direction:column;gap:18px;padding-left:16px;border-left:1.5px solid var(--line);min-width:420px}
.branch-ghost{display:flex;gap:10px;align-items:flex-start}
.branch-ghost>span{display:block;width:90px;height:26px;margin-top:14px;border-radius:12px;background:#efece4}
.branch-ghost .scene-ghost{width:360px}
.live-tag{font-size:11.5px;color:var(--primary);background:var(--primary-soft);border-radius:20px;padding:2px 9px;white-space:nowrap}
</style>
