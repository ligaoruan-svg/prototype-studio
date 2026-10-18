<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ChevronDown, ChevronRight, Code2, Layers, LoaderCircle, Monitor, PencilLine, RotateCw, Hand } from 'lucide-vue-next'
import { cardDocument, edgeLabel } from '../../lib/probeTree.js'
const props = defineProps({ node: Object, styles: Object, frame: Object, picked: Object, mode: String, crumb: String, large: Boolean, notes: Number, compact: Boolean, width: Number, patch: Object })
const emit = defineEmits(['pick', 'edit', 'play', 'refind', 'fix'])
const iframe = ref(null), stage = ref(null), measured = ref(0), root = ref(null)
// 很久没看到的卡片先不渲染：一页几十张卡，每张都是一份原型副本，全挂着很吃内存、滚动也卡。
// 滚到附近才载入；离开视野 30 秒后卸掉，只留一个同样大小的占位，滚回来再载入
const live = ref(!!props.large)
const UNLOAD_MS = 30_000
let io = null, unloadTimer = null
// 认错了自己纠正：子页面 / 页签 / 别的业务页面，三选一
const fixOpen = ref(false)
const fixable = computed(() => !props.large && props.node.kind === 'subpage' && !props.node.isPage)
const fixOptions = computed(() => [
  { kind: 'subpage', label: '子页面', hint: '点进去的详情页，挂在这页的树下' },
  { kind: 'tab', label: '页签', hint: '同一页的另一个视图' },
  { kind: 'jump', label: '别的业务页面', hint: '不挂在这页，列到「从这页能跳到」' },
].filter(o => o.kind !== (props.node.tab ? 'tab' : 'subpage')))
function fix(kind) { fixOpen.value = false; emit('fix', { node: props.node, kind }) }
const pageLike = computed(() => props.node.isPage || props.node.kind === 'subpage')
const doc = computed(() => cardDocument(props.styles, props.node.html, { pickable: true, scroll: props.large && pageLike.value }))
// 放大编辑时滚到哪了：卡片重拍（改完同步）会重新载入，载入后回到原来的位置
let scrolled = null
const box = computed(() => props.node.box || { x: 0, y: 0, w: props.frame.w, h: props.frame.h })
// 按卡片实际宽度取景：弹窗本体铺满卡片，最多放大到原尺寸（编辑视图里到 1.3 倍）
const view = computed(() => {
  const scale = Math.max(0.1, Math.min((measured.value || props.width || 360) / box.value.w, props.large ? 1.3 : 1))
  return { width: Math.round(box.value.w * scale), height: Math.round(box.value.h * scale),
    transform: `translate(${-box.value.x * scale}px, ${-box.value.y * scale}px) scale(${scale})` }
})
const rels = computed(() => props.picked?.nodeId === props.node.id ? props.picked.rels : [])
const kindLabel = computed(() => props.node.isPage ? '静态页面' : props.node.tab ? '页签 · 同一页的另一个视图' : props.node.kind === 'subpage' ? '子页面 · 页内跳转' : '动态弹窗')
const post = message => iframe.value?.contentWindow?.postMessage(message, '*')
function sync() {
  post({ type: 'CARD_MODE', mode: props.mode })
  if (scrolled) post({ type: 'CARD_SCROLL_TO', ...scrolled })
  post({ type: 'CARD_SHOW', rels: [...rels.value], reveal: props.large && !scrolled })
}
watch(rels, () => post({ type: 'CARD_SHOW', rels: [...rels.value] }))
watch(() => props.mode, () => post({ type: 'CARD_MODE', mode: props.mode }))
// 属性面板里改颜色、字号、文字：先在卡片快照上直接改，不等保存和同步
watch(() => props.patch?.seq, () => {
  const p = props.patch
  if (!p || (p.nodeId != null && p.nodeId !== props.node.id)) return
  // 改了没存成：重新载入快照，退回原来的样子
  if (p.revert) { if (iframe.value) iframe.value.srcdoc = doc.value; return }
  post({ type: 'CARD_PATCH', prop: p.prop, value: p.value, rels: [...(p.rels || [])] })
})
function listen(event) {
  if (event.source !== iframe.value?.contentWindow || event.data?.source !== 'pa-card') return
  // 空的也要报：Shift 把最后一个取消掉，外面的选中也得跟着清掉
  if (event.data.type === 'CARD_PICK') emit('pick', { node: props.node, items: event.data.items || [] })
  if (event.data.type === 'CARD_SCROLL' && props.large) scrolled = { at: event.data.at, top: event.data.top, left: event.data.left }
}
let observer
onMounted(() => {
  window.addEventListener('message', listen)
  observer = new ResizeObserver(([entry]) => { measured.value = Math.floor(entry.contentRect.width) })
  if (stage.value) observer.observe(stage.value)
  if (!props.large && root.value && 'IntersectionObserver' in window) {
    io = new IntersectionObserver(([e]) => {
      clearTimeout(unloadTimer)
      if (e.isIntersecting) live.value = true
      else if (live.value) unloadTimer = setTimeout(() => { if (!rels.value.length) live.value = false }, UNLOAD_MS)
    }, { root: root.value.closest('.board-scroll'), rootMargin: '600px' })
    io.observe(root.value)
  } else live.value = true
})
onUnmounted(() => { window.removeEventListener('message', listen); observer?.disconnect(); io?.disconnect(); clearTimeout(unloadTimer) })
</script>
<template>
  <article ref="root" class="scene-card" :class="{ 'selected-card': rels.length, large, stale: node.stale, pending: node.pending }" :data-node-id="node.id">
    <header v-if="!large" class="scene-head">
      <component :is="pageLike ? Monitor : Layers" :size="14" />
      <h3 :title="$t(node.title)">{{ $t(node.title) }}</h3>
      <span v-if="node.pending" class="sync-badge" :title="$t('改动后正在重新拍这张卡')"><LoaderCircle :size="11" class="spin" />{{ $t('更新中') }}</span>
      <span v-if="notes" class="note-badge" :title="$t('这张卡上已记下 {0} 条修改意见', [$t(notes)])">{{ $t('已记 {0}', [$t(notes)]) }}</span>
      <button v-if="node.stale" type="button" class="stale-badge" :title="$t('按原来的路径点不开了（按钮可能改了名或被删了），这张卡显示的是旧样子。点这里重新查找这一页')" @click="$emit('refind')"><RotateCw :size="11" />{{ $t('路径失效') }}</button>
      <button type="button" class="head-action" :title="$t('编辑「{0}」：放大后点选要改的地方', [$t(node.title)])" @click="$emit('edit', node)"><PencilLine :size="13" /><span>{{ $t('编辑') }}</span></button>
    </header>
    <div v-if="!large && !compact" class="scene-trail" :title="$t(crumb)"><ChevronRight :size="12" /><span>{{ $t(crumb) }}</span></div>
    <div ref="stage" class="scene-preview">
      <!-- 交互模式：卡片是快照不能点，点一下放大成真的在跑的原型 -->
      <button v-if="mode === 'interact' && !large" type="button" class="play-cover" :aria-label="$t('交互{0}', [$t(node.title)])" @click="$emit('play', node)"><span><Hand :size="14" />{{ $t('点一下交互') }}</span></button>
      <div class="thumb" :class="{ asleep: !live }" :style="{ width: view.width + 'px', height: view.height + 'px' }">
        <iframe v-if="live" ref="iframe" sandbox="allow-scripts" :title="$t('{0} · 点选要改的地方', [$t(node.title)])" :srcdoc="doc" :style="{ width: frame.w + 'px', height: frame.h + 'px', transform: view.transform }" @load="sync"></iframe>
      </div>
    </div>
    <footer v-if="!large" class="scene-foot">
      <button v-if="fixable" type="button" class="source-type fixable" :aria-expanded="fixOpen" :title="$t('认错了？点这里改成子页面 / 页签 / 别的业务页面，下次展开照你改的来')" @click="fixOpen = !fixOpen"><Code2 :size="12" />{{ $t(kindLabel) }}<span v-if="node.forced" class="mine">{{ $t('你改的') }}</span><ChevronDown :size="11" /></button>
      <span v-else class="source-type"><component :is="pageLike ? Code2 : Layers" :size="12" />{{ $t(kindLabel) }}</span>
      <button type="button" class="play-mini" :title="$t('交互「{0}」：真的跑起来随便点，演示数据不保存', [$t(node.title)])" @click="$emit('play', node)"><Hand :size="12" />{{ $t('交互') }}</button>
      <div v-if="fixOpen" class="fix-menu" role="menu" :aria-label="$t('纠正这张卡的类型')">
        <p>{{ $t('认错了？「{0}」点出来的其实是', [edgeLabel(node.label)]) }}</p>
        <button v-for="o in fixOptions" :key="o.kind" type="button" role="menuitem" @click="fix(o.kind)"><b>{{ $t(o.label) }}</b><small>{{ $t(o.hint) }}</small></button>
        <button v-if="node.forced" type="button" role="menuitem" class="reset" @click="fix(null)"><b>{{ $t('恢复自动认') }}</b><small>{{ $t('去掉你的纠正，按默认规则认') }}</small></button>
      </div>
    </footer>
  </article>
</template>
<style scoped>
.scene-card{background:#fff;border:1px solid #dfddd5;border-radius:12px;overflow:hidden;min-width:0;transition:border-color .15s,box-shadow .15s}
.scene-card.selected-card{border-color:var(--primary);box-shadow:0 0 0 2px #b8532f12}
.scene-card.stale:not(.selected-card){border-color:#e7cf9f}
.scene-card.large{border:0;border-radius:0;background:transparent;overflow:visible}
.scene-head{display:flex;align-items:center;gap:6px;padding:9px 10px 9px 12px;border-bottom:1px solid var(--line)}
.scene-head>svg{color:var(--muted)}
.scene-head h3{flex:1;min-width:0;font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.head-action{gap:5px;padding:3px 7px;border-radius:7px;font-size:11.5px;color:var(--muted)}
.head-action:hover{background:var(--primary-soft);color:var(--primary)}
.note-badge{flex-shrink:0;font-size:11px;color:#fff;background:var(--primary);border-radius:20px;padding:1px 7px}
.sync-badge{flex-shrink:0;display:inline-flex;align-items:center;gap:3px;font-size:11px;color:var(--primary);background:var(--primary-soft);border-radius:20px;padding:1px 7px}
.scene-card.pending .thumb{opacity:.72}
.stale-badge{flex-shrink:0;gap:3px;font-size:11px;color:#8a5a0b;background:#fbf1dc;border:1px solid #edd6a6;border-radius:20px;padding:1px 7px}
.stale-badge:hover{background:#f7e6c1}
.scene-trail{display:flex;align-items:center;gap:5px;min-width:0;padding:8px 12px;font-size:11px;color:var(--muted);background:#fcfbf8;border-bottom:1px solid var(--line)}
.scene-trail svg{color:var(--subtle)}
.scene-trail span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.scene-preview{position:relative;display:flex;justify-content:center;align-items:flex-start;padding:12px;background:#f5f7fa;max-height:460px;overflow:auto;overscroll-behavior:contain}
.scene-card.large .scene-preview{max-height:none;padding:0;background:transparent;overflow:visible}
.thumb{position:relative;flex-shrink:0;overflow:hidden;border-radius:6px;box-shadow:0 1px 4px #2b33200f}
.scene-card.large .thumb{border-radius:10px;box-shadow:0 8px 24px #2b332016}
.thumb iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0;background:transparent}
.play-cover{position:absolute;inset:0;z-index:2;display:flex;align-items:center;justify-content:center;padding:0;border-radius:0;background:transparent;cursor:pointer}
.play-cover span{display:inline-flex;align-items:center;gap:6px;padding:7px 13px;border-radius:20px;background:#141413cc;color:#fff;font-size:12px;opacity:0;transform:translateY(4px);transition:opacity .15s,transform .15s}
.play-cover:hover{background:#14141308}.play-cover:hover span,.play-cover:focus-visible span{opacity:1;transform:none}
.scene-foot{display:flex;align-items:center;gap:8px;padding:8px 12px;font-size:11px;color:var(--muted);border-top:1px solid var(--line)}
.scene-foot .source-type{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
.scene-foot{flex-wrap:wrap}
.scene-foot .play-mini{gap:5px;margin-left:auto;padding:3px 8px;border-radius:7px;font-size:11.5px;color:var(--muted)}
.scene-foot .play-mini:hover{background:var(--quiet);color:var(--primary)}
.source-type.fixable{gap:5px;padding:2px 6px;margin:-2px -6px;border-radius:7px;font-size:11px;color:var(--muted)}
.source-type.fixable:hover,.source-type.fixable[aria-expanded=true]{background:var(--quiet);color:var(--ink)}
.source-type .mine{padding:0 5px;border-radius:10px;background:var(--primary-soft);color:var(--primary);font-size:10.5px}
.fix-menu{flex-basis:100%;display:flex;flex-direction:column;gap:2px;margin-top:6px;padding:6px;border:1px solid var(--line);border-radius:10px;background:#fcfbf8}
.fix-menu p{margin:0 0 3px 4px;font-size:11px;color:var(--muted)}
.fix-menu button{display:flex;flex-direction:column;align-items:flex-start;gap:1px;padding:5px 8px;border-radius:7px;text-align:left}
.fix-menu button:hover{background:#fff}
.fix-menu b{font-size:12px;font-weight:550;color:var(--ink)}.fix-menu small{font-size:10.5px;color:var(--muted)}
.fix-menu .reset b{color:var(--muted)}
.thumb.asleep{background:repeating-linear-gradient(135deg,#f3f1ec 0 10px,#f8f7f3 10px 20px)}
@media (prefers-reduced-motion: reduce){.scene-card{transition:none}.play-cover span{transition:none}}
</style>
