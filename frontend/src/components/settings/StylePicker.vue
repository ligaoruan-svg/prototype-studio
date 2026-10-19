<script setup>
// 选风格：新建原型、设计规范里换风格都用它。
// 按「后台 / 中台 / 手机 / 自定义」分页签，一次只看一类的三张卡；卡片上是真实的预览图和一句短说明，
// 完整说明只在下面显示选中的那一套——以前十几张卡片一起铺开、每张都截断一段长说明，看着乱
import { computed, ref, watch } from 'vue'
import { Check, Upload } from 'lucide-vue-next'
const props = defineProps({
  styles: { type: Object, default: () => ({ builtin: [], mine: [] }) },
  modelValue: { type: String, default: '' },
  disabled: Boolean,
})
const emit = defineEmits(['update:modelValue', 'import'])
const TABS = ['后台', '中台', '手机', '自定义']
const NONE = { value: 'none', name: '不选风格', tagline: '只按设计规范', layout: 'none', tab: '自定义',
  description: '只按设计规范，AI 自己定样子。导入已有原型时默认这项，保持原样' }
const all = computed(() => [
  ...(props.styles.builtin || []).map(s => ({ ...s, value: 'builtin:' + s.folder, tab: TABS.includes(s.category) ? s.category : '自定义' })),
  ...(props.styles.mine || []).map(s => ({ ...s, value: 'mine:' + s.folder, tab: '自定义', mine: true,
    tagline: s.has_shell ? '自己导入的风格' : '没有页面外壳，只当规矩用' })),
  NONE,
])
const tabOf = value => all.value.find(c => c.value === value)?.tab || TABS[0]
const tab = ref(tabOf(props.modelValue))
// 清单是打开弹窗后才拿到的、选中的也可能从外面改：都跟着跳到选中那一套所在的页签
watch([() => props.modelValue, () => all.value.length], () => { tab.value = tabOf(props.modelValue) })
const cards = computed(() => all.value.filter(c => c.tab === tab.value))
const current = computed(() => all.value.find(c => c.value === props.modelValue))
const preview = card => card.has_preview ? `/api/styles/${card.mine ? 'mine' : 'builtin'}/${encodeURIComponent(card.folder)}/preview.png` : ''
const BAR_HEIGHTS = [42, 58, 36, 66, 74]
function pick(card) { if (!props.disabled && card.value !== props.modelValue) emit('update:modelValue', card.value) }
</script>

<template>
<div class="style-picker">
  <div class="style-tabs" role="tablist">
    <button v-for="t in TABS" :key="t" type="button" role="tab" :aria-selected="tab === t" :class="{ active: tab === t }" @click="tab = t">
      {{ $t(t) }}<i v-if="current?.tab === t" class="dot" :title="$t('当前选的在这一类')"></i>
    </button>
  </div>
  <div class="style-grid" role="radiogroup" :aria-label="$t('风格')">
    <button v-for="card in cards" :key="card.value" type="button" role="radio" class="style-card" :class="{ on: modelValue === card.value }" :aria-checked="modelValue === card.value" :disabled="disabled" @click="pick(card)">
      <span class="thumb" :class="'is-' + card.layout" :style="{ '--p': card.primary, '--b': card.background, '--side': card.side || '#ffffff' }" aria-hidden="true">
        <img v-if="preview(card)" :src="preview(card)" alt="" loading="lazy">
        <template v-else-if="card.layout === 'sidebar'"><i class="t-side"></i><i class="t-row"></i><i class="t-row short"></i><i class="t-btn"></i></template>
        <template v-else-if="card.layout === 'topbar'"><i class="t-topbar"></i><i class="t-sub"></i><i class="t-row low"></i><i class="t-row short low2"></i><i class="t-btn low"></i></template>
        <template v-else-if="card.layout === 'screen'"><i class="t-title"></i><i v-for="h in BAR_HEIGHTS" :key="h" class="t-bar" :style="{ height: h + '%' }"></i></template>
        <template v-else-if="card.layout === 'mobile'"><i class="t-phone"><i class="t-card"></i><i class="t-card"></i><i class="t-tab"></i></i></template>
        <i v-else class="t-blank"></i>
        <Check v-if="modelValue === card.value" class="t-check" :size="11" :stroke-width="3" />
      </span>
      <span class="style-name"><span>{{ $t(card.name) }}</span><em v-if="card.mine">{{ $t('我的') }}</em></span>
      <small :class="{ warn: card.mine && !card.has_shell }">{{ $t(card.tagline || card.description) }}</small>
    </button>
    <button v-if="tab === '自定义'" type="button" class="style-card import" :disabled="disabled" @click="emit('import')">
      <span class="thumb is-import" aria-hidden="true"><Upload :size="18" /></span>
      <span class="style-name"><span>{{ $t('导入风格') }}</span></span>
      <small>{{ $t('带 SKILL.md 的 zip') }}</small>
    </button>
  </div>
  <p class="style-detail"><template v-if="current"><b>{{ $t(current.name) }}</b>{{ $t(current.description) }}</template></p>
</div>
</template>

<style scoped>
.style-tabs{display:flex;gap:18px;border-bottom:1px solid var(--line);margin-bottom:12px}
.style-tabs button{position:relative;padding:6px 0 9px;border:0;background:none;font-size:12px;color:var(--muted);cursor:pointer;box-shadow:inset 0 -2px transparent}
.style-tabs button:hover{color:var(--ink)}
.style-tabs button.active{color:var(--ink);font-weight:550;box-shadow:inset 0 -2px var(--primary)}
.style-tabs .dot{position:absolute;top:5px;right:-7px;width:5px;height:5px;border-radius:50%;background:var(--primary)}
.style-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.style-card{display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;gap:4px;min-width:0;height:auto;padding:6px 6px 9px;border:1px solid var(--line);border-radius:12px;background:var(--surface);text-align:left;white-space:normal;cursor:pointer;color:var(--ink)}
.style-card:hover:not(:disabled){border-color:#d6ccc6}
.style-card.on{border-color:var(--primary);box-shadow:0 0 0 2px color-mix(in srgb,var(--primary) 16%,transparent)}
.style-card.import{border-style:dashed;background:transparent}
.style-card:disabled{cursor:default;opacity:.7}
.style-name{display:flex;align-items:center;gap:6px;padding:4px 3px 0;font-size:12.5px;font-weight:550;min-width:0}
.style-name>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.style-name em{flex:none;font-style:normal;font-size:10px;font-weight:400;padding:0 6px;line-height:16px;border-radius:999px;background:#f6e9e2;color:#9a3e1b}
small{padding:0 3px;font-size:11px;line-height:1.5;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
small.warn{color:#9a5a00}
.thumb{position:relative;display:block;aspect-ratio:16/10;border-radius:8px;background:var(--b,#f6f7f9);overflow:hidden;box-shadow:inset 0 0 0 1px #0000000f}
.thumb img{display:block;width:100%;height:100%;object-fit:cover}
.thumb i{display:block}
.t-side{position:absolute;left:0;top:0;bottom:0;width:24%;background:var(--side);box-shadow:inset -1px 0 #0000000f}
.t-row{position:absolute;left:32%;right:8%;top:20%;height:15%;border-radius:3px;background:#fff;box-shadow:0 0 0 1px #00000012}
.t-row.short{top:44%;right:34%}
.t-btn{position:absolute;right:8%;top:70%;width:20%;height:13%;border-radius:3px;background:var(--p)}
.t-topbar{position:absolute;left:0;right:0;top:0;height:20%;background:var(--side);box-shadow:inset 0 -1px #0000000f}
.t-sub{position:absolute;left:0;top:20%;bottom:0;width:20%;background:#fff;box-shadow:inset -1px 0 #0000000f}
.t-row.low{top:34%;left:28%}
.t-row.low2{top:56%;left:28%}
.t-btn.low{top:78%}
.is-screen{display:flex;align-items:flex-end;justify-content:center;gap:6%;padding:0 14% 9%}
.t-title{position:absolute;left:32%;right:32%;top:11%;height:7%;border-radius:2px;background:#ffffff59}
.t-bar{width:9%;border-radius:2px 2px 0 0;background:var(--p);opacity:.85}
.is-mobile{display:grid;place-items:center}
.t-phone{position:relative;width:27%;height:86%;padding:12% 7% 0;border-radius:6px;background:#fff;box-shadow:0 0 0 1px #00000014}
.t-card{height:22%;margin-bottom:12%;border-radius:3px;background:color-mix(in srgb,var(--p) 14%,#fff)}
.t-tab{position:absolute;left:0;right:0;bottom:0;height:13%;border-top:1px solid #0000000f;background:radial-gradient(circle at 50% 50%,var(--p) 0 2px,transparent 2.5px)}
.is-none{background:#fff;box-shadow:inset 0 0 0 1px var(--line)}
.t-blank{position:absolute;inset:22% 30%;border:1px dashed #c9c2bd;border-radius:4px}
.is-import{display:grid;place-items:center;background:transparent;box-shadow:inset 0 0 0 1px var(--line);color:var(--muted)}
.t-check{position:absolute;right:6px;top:6px;width:18px;height:18px;padding:3px;border-radius:50%;background:var(--primary);color:#fff;box-shadow:0 1px 3px #0003}
.style-detail{min-height:38px;margin:10px 0 0;padding:8px 11px;border-radius:9px;background:var(--quiet);font-size:11.5px;line-height:1.6;color:var(--muted)}
.style-detail b{color:var(--ink);font-weight:550;margin-right:8px}
@media (max-width:560px){.style-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
