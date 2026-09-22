<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
const emit = defineEmits(['select', 'scroll'])
const root = ref(null), box = ref(null)
let start = null
function point(event) { const r = root.value.getBoundingClientRect(); return { x: Math.max(0, Math.min(r.width, event.clientX - r.left)), y: Math.max(0, Math.min(r.height, event.clientY - r.top)) } }
function down(event) { if (start || event.button !== 0) return; event.preventDefault(); start = point(event); box.value = null; if (Number.isInteger(event.pointerId)) root.value.setPointerCapture(event.pointerId) }
function move(event) { if (!start) return; const p = point(event); box.value = { left: Math.min(start.x, p.x), top: Math.min(start.y, p.y), right: Math.max(start.x, p.x), bottom: Math.max(start.y, p.y) } }
function up(event) { if (!start) return; move(event); start = null; if (box.value.right - box.value.left > 8 && box.value.bottom - box.value.top > 8) emit('select', box.value); else box.value = null }
function wheel(event) { event.preventDefault(); box.value = null; const p = point(event); emit('scroll', { x: p.x, y: p.y, deltaX: event.deltaX, deltaY: event.deltaY }) }
onMounted(() => { root.value.addEventListener('mousedown', down); root.value.addEventListener('wheel', wheel, { passive: false }); window.addEventListener('mousemove', move); window.addEventListener('mouseup', up) })
onUnmounted(() => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) })
</script>

<template>
  <div ref="root" class="region-capture" aria-label="拖动框选原型区域" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="start = null" @click.prevent.stop>
    <div v-if="box" class="region-rectangle" :style="{ left: box.left + 'px', top: box.top + 'px', width: box.right - box.left + 'px', height: box.bottom - box.top + 'px' }"></div>
  </div>
</template>

<style scoped>
.region-capture{position:absolute;inset:0;z-index:4;cursor:crosshair;touch-action:none;user-select:none}
.region-rectangle{position:absolute;pointer-events:none;border:2px solid var(--primary);background:#60392515}
</style>
