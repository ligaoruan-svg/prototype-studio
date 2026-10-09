<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowLeft, Download, ExternalLink, Layers, LoaderCircle, LocateFixed, PencilLine, Play, RotateCw, Search, AlertCircle, ChevronDown } from 'lucide-vue-next'
import { expand, expandAll, isFresh, requestRoute, touch } from './expandStore.js'
import { ORIGIN_LABEL, ancestorsOf, buildTree, crumbOf, originOf, pickToSelection, shortLabel, trailOf } from './probeTree.js'
import SceneCard from './SceneCard.vue'
import BoardBranch from './BoardBranch.vue'
import LiveScene from './LiveScene.vue'

const props = defineProps({ route: { type: String, default: '' }, pageName: String, selection: Object, mode: String, focus: [Number, null], notes: { type: Array, default: () => [] }, patch: Object })
const emit = defineEmits(['open', 'select', 'clear', 'mode', 'update:focus', 'update:route', 'export'])
const exportable = computed(() => Object.values(expand.entries).some(e => e?.result?.styles))

const empty = { title: '', styles: null, page: '', width: 1150, height: 800, nodes: [] }
const filter = ref('all'), query = ref(''), live = ref(null), scroller = ref(null)
const openIds = ref(new Set())   // 展开了「后续」的节点
const entry = computed(() => expand.entries[props.route] || null)
const job = computed(() => expand.jobs[props.route] || null)
const state = computed(() => entry.value?.result || empty)
const progress = computed(() => job.value?.progress || {})
// running：第一次展开这一页；refreshing：重新查找；syncing：改过一版在同步；queued：排着队
const status = computed(() => job.value ? (job.value.kind === 'sync' ? 'syncing' : entry.value && !entry.value.partial ? 'refreshing' : 'running')
  : expand.queued.includes(props.route) ? 'queued' : entry.value ? 'done' : 'idle')
const busy = computed(() => status.value !== 'done' && status.value !== 'idle')
const staleCount = computed(() => state.value.nodes.filter(n => n.stale).length)

// 业务页面：原型里导航的每个路由一项（和左侧「原型文件」不是一回事）
const routeTitle = route => expand.routes.find(r => r.hash === route)?.title
const pages = computed(() => expand.routes.map(r => ({ ...r, count: expand.entries[r.hash]?.result?.nodes?.length,
  state: expand.jobs[r.hash] ? '展开中' : isFresh(r.hash) ? '' : expand.entries[r.hash] ? '待同步' : expand.queued.includes(r.hash) ? '排队中' : '未展开' })))
const allDone = computed(() => expand.routes.length > 0 && expand.routes.every(r => isFresh(r.hash)))
const allProgress = computed(() => ({ done: expand.routes.filter(r => isFresh(r.hash)).length, total: expand.routes.length }))
const allRunning = computed(() => expand.discovering || (expand.routes.length > 0 && !allDone.value && (Object.keys(expand.jobs).length > 0 || expand.queued.length > 0)))

// 导航里的菜单名最准（「碳排核算模板配置」）；原型页面里取到的常常是整站标题
const title = computed(() => routeTitle(props.route) || state.value.title || props.pageName || '当前页面')
const pageNode = computed(() => state.value.styles && state.value.page ? { id: 0, isPage: true, title: title.value, html: state.value.page, box: null } : null)
const scenes = computed(() => [...(pageNode.value ? [pageNode.value] : []), ...state.value.nodes].map(node => ({ node, crumb: node.isPage ? '当前页面' : crumbOf(state.value.nodes, node) })))
// 一棵树：页面在左边，从它的按钮出发一条条链
const tree = computed(() => buildTree(state.value.nodes.map(n => ({ ...n, crumb: crumbOf(state.value.nodes, n), notes: notesOf(n) }))))
const q = computed(() => query.value.trim())
const hit = node => !!q.value && `${node.title} ${node.label}`.includes(q.value)
const matches = node => !q.value || hit(node) || node.children.some(matches)
const roots = computed(() => tree.value.filter(n => (filter.value === 'all' || originOf(n) === filter.value) && matches(n)))
// 口径统一：总数是视图数，分组是「组」（每组一条按钮链）
const groups = computed(() => {
  const counts = {}
  for (const n of tree.value) counts[originOf(n)] = (counts[originOf(n)] || 0) + 1
  return [{ key: 'all', label: `全部 ${scenes.value.length} 个视图` }, ...['button', 'row'].filter(k => counts[k]).map(k => ({ key: k, label: `${ORIGIN_LABEL[k]} ${counts[k]} 组` }))]
})
const frame = computed(() => ({ w: state.value.width || 1150, h: state.value.height || 800 }))
const routePatch = computed(() => props.patch && (props.patch.route == null || props.patch.route === props.route) ? props.patch : null)
const picked = computed(() => props.selection?.card?.route === props.route ? props.selection.card : null)
const focused = computed(() => props.focus == null ? null : scenes.value.find(s => s.node.id === props.focus) || null)
const hint = computed(() => props.mode === 'interact' ? '点卡片试玩；要改哪里，点卡片右上角「编辑」' : props.mode === 'box' ? '在卡片里拖动框选一组元素；太小时点「编辑」放大' : '点击元素选择修改，按住 Shift 多选；太小时点「编辑」放大')

function notesOf(node) { return props.notes.filter(a => node.isPage ? !a.in_modal && !a.in_subpage : (a.in_modal || a.in_subpage) === node.title).length }
function edit(node) { if (props.mode === 'interact') emit('mode', 'select'); emit('update:focus', node.id) }
function play(node) { if (props.mode !== 'interact') emit('mode', 'interact'); emit('update:focus', node.id) }
function openInPreview(node) { emit('open', { ...node, route: props.route, trail: node.isPage ? '' : trailOf(state.value.nodes, node) }) }
function refind() { requestRoute(props.route, { force: true }) }
function pick({ node, items }) {
  if (!items.length) { emit('clear'); return }
  touch(props.route, node.id)
  const sel = pickToSelection(node, items, title.value)
  emit('select', { ...sel, card: { ...sel.card, route: props.route }, trail: node.isPage ? '' : trailOf(state.value.nodes, node) })
}
function toggle(id) { const next = new Set(openIds.value); next.has(id) ? next.delete(id) : next.add(id); openIds.value = next }
// 把这一路的「后续」都展开，再滚过去
async function reveal(id, also = []) {
  if (id == null) return
  const next = new Set(openIds.value)
  for (const target of [id, ...also]) for (const a of ancestorsOf(state.value.nodes, target)) next.add(a)
  openIds.value = next
  await nextTick()
  scroller.value?.querySelector(`[data-node-id="${id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' })
}
// 搜索：命中的那张卡所在的路径自动展开并滚过去
// 每个命中的都要露出来（不只第一个：「GWP 值」既有顶层的编辑弹窗，也有藏在「新增因子 → 下一步」后面的）
watch(q, value => { if (!value) return; const all = state.value.nodes.filter(n => `${n.title} ${n.label}`.includes(value)); if (all.length) reveal(all[0].id, all.slice(1).map(n => n.id)) })
// 选中的、正在编辑的卡，它那一路默认展开
watch(() => picked.value?.nodeId, id => { if (id) reveal(id) })
// 记过意见的卡：改完同步时先拍
watch(() => props.notes, notes => { for (const n of state.value.nodes) if (notes.some(a => (a.in_modal || a.in_subpage) === n.title)) touch(props.route, n.id) }, { immediate: true })
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
        <span class="state-tag" :class="{ live: mode === 'interact' }">{{ mode === 'interact' ? '试玩中 · 演示数据不保存' : mode === 'box' ? '编辑中 · 拖动框选' : '编辑中 · 点击元素选择修改' }}</span>
        <template v-if="mode === 'interact'">
          <button type="button" class="outline focus-btn" @click="live?.restart()"><RotateCw :size="14" />重新开始</button>
          <button type="button" class="outline focus-btn" @click="edit(focused.node)"><PencilLine :size="14" />改为编辑</button>
        </template>
        <button v-else type="button" class="outline focus-btn" @click="play(focused.node)"><Play :size="14" />试玩</button>
        <button type="button" class="outline focus-btn" title="回到预览，在完整页面里打开这个视图" @click="openInPreview(focused.node)"><ExternalLink :size="14" />在预览中打开</button>
      </div>
      <div class="focus-content">
        <LiveScene v-if="mode === 'interact'" ref="live" :key="'live-' + focused.node.id" :node="focused.node" :route="route" :frame="frame" />
        <SceneCard v-else :key="'focus-' + focused.node.id" :node="focused.node" :styles="state.styles" :frame="frame" :picked="picked" :mode="mode" :crumb="focused.crumb" :patch="routePatch" large @pick="pick" />
      </div>
    </template>
    <template v-else>
      <div class="board-tools">
        <div class="board-heading-wrap">
          <div class="board-heading">
            <Layers :size="16" />
            <label v-if="pages.length" class="page-switch" title="切换业务页面"><select :value="route" aria-label="切换业务页面" @change="$emit('update:route', $event.target.value); $emit('update:focus', null)"><option v-if="!pages.some(p => p.hash === route)" :value="route">{{ title }}</option><option v-for="p in pages" :key="p.hash" :value="p.hash">{{ p.title }}{{ p.count != null ? ' · ' + p.count : '' }}{{ p.state ? '（' + p.state + '）' : '' }}</option></select><strong>{{ title }}</strong><ChevronDown :size="14" /></label>
            <strong v-else>{{ title }}</strong>
          </div>
          <p v-if="status === 'running'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />正在试「{{ shortLabel(progress.current) || '准备中' }}」· 已试 {{ progress.tried || 0 }} / {{ progress.total || '…' }} · 找到 {{ progress.nodes?.length || 0 }} 个</p>
          <p v-else-if="status === 'refreshing'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />正在重新查找 · 已试 {{ progress.tried || 0 }} / {{ progress.total || '…' }}</p>
          <p v-else-if="status === 'syncing'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />正在同步改动 · {{ progress.done || 0 }} / {{ progress.total || state.nodes.length }}</p>
          <p v-else-if="status === 'queued'" class="board-sub live" aria-live="polite"><LoaderCircle :size="12" class="spin" />排队中，马上轮到这一页</p>
          <p v-else-if="staleCount" class="board-sub warn">有 {{ staleCount }} 张卡路径失效（标了黄色），可能按钮改了名——<button type="button" class="link-btn" @click="refind">重新查找这一页</button></p>
          <p v-else class="board-sub">{{ hint }}</p>
        </div>
        <div class="board-control">
          <button v-if="picked" type="button" class="icon-button tool" title="定位当前选中的视图" aria-label="定位当前选中的视图" @click="reveal(picked.nodeId)"><LocateFixed :size="15" /></button>
          <button v-if="exportable" type="button" class="export-expand" title="把已展开的所有业务页面导出成一个 HTML 文件：发给别人双击就能看，也能打印成 PDF" @click="$emit('export')"><Download :size="13" />导出展开图</button>
          <button v-if="!allDone" type="button" class="expand-all" :disabled="allRunning" :title="allRunning ? '后台正在展开，预览和展开视图照常能用' : '把原型里的每个业务页面都展开一遍，之后改动会自动同步'" @click="expandAll(route)"><LoaderCircle v-if="allRunning" :size="13" class="spin" /><Layers v-else :size="13" />{{ allRunning ? (expand.discovering ? '正在找页面…' : `业务页面 ${allProgress.done} / ${allProgress.total}`) : '一键展开全部业务页面' }}</button>
          <span v-else class="all-done" title="所有业务页面都已展开，改动会自动同步">{{ allProgress.total }} 个业务页面已展开</span>
          <label class="search"><Search :size="14" /><input v-model="query" type="search" placeholder="查找弹窗" aria-label="查找弹窗"></label>
          <button type="button" class="icon-button tool" :disabled="busy" title="重新查找这一页的所有弹窗（新加了按钮时用）" aria-label="重新查找这一页的所有弹窗" @click="refind"><RotateCw :size="15" :class="{ spin: busy }" /></button>
        </div>
      </div>
      <div class="board-filter" role="tablist" aria-label="按来源筛选">
        <button v-for="g in groups" :key="g.key" type="button" role="tab" :aria-selected="filter === g.key" :class="{ active: filter === g.key }" @click="filter = g.key">{{ g.label }}</button>
      </div>
      <div v-if="expand.error" class="board-error"><AlertCircle :size="15" /><span>{{ expand.error }}，可以点右上角的刷新再试一次。</span></div>
      <div ref="scroller" class="board-scroll">
        <div class="board-tree">
          <div class="tree-root">
            <SceneCard v-if="pageNode" :node="pageNode" :styles="state.styles" :frame="frame" :picked="picked" :mode="mode" crumb="当前页面" :notes="notesOf(pageNode)" :width="216" :patch="routePatch" compact @pick="pick" @edit="edit" @play="play" />
            <div v-else class="scene-ghost" aria-hidden="true"><span></span><span></span><span></span></div>
          </div>
          <div class="tree-branches">
            <BoardBranch v-for="node in roots" :key="node.id" :node="node" :styles="state.styles" :frame="frame" :picked="picked" :mode="mode" :open="openIds" :patch="routePatch" @pick="pick" @edit="edit" @play="play" @refind="refind" @toggle="toggle" />
            <div v-if="status === 'running' || status === 'queued'" class="branch-ghost" aria-hidden="true"><span></span><div class="scene-ghost"><span></span><span></span><span></span></div></div>
            <div v-if="!busy && !roots.length" class="empty-board">
              <template v-if="q || filter !== 'all'"><Search :size="22" /><h3>没有找到对应视图</h3><p>试试其他名称，或者清空当前筛选。</p><button type="button" class="outline" @click="query = ''; filter = 'all'">清空筛选</button></template>
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
.export-expand{display:inline-flex;align-items:center;gap:6px;height:34px;padding:0 12px;border:1px solid #e2ded3;border-radius:10px;background:#fff;font-size:12.5px;color:var(--ink);white-space:nowrap}.export-expand:hover{border-color:#c9c1b4}
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
.tree-root{width:240px;flex-shrink:0}
.tree-branches{display:flex;flex-direction:column;gap:18px;padding-left:16px;border-left:1.5px solid var(--line);min-width:420px}
.branch-ghost{display:flex;gap:10px;align-items:flex-start}
.branch-ghost>span{display:block;width:90px;height:26px;margin-top:14px;border-radius:12px;background:#efece4}
.branch-ghost .scene-ghost{width:360px}
.state-tag{font-size:11.5px;color:var(--muted);background:var(--quiet);border-radius:20px;padding:2px 9px;white-space:nowrap}
.state-tag.live{color:var(--primary);background:var(--primary-soft)}
.focus-btn{gap:6px;font-size:12px;padding:6px 11px;border:1px solid var(--line);border-radius:9px;background:#fff;white-space:nowrap}
.link-btn{padding:0;font-size:inherit;color:var(--primary);text-decoration:underline;text-underline-offset:2px}
.board-control .tool{width:32px;height:32px;background:#fff;border:1px solid var(--line);border-radius:8px}
</style>
