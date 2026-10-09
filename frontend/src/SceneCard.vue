<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ChevronRight, Code2, Hand, Layers, Maximize2, Monitor } from 'lucide-vue-next'
import { cardDocument } from './probeTree.js'
const props = defineProps({ node: Object, styles: Object, frame: Object, picked: Object, mode: String, crumb: String, large: Boolean, notes: Number })
const emit = defineEmits(['pick', 'open', 'focus'])
const iframe = ref(null), stage = ref(null), width = ref(0)
const doc = computed(() => cardDocument(props.styles, props.node.html, { pickable: true }))
const box = computed(() => props.node.box || { x: 0, y: 0, w: props.frame.w, h: props.frame.h })
// 按卡片实际宽度取景：弹窗本体铺满卡片，最多放大到原尺寸（放大编辑时到 1.3 倍）
const view = computed(() => {
  const scale = Math.max(0.1, Math.min((width.value || 360) / box.value.w, props.large ? 1.3 : 1))
  return { scale, width: Math.round(box.value.w * scale), height: Math.round(box.value.h * scale),
    transform: `translate(${-box.value.x * scale}px, ${-box.value.y * scale}px) scale(${scale})` }
})
const rels = computed(() => props.picked?.nodeId === props.node.id ? props.picked.rels : [])
const post = message => iframe.value?.contentWindow?.postMessage(message, '*')
function sync() { post({ type: 'CARD_MODE', mode: props.mode }); post({ type: 'CARD_SHOW', rels: [...rels.value], reveal: props.large }) }
watch(rels, () => post({ type: 'CARD_SHOW', rels: [...rels.value] }))
watch(() => props.mode, () => post({ type: 'CARD_MODE', mode: props.mode }))
function listen(event) {
  if (event.source !== iframe.value?.contentWindow || event.data?.source !== 'pa-card') return
  if (event.data.type === 'CARD_PICK') emit('pick', { node: props.node, items: event.data.items })
}
let observer
onMounted(() => {
  window.addEventListener('message', listen)
  observer = new ResizeObserver(([entry]) => { width.value = Math.floor(entry.contentRect.width) })
  if (stage.value) observer.observe(stage.value)
})
onUnmounted(() => { window.removeEventListener('message', listen); observer?.disconnect() })
</script>
<template>
  <article class="scene-card" :class="{ 'selected-card': rels.length, large }">
    <header v-if="!large" class="scene-head">
      <component :is="node.isPage ? Monitor : Layers" :size="14" />
      <h3 :title="node.title">{{ node.title }}</h3>
      <span v-if="notes" class="note-badge" :title="`这张卡上已记下 ${notes} 条修改意见`">已记 {{ notes }}</span>
      <button type="button" :aria-label="`放大编辑${node.title}`" title="放大后选中元素，不切换查看方式" @click="$emit('focus', node)"><Maximize2 :size="13" /><span>放大编辑</span></button>
    </header>
    <div v-if="!large" class="scene-trail" :title="crumb"><ChevronRight :size="12" /><span>{{ crumb }}</span><em v-if="node.stale">· 点不开了，可能已过期</em></div>
    <div ref="stage" class="scene-preview" :class="{ page: node.isPage }">
      <div class="thumb" :style="{ width: view.width + 'px', height: view.height + 'px' }">
        <iframe ref="iframe" sandbox="allow-scripts" :title="`${node.title} · 点选要改的地方`" :srcdoc="doc" :style="{ width: frame.w + 'px', height: frame.h + 'px', transform: view.transform }" @load="sync"></iframe>
      </div>
    </div>
    <footer v-if="!large" class="scene-foot">
      <span class="source-type"><component :is="node.isPage ? Code2 : Layers" :size="12" />{{ node.isPage ? '静态页面' : '动态弹窗' }}</span>
      <button type="button" :title="node.isPage ? '回到预览' : `在预览里打开「${node.title}」，可以真的点一点`" @click="$emit('open', node)"><Hand :size="12" />交互预览</button>
    </footer>
  </article>
</template>
<style scoped>
.scene-card{background:#fff;border:1px solid #dfddd5;border-radius:12px;overflow:hidden;min-width:0;transition:border-color .15s,box-shadow .15s}
.scene-card.selected-card{border-color:var(--primary);box-shadow:0 0 0 2px #b8532f12}
.scene-card.large{border:0;border-radius:0;background:transparent;overflow:visible}
.scene-head{display:flex;align-items:center;gap:6px;padding:10px 12px;border-bottom:1px solid var(--line)}
.scene-head svg{color:var(--muted)}
.scene-head h3{flex:1;min-width:0;font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.scene-head button{gap:5px;padding:3px 6px;border-radius:7px;font-size:11px;color:var(--muted)}
.scene-head button:hover{background:var(--quiet);color:var(--ink)}
.scene-trail{display:flex;align-items:center;gap:5px;min-width:0;padding:8px 12px;font-size:11px;color:var(--muted);background:#fcfbf8;border-bottom:1px solid var(--line)}
.scene-trail svg{color:var(--subtle)}
.scene-trail span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.scene-trail em{font-style:normal;color:#9a6a1b;white-space:nowrap}
.note-badge{flex-shrink:0;font-size:11px;color:#fff;background:var(--primary);border-radius:20px;padding:1px 7px}
.scene-preview{display:flex;justify-content:center;align-items:flex-start;padding:14px;background:#f5f7fa;max-height:480px;overflow:auto;overscroll-behavior:contain}
.scene-card.large .scene-preview{max-height:none;padding:0;background:transparent;overflow:visible}
.thumb{position:relative;flex-shrink:0;overflow:hidden;border-radius:6px;box-shadow:0 1px 4px #2b33200f}
.scene-card.large .thumb{border-radius:10px;box-shadow:0 8px 24px #2b332016}
.thumb iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0;background:transparent}
.scene-foot{display:flex;align-items:center;gap:8px;padding:9px 12px;font-size:11px;color:var(--muted);border-top:1px solid var(--line)}
.scene-foot .source-type{display:inline-flex;align-items:center;gap:5px}
.scene-foot button{gap:5px;margin-left:auto;padding:3px 7px;border-radius:7px;font-size:11px;color:var(--muted)}
.scene-foot button:hover{background:var(--quiet);color:var(--primary)}
@media (prefers-reduced-motion: reduce){.scene-card{transition:none}}
</style>
