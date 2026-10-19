<script setup>
// 选风格：新建原型、设计规范里换风格都用它。一张卡 = 一套风格（内置 / 我的），外加「不选风格」和「导入风格」
import { computed } from 'vue'
import { Check, Upload } from 'lucide-vue-next'
const props = defineProps({
  styles: { type: Object, default: () => ({ builtin: [], mine: [] }) },
  modelValue: { type: String, default: '' },
  disabled: Boolean,
})
const emit = defineEmits(['update:modelValue', 'import'])
const NONE = { value: 'none', name: '不选风格', description: '只按设计规范，AI 自己定样子。导入已有原型时默认这项，保持原样', layout: 'none' }
// 内置的按「后台 / 中台 / 手机」分组；自己导入的、不选风格、导入风格放最后一组
const GROUPS = ['后台', '中台', '手机']
const sections = computed(() => {
  const builtin = (props.styles.builtin || []).map(s => ({ ...s, value: 'builtin:' + s.folder }))
  const out = GROUPS.map(title => ({ title, cards: builtin.filter(s => s.category === title) }))
  const rest = builtin.filter(s => !GROUPS.includes(s.category))
  if (rest.length) out.push({ title: '其他', cards: rest })
  out.push({ title: '我的 · 其他', cards: [...(props.styles.mine || []).map(s => ({ ...s, value: 'mine:' + s.folder, tag: '我的' })), NONE], last: true })
  return out.filter(x => x.cards.length)
})
const BAR_HEIGHTS = [42, 58, 36, 66, 74]
function pick(card) { if (!props.disabled && card.value !== props.modelValue) emit('update:modelValue', card.value) }
</script>

<template>
<div class="style-sections" role="radiogroup" :aria-label="$t('风格')">
  <section v-for="section in sections" :key="section.title" class="style-section">
    <h4>{{ $t(section.title) }}</h4>
    <div class="style-grid">
      <button v-for="card in section.cards" :key="card.value" type="button" role="radio" class="style-card" :class="{ on: modelValue === card.value }" :aria-checked="modelValue === card.value" :disabled="disabled" @click="pick(card)">
        <span class="thumb" :class="'is-' + card.layout" :style="{ '--p': card.primary, '--b': card.background, '--side': card.side || '#ffffff' }" aria-hidden="true">
          <template v-if="card.layout === 'sidebar'"><i class="t-side"></i><i class="t-row"></i><i class="t-row short"></i><i class="t-btn"></i></template>
          <template v-else-if="card.layout === 'topbar'"><i class="t-topbar"></i><i class="t-sub"></i><i class="t-row low"></i><i class="t-row short low2"></i><i class="t-btn low"></i></template>
          <template v-else-if="card.layout === 'screen'"><i class="t-title"></i><i v-for="h in BAR_HEIGHTS" :key="h" class="t-bar" :style="{ height: h + '%' }"></i></template>
          <template v-else-if="card.layout === 'mobile'"><i class="t-phone"><i class="t-card"></i><i class="t-card"></i><i class="t-tab"></i></i></template>
          <i v-else class="t-blank"></i>
          <Check v-if="modelValue === card.value" class="t-check" :size="11" :stroke-width="3" />
        </span>
        <span class="style-name"><span>{{ $t(card.name) }}</span><em v-if="card.tag" class="mine">{{ $t(card.tag) }}</em></span>
        <small>{{ $t(card.description) }}</small>
        <small v-if="card.tag === '我的' && !card.has_shell" class="warn">{{ $t('没有页面外壳：只当规矩用，不能一键起页面') }}</small>
      </button>
      <button v-if="section.last" type="button" class="style-card import" :disabled="disabled" @click="emit('import')">
        <span class="thumb is-import" aria-hidden="true"><Upload :size="18" /></span>
        <span class="style-name"><span>{{ $t('导入风格') }}</span></span>
        <small>{{ $t('传一个带 SKILL.md 的 zip，装好后出现在「我的」') }}</small>
      </button>
    </div>
  </section>
</div>
</template>

<style scoped>
.style-sections{display:flex;flex-direction:column;gap:12px}
.style-section h4{margin:0 0 6px;font-size:11px;font-weight:500;color:var(--muted);letter-spacing:.04em}
.style-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.style-card{display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;gap:5px;min-width:0;white-space:normal;height:auto;padding:7px 7px 9px;border:1px solid var(--line);border-radius:12px;background:var(--surface);text-align:left;cursor:pointer;color:var(--ink)}
.style-card:hover:not(:disabled){border-color:#d6ccc6}
.style-card.on{border-color:var(--primary);box-shadow:0 0 0 2px color-mix(in srgb,var(--primary) 16%,transparent)}
.style-card.import{border-style:dashed;background:transparent}
.style-card:disabled{cursor:default;opacity:.7}
.style-name{display:flex;align-items:center;gap:6px;padding:0 2px;font-size:12px;font-weight:550;min-width:0}
.style-name>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.style-name em{flex:none;font-style:normal;font-size:10px;font-weight:400;padding:0 6px;line-height:16px;border-radius:999px;background:var(--quiet);color:var(--muted)}
.style-name em.mine{background:#f6e9e2;color:#9a3e1b}
small{padding:0 2px;font-size:10.5px;line-height:1.5;color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
small.warn{color:#9a5a00}
.thumb{position:relative;display:block;height:56px;border-radius:8px;background:var(--b,#f6f7f9);overflow:hidden;box-shadow:inset 0 0 0 1px #0000000d}
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
.t-blank{position:absolute;inset:20% 30%;border:1px dashed #c9c2bd;border-radius:4px}
.is-import{display:grid;place-items:center;background:transparent;box-shadow:none;border:1px dashed var(--line);color:var(--muted)}
.t-check{position:absolute;right:5px;top:5px;width:16px;height:16px;padding:2px;border-radius:50%;background:var(--primary);color:#fff}
@media (max-width:560px){.style-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
