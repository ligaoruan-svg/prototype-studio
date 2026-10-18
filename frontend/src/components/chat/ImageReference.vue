<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { Scan, Trash2 } from 'lucide-vue-next'
const props = defineProps({ reference: { type: Object, required: true } })
const emit = defineEmits(['update'])
const surface = ref(null), draft = ref(null), start = ref(null), active = ref(-1)
function point(event) { const r = surface.value.getBoundingClientRect(); return { x: Math.max(0, Math.min(1, (event.clientX - r.left) / r.width)), y: Math.max(0, Math.min(1, (event.clientY - r.top) / r.height)) } }
function down(event) { if (event.button !== 0 || start.value || props.reference.regions.length >= 16) return; event.preventDefault(); start.value = point(event); if (Number.isInteger(event.pointerId)) surface.value.setPointerCapture(event.pointerId); draft.value = null }
function move(event) { if (!start.value) return; const p = point(event); draft.value = { x: Math.min(p.x, start.value.x), y: Math.min(p.y, start.value.y), w: Math.abs(p.x - start.value.x), h: Math.abs(p.y - start.value.y), note: '' } }
function up() { if (draft.value?.w > .01 && draft.value?.h > .01) { const at = props.reference.regions.length; emit('update', [...props.reference.regions, draft.value]); active.value = at } start.value = null; draft.value = null }
function style(box) { return { left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.w * 100}%`, height: `${box.h * 100}%` } }
function updateNote(i, note) { emit('update', props.reference.regions.map((box, j) => j === i ? { ...box, note } : box)) }
onMounted(() => { surface.value.addEventListener('mousedown', down); window.addEventListener('mousemove', move); window.addEventListener('mouseup', up) })
onUnmounted(() => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up) })
</script>

<template>
  <div class="reference-editor">
    <div class="reference-hint"><Scan :size="16" />{{ reference.regions.length >= 16 ? $t('已达到 16 个区域上限，可删除区域后重新框选') : $t('在截图上按住拖动，框出需要调整的区域') }}</div>
    <div class="reference-viewport"><div ref="surface" class="reference-surface" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="start = null; draft = null"><img :src="reference.data_url" :alt="$t(reference.name)" draggable="false"><div v-for="(box, i) in reference.regions" :key="i" class="reference-box" :class="{ active: active === i }" :style="style(box)"><span>{{ i + 1 }}</span></div><div v-if="draft" class="reference-box drawing" :style="style(draft)"></div></div></div>
    <div v-if="!reference.regions.length" class="field-hint">{{ $t('也可以直接参考整张图，在对话里描述希望借鉴的布局、配色或功能。') }}</div>
    <div class="reference-notes"><label v-for="(box, i) in reference.regions" :key="i"><span class="reference-number">{{ i + 1 }}</span><textarea :aria-label="$t('截图区域 {0} 修改意见', [i + 1])" :value="box.note" :placeholder="$t('这一块需要怎么改？')" rows="2" @focus="active = i" @input="updateNote(i, $event.target.value)"></textarea><button type="button" class="icon-button" :aria-label="$t('移除区域 {0}', [i + 1])" @click="emit('update', reference.regions.filter((_, j) => j !== i))"><Trash2 :size="14" /></button></label></div>
  </div>
</template>

<style scoped>
.reference-hint{display:flex;gap:8px;align-items:center;color:var(--primary);font-size:12px;margin:14px 0}
.reference-viewport{max-height:48vh;overflow:auto;background:#f1eeed;border:1px solid var(--line);border-radius:7px;padding:12px}
.reference-surface{position:relative;cursor:crosshair;touch-action:none;user-select:none;width:100%;line-height:0}
.reference-surface img{width:100%;display:block;pointer-events:none}
.reference-box{position:absolute;border:2px solid var(--primary);background:#60392515;pointer-events:none}
.reference-box.active{border-color:#e06f30;background:#e06f3012}
.reference-box>span{position:absolute;left:-2px;top:-2px;display:grid;place-items:center;line-height:1;width:19px;height:19px;background:var(--primary);color:white;font:11px system-ui;border-radius:0 0 4px 0}
.reference-box.active>span{background:#e06f30}
.reference-notes{display:flex;flex-direction:column;gap:10px;margin-top:16px;max-height:200px;overflow:auto}
.reference-notes label{display:flex;gap:8px;align-items:flex-start}
.reference-number{display:grid;place-items:center;width:21px;height:21px;background:var(--primary-soft);color:var(--primary);font-size:11px;border-radius:5px;margin-top:8px;flex-shrink:0}
.reference-notes textarea{flex:1;min-width:0;border:1px solid var(--line);border-radius:6px;padding:8px;font-size:12px}
</style>
