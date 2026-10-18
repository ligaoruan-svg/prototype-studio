<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { LoaderCircle, AlertCircle } from 'lucide-vue-next'
import { liveDoc } from '../../lib/expandStore.js'
// 在展开视图里直接交互：真正跑起原型，按记下的路径把弹窗点开，然后随便点。
// 用的是后台副本那一套：演示数据只在这一份里，点了保存也不会写回你的预览。
const props = defineProps({ node: Object, route: String, frame: Object })
const emit = defineEmits(['state'])
const iframe = ref(null), stage = ref(null), width = ref(0), nonce = ref(0)
const status = ref('loading')   // loading | ready | failed
const doc = computed(() => liveDoc(props.route) + `\n<!-- live ${nonce.value} -->`)
const scale = computed(() => Math.max(0.2, Math.min((width.value || props.frame.w) / props.frame.w, 1)))
function listen(event) {
  if (event.source !== iframe.value?.contentWindow) return
  const data = event.data || {}
  if (data.source !== 'prototype-agent') return
  if (data.type === 'LOADED') {
    if (props.node.isPage) { status.value = 'ready'; return }
    clearTimeout(replayTimer)
    replayTimer = setTimeout(() => iframe.value?.contentWindow?.postMessage({ type: 'PA_REPLAY', path: JSON.parse(JSON.stringify(props.node.path || [])) }, '*'), 450)
  }
  if (data.type === 'REPLAYED') status.value = data.ok ? 'ready' : 'failed'
}
// 原型一直不回话（脚本卡死、载入报错）：15 秒后撤掉白层，至少能看见、能自己点
let giveUp = null, replayTimer = null
function arm() { clearTimeout(giveUp); giveUp = setTimeout(() => { if (status.value === 'loading') status.value = 'failed' }, 15_000) }
function restart() { status.value = 'loading'; nonce.value++; arm() }
defineExpose({ restart })
let observer
onMounted(() => {
  window.addEventListener('message', listen)
  observer = new ResizeObserver(([entry]) => { width.value = Math.floor(entry.contentRect.width) })
  observer.observe(stage.value)
  arm()
})
onUnmounted(() => { window.removeEventListener('message', listen); observer?.disconnect(); clearTimeout(giveUp); clearTimeout(replayTimer) })
</script>
<template>
  <div ref="stage" class="live-stage">
    <div class="live-frame" :style="{ width: frame.w * scale + 'px', height: frame.h * scale + 'px' }">
      <iframe ref="iframe" sandbox="allow-scripts allow-forms" :title="$t('{0} · 交互', [$t(node.title)])" :srcdoc="doc" :style="{ width: frame.w + 'px', height: frame.h + 'px', transform: `scale(${scale})` }"></iframe>
      <div v-if="status === 'loading'" class="live-veil"><LoaderCircle :size="18" class="spin" />{{ $t('正在打开「{0}」…', [$t(node.title)]) }}</div>
    </div>
    <p v-if="status === 'failed'" class="live-note"><AlertCircle :size="14" />{{ $t('没能按原路径点开这个弹窗，页面已经载入，可以自己点一下打开') }}</p>
  </div>
</template>
<style scoped>
.live-stage{width:100%}
.live-frame{position:relative;margin:0 auto;overflow:hidden;border-radius:10px;background:#fff;box-shadow:0 8px 24px #2b332016}
.live-frame iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0}
.live-veil{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:8px;background:#ffffffd9;color:var(--muted);font-size:13px}
.live-note{display:flex;align-items:center;justify-content:center;gap:6px;margin-top:12px;font-size:12px;color:#9a6a1b}
</style>
