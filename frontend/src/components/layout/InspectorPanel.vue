<script setup>
// 从 App.vue 拆出来的一块界面：状态和函数都在 App 里，按同样的名字 inject 进来，模板原样不动
import { computed, inject } from 'vue'
import { AlertCircle, AlignCenter, AlignJustify, AlignLeft, AlignRight, ArrowUp, CheckCheck, Hand, Image as ImageIcon, Layers, LoaderCircle, MessageCircle, MessageSquare, MousePointer2, PanelLeftClose, PenLine, Pencil, Plus, Scan, SlidersHorizontal, Square, Type, X } from 'lucide-vue-next'
const {
  aiOnly, annotations, canEdit, closeSelection, colors, commentDraft, commentToAI,
  drawClear, drawing, dynEdit, edit, elementLabel, inspection, leftOpen, locked,
  model, playing, removeAnnotation, rightOpen, runAgent, saveNote, saving,
  selected, selectionPlace, setTool, shotUrl, showChat, showPanel, textEditable, textValue,
  tool, selectLayer, hoverLayer, toast
} = inject('studio')

// ── 编辑模式的属性分组：尺寸、布局、文字、填充、边框、效果 ──
const st = key => selected.value?.styles?.[key] || ''
const num = value => { const n = parseFloat(value); return Number.isFinite(n) ? Math.round(n * 10) / 10 : '' }
function setNumber(key, event, { max = 999, neg = false, more = null } = {}) {
  const raw = String(event.target.value ?? '').trim()
  if (!raw) return   // 清空了不是想改成 0
  const n = Math.round(Number(raw) * 100) / 100, low = neg ? -max : 0
  if (!Number.isFinite(n) || n < low || n > max) { toast(`请输入 ${low}–${max} 之间的数值`); event.target.value = num(st(key)); return }
  edit(key, `${n}px`, more)
}
const hex = value => {
  const m = String(value).match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/)
  return m ? '#' + m.slice(1, 4).map(x => Number(x).toString(16).padStart(2, '0')).join('') : '#000000'
}
const transparent = value => /rgba\([^)]*,\s*0\)|transparent/.test(String(value))

// 宽高：适应内容（Hug）/ 固定（Fixed）/ 填满（Fill）。在横向 flex 里「填满」用 flex: 1，不然 100% 会把兄弟挤出去
const SIZE_MODES = [ { key: 'hug', label: '适应', tip: '适应内容（Hug）：有多少内容就多大' }, { key: 'fixed', label: '固定', tip: '固定尺寸（Fixed）：写死像素' }, { key: 'fill', label: '填满', tip: '填满（Fill）：撑满父容器剩下的空间' } ]
const alongFlex = axis => { const p = selected.value?.parent || {}; return /flex/.test(p.display || '') && (axis === 'width') !== /column/.test(p.direction || '') }
function setSize(axis, mode) {
  if (!canEdit.value || selected.value?.size?.[axis] === mode) return
  const flex = alongFlex(axis)
  if (mode === 'fill') return flex ? edit('flex', '1 1 0%', { [axis]: 'auto' }) : edit(axis, '100%')
  if (mode === 'hug') return edit(axis, 'fit-content', flex ? { flex: '0 0 auto' } : null)
  const n = Math.round(parseFloat(st(axis)) || 0)
  if (n > 999) { toast('超过 999px，请在输入框里写一个更小的值'); return }
  edit(axis, `${n}px`, flex ? { flex: '0 0 auto' } : null)
}
const sizeMore = axis => alongFlex(axis) ? { flex: '0 0 auto' } : null

// 排列：不排 / 横向 / 纵向（一次修改里同时写 display 和方向）
const arrange = computed(() => /flex/.test(st('display')) ? (/column/.test(st('flex-direction')) ? 'column' : 'row') : /grid/.test(st('display')) ? 'grid' : 'none')
const ARRANGE = [ { key: 'none', label: '不排' }, { key: 'row', label: '横向' }, { key: 'column', label: '纵向' } ]
function setArrange(key) {
  if (!canEdit.value || arrange.value === key) return
  if (key === 'none') return edit('display', 'block')
  edit('display', 'flex', { 'flex-direction': key })
}
const ALIGN = [ ['flex-start', '靠前'], ['center', '居中'], ['flex-end', '靠后'], ['stretch', '拉伸'], ['baseline', '基线'] ]
const JUSTIFY = [ ['flex-start', '靠前'], ['center', '居中'], ['flex-end', '靠后'], ['space-between', '两端分布'], ['space-around', '均匀分布'] ]
const WEIGHTS = [ ['300', '细'], ['400', '常规'], ['500', '中等'], ['600', '半粗'], ['700', '粗'] ]
const TEXT_ALIGN = [ { key: 'left', icon: AlignLeft, label: '左对齐' }, { key: 'center', icon: AlignCenter, label: '居中' }, { key: 'right', icon: AlignRight, label: '右对齐' }, { key: 'justify', icon: AlignJustify, label: '两端对齐' } ]
const textAlign = computed(() => { const v = st('text-align'); return v === 'start' ? 'left' : v === 'end' ? 'right' : v })
const BOX = [ ['top', '上'], ['right', '右'], ['bottom', '下'], ['left', '左'] ]
const BORDER_STYLES = [ ['none', '无'], ['solid', '实线'], ['dashed', '虚线'], ['dotted', '点线'] ]
// 阴影只给几档现成的，值和后端白名单一字不差
const SHADOWS = [ ['none', '无'], ['0 1px 2px rgba(0,0,0,.06)', '轻'], ['0 4px 12px rgba(0,0,0,.08)', '中'], ['0 12px 32px rgba(0,0,0,.12)', '重'] ]
const opacity = computed(() => { const n = parseFloat(st('opacity')); return Number.isFinite(n) ? Math.round(n * 100) : 100 })
function setOpacity(event) { const v = Number(event.target.value); edit('opacity', v >= 100 ? '1' : v <= 0 ? '0' : String(Math.round(v) / 100)) }

// 图层：往上几层祖先、自己、直接子元素；点一下换着选，移上去在页面上框出来
const TAG_NAMES = { body: '页面', div: '容器', section: '区块', main: '主体', header: '页眉', footer: '页脚', nav: '导航', aside: '侧栏', ul: '列表', ol: '列表', li: '列表项', a: '链接', button: '按钮', img: '图片', svg: '图标', input: '输入框', select: '下拉框', textarea: '多行输入', table: '表格', thead: '表头', tbody: '表体', tr: '行', td: '单元格', th: '表头格', p: '段落', span: '文字', label: '标签', form: '表单', h1: '标题', h2: '标题', h3: '标题', h4: '标题', h5: '标题', h6: '标题', strong: '加粗', i: '图标', em: '强调', small: '小字' }
const layerName = l => TAG_NAMES[l.tag] || l.tag
const layerIcon = l => l.tag === 'img' || l.tag === 'svg' ? ImageIcon : (!l.kids && l.text) || /^(p|span|h\d|label|strong|em|small)$/.test(l.tag) ? Type : Square
const depth = i => ({ '--depth': Math.min(i, 7) })
const layers = computed(() => selected.value?.layers || null)
const self = computed(() => ({ tag: selected.value?.tag || '', cls: '', text: (selected.value?.text || '').slice(0, 24), kids: selected.value?.leaf ? 0 : 1 }))
</script>

<template>
<aside class="inspector" :class="{ collapsed: !rightOpen }" :aria-label="$t('属性面板')">
  <div class="panel-header"><div class="side-tabs" role="tablist" :aria-label="$t('左侧面板')"><button type="button" role="tab" :aria-selected="!rightOpen" :class="{ active: !rightOpen }" @click="showChat"><MessageSquare :size="14" />{{ $t('对话') }}</button><button type="button" role="tab" :aria-selected="rightOpen" :class="{ active: rightOpen }" @click="showPanel"><component :is="tool === 'comment' ? MessageCircle : SlidersHorizontal" :size="14" />{{ tool === 'comment' ? $t('评论') : $t('属性') }}<span v-if="tool === 'comment' && annotations.length" class="count">{{ $t(annotations.length) }}</span></button></div><button class="icon-button" :aria-label="$t('收起左侧面板')" @click="leftOpen = false; rightOpen = false"><PanelLeftClose :size="16" /></button></div>
  <p class="side-hint">{{ tool === 'comment' ? $t('写下怎么改，交给 AI 修改') : aiOnly ? $t('这里要交给 AI 修改') : $t('直接改，马上生效，不调用 AI') }}</p>
  <div class="inspector-scroll">
    <div v-if="!selected && (tool !== 'comment' || !annotations.length)" class="inspector-empty"><component :is="tool === 'comment' ? MessageCircle : tool === 'edit' ? Pencil : Hand" :size="28" :stroke-width="1.3" /><h2>{{ tool === 'comment' ? $t('评论：告诉 AI 怎么改') : tool === 'edit' ? $t('编辑：自己动手改') : $t('浏览中') }}</h2><p v-if="tool === 'comment'">{{ $t('点一下要改的元素，或者') }}<b>{{ $t('按住拖动直接在页面上画') }}</b>{{ $t('（画圈、划线），') }}<br>{{ $t('写下怎么改，交给 AI 去改代码。') }}</p><p v-else-if="tool === 'edit'">{{ $t('点一下元素，在这里') }}<b>{{ $t('直接改') }}</b>{{ $t('文字、颜色、字号、间距，') }}<br>{{ $t('马上生效，不调用 AI、不花 token。') }}</p><p v-else>{{ $t('像用户一样点页面。') }}<br>{{ $t('要改东西，切到「评论」或「编辑」。') }}</p><p v-if="tool !== 'comment' && annotations.length" class="field-hint">{{ $t('页面上有 {0} 条评论，切到「评论」（C）查看', [$t(annotations.length)]) }}</p></div>
    <div v-else-if="!selected" class="noted-panel">
      <div class="section-label">{{ $t('已记下的意见') }}<span class="count">{{ $t(annotations.length) }}</span></div>
      <div v-for="(a, i) in annotations" :key="a.id" class="annotation-row"><span class="annotation-number">{{ i + 1 }}</span><div><img v-if="a.shot" class="ann-shot" :src="shotUrl(a)" :alt="$t('评论截图')"><b v-else>{{ a.kind === 'region' ? $t('框选 {0} 个元素', [a.targets?.length || 0]) : (a.text?.slice(0, 30) || a.tag) }}</b><p>{{ a.note }}</p></div><button class="icon-button" :aria-label="$t('移除这条意见')" :disabled="locked" @click="removeAnnotation(a.id)"><X :size="14" /></button></div>
      <p class="field-hint">{{ tool === 'comment' ? $t('继续点或框下一处，或一起交给 AI 修改。') : $t('按 C 切到评论，继续标下一处。') }}</p>
      <button class="primary full-width" :disabled="locked" @click="runAgent($t('请逐条处理已记下的修改意见，保留其他区域。'), '', { intent: 'edit' })"><CheckCheck :size="15" />{{ $t('这 {0} 条一起修改', [$t(annotations.length)]) }}</button>
    </div>
    <template v-else-if="tool === 'comment' && selected.drawing">
      <div class="selected-heading"><span class="element-icon"><PenLine :size="17" /></span><div><h2>{{ $t('画了 {0} 笔', [drawing?.count || 0]) }}</h2><small>{{ $t('圈到 {0} 个元素 · 在画布下方写说明', [selected.targets?.length || 0]) }}</small></div><button class="icon-button" :aria-label="$t('取消这次标记')" @click="drawClear"><X :size="14" /></button></div>
      <p class="field-hint draw-hint">{{ $t('可以接着画，几笔算一条评论。{0}', [model.supports_vision ? $t('发送时会带上这块页面的截图（红圈也在上面）。') : $t('当前模型看不了图片，只把圈到的元素位置交给 AI。')]) }}</p>
      <div v-if="annotations.length" class="noted-panel"><div class="section-label">{{ $t('已记下的评论') }}<span class="count">{{ $t(annotations.length) }}</span></div><div v-for="(a, i) in annotations" :key="a.id" class="annotation-row"><span class="annotation-number">{{ i + 1 }}</span><div><img v-if="a.shot" class="ann-shot" :src="shotUrl(a)" :alt="$t('评论截图')"><b v-else>{{ a.kind === 'region' ? $t('框选 {0} 个元素', [a.targets?.length || 0]) : (a.text?.slice(0, 30) || a.tag) }}</b><p>{{ a.note }}</p></div><button class="icon-button" :aria-label="$t('移除这条评论')" :disabled="locked" @click="removeAnnotation(a.id)"><X :size="14" /></button></div></div>
    </template>
    <template v-else-if="tool === 'comment'">
      <div class="selected-heading"><span class="element-icon"><MessageCircle :size="17" /></span><div><h2>{{ selected.kind === 'region' ? $t('框选了 {0} 个元素', [selected.targets?.length || 0]) : elementLabel(selected) }}</h2><small>{{ selectionPlace || $t('写下这里要怎么改') }}</small></div><button class="icon-button" :aria-label="$t('取消选择')" @click="closeSelection"><X :size="14" /></button></div>
      <section class="property-section comment-box">
        <div v-if="selected.kind === 'region'" class="region-list"><span v-for="(target, index) in selected.targets" :key="index">{{ target.text?.slice(0, 28) || target.tag }}</span></div>
        <textarea v-model="commentDraft" class="text-property" rows="4" maxlength="1000" :placeholder="$t('比如：这一块改成卡片布局；按钮换成描边样式')" :aria-label="$t('评论内容')" @keydown.meta.enter.prevent="commentToAI" @keydown.ctrl.enter.prevent="commentToAI"></textarea>
        <div class="comment-actions"><button class="outline" :disabled="locked || saving || !commentDraft.trim()" :title="$t('先记下，攒几条一起改')" @click="saveNote(commentDraft)"><Plus :size="14" />{{ $t('添加评论') }}</button><button class="primary" :disabled="locked || !commentDraft.trim()" title="⌘/Ctrl ↵" @click="commentToAI"><ArrowUp :size="14" />{{ $t('直接交给 AI') }}</button></div>
        <p class="field-hint">{{ $t('点下一个元素会换成那一个；按住 Shift 可以多选。记下的评论会钉在页面上。') }}</p>
      </section>
      <div v-if="annotations.length" class="noted-panel"><div class="section-label">{{ $t('已记下的评论') }}<span class="count">{{ $t(annotations.length) }}</span></div><div v-for="(a, i) in annotations" :key="a.id" class="annotation-row"><span class="annotation-number">{{ i + 1 }}</span><div><img v-if="a.shot" class="ann-shot" :src="shotUrl(a)" :alt="$t('评论截图')"><b v-else>{{ a.kind === 'region' ? $t('框选 {0} 个元素', [a.targets?.length || 0]) : (a.text?.slice(0, 30) || a.tag) }}</b><p>{{ a.note }}</p></div><button class="icon-button" :aria-label="$t('移除这条评论')" :disabled="locked" @click="removeAnnotation(a.id)"><X :size="14" /></button></div><button class="primary full-width" :disabled="locked" @click="runAgent($t('请逐条处理已记下的修改意见，保留其他区域。'), '', { intent: 'edit' })"><CheckCheck :size="15" />{{ $t('这 {0} 条一起修改', [$t(annotations.length)]) }}</button></div>
    </template>
    <template v-else>
      <div class="selected-heading"><span class="element-icon"><MousePointer2 :size="17" /></span><div><h2>{{ elementLabel(selected) }}</h2><small>{{ aiOnly ? $t('只读') : $t('直接修改 · 不调用 AI') }}</small></div><button class="icon-button" :aria-label="$t('取消选择')" @click="closeSelection"><X :size="14" /></button></div>
      <details v-if="layers" class="prop-group layer-group" open>
        <summary>{{ $t('图层') }}<span>{{ $t('点一层换着选') }}</span></summary>
        <ul class="layer-tree" @mouseleave="hoverLayer('')">
          <li v-if="layers.cut" class="layer-cut">{{ $t('上面还有 {0} 层', [$t(layers.cut)]) }}</li>
          <li v-for="(l, i) in layers.up" :key="'u' + l.selector" :style="depth(i)"><button type="button" :title="$t(l.selector)" @click="selectLayer(l.selector)" @mouseenter="hoverLayer(l.selector)" @focus="hoverLayer(l.selector)"><component :is="layerIcon(l)" :size="13" /><b>{{ $t(layerName(l)) }}</b><small>{{ l.text || (l.cls ? '.' + l.cls : '') }}</small></button></li>
          <li class="current" :style="depth(layers.up.length)" aria-current="true"><span><component :is="layerIcon(self)" :size="13" /><b>{{ $t(layerName(self)) }}</b><small>{{ self.text }}</small></span></li>
          <li v-for="l in layers.down" :key="'d' + l.selector" :style="depth(layers.up.length + 1)"><button type="button" :title="$t(l.selector)" @click="selectLayer(l.selector)" @mouseenter="hoverLayer(l.selector)" @focus="hoverLayer(l.selector)"><component :is="layerIcon(l)" :size="13" /><b>{{ $t(layerName(l)) }}</b><small>{{ l.text || (l.cls ? '.' + l.cls : '') }}</small><i v-if="l.kids" class="layer-kids">{{ $t(l.kids) }}</i></button></li>
          <li v-if="layers.more" class="layer-cut" :style="depth(layers.up.length + 1)">{{ $t('还有 {0} 个子元素', [$t(layers.more)]) }}</li>
        </ul>
      </details>
      <p v-if="!inspection" class="inspector-loading"><LoaderCircle class="spin" :size="14" />{{ $t('定位中…') }}</p><p v-else-if="inspection.failed" class="inspector-loading">{{ $t('没能在源码里定位这个元素，不能直接改属性；可以在下面写意见交给 AI') }}</p>
      <div v-else-if="aiOnly && (selected.card || selected.modal)" class="dynamic-note"><AlertCircle :size="16" /><div><b>{{ selected.kind === 'region' ? $t('已选中 {0} 个元素', [selected.targets?.length || 0]) : $t('这里不能直接改') }}</b><p>{{ selected.kind === 'region' ? $t('多个元素一起改，用评论告诉 AI 怎么改。') : selected.modal ? $t('这是弹窗里的内容，弹窗是脚本临时生成的，要由 AI 改对应的代码。') : $t('这是页面脚本生成的内容，要由 AI 改对应的代码。') }}</p><button class="outline" @click="setTool('comment')"><MessageCircle :size="14" />{{ $t('改成评论') }}</button></div></div>
      <div v-else-if="!inspection.editable && !dynEdit" class="dynamic-note"><Scan v-if="selected.kind === 'region'" :size="16" /><AlertCircle v-else :size="16" /><div><b>{{ selected.kind === 'region' ? $t('已选中 {0} 个元素', [$t(selected.targets.length)]) : $t('这是代码生成的内容') }}</b><p>{{ selected.kind === 'region' ? $t('多个元素一起改，用评论告诉 AI 怎么改。') : $t('它是页面脚本渲染出来的（列表、模板里的数据），不能直接改。用评论告诉 AI 怎么改，它会去改对应的代码。') }}</p><button class="outline" @click="setTool('comment')"><MessageCircle :size="14" />{{ $t('改成评论') }}</button><div v-if="selected.targets" class="region-targets"><span v-for="(target, index) in selected.targets" :key="index">{{ target.text?.slice(0, 28) || target.tag }}</span></div></div></div>
      <template v-else>
        <div v-if="playing" class="dynamic-note play-note"><Hand :size="16" /><div><b>{{ $t('浏览中 · 属性只读') }}</b><p>{{ $t('浏览时的操作不会保存。要改这个元素，先切到编辑。') }}</p><button class="outline" @click="setTool('edit')">{{ $t('切到编辑') }}</button></div></div>
        <div v-if="dynEdit" class="dyn-note"><Layers :size="14" /><p><b>{{ $t('脚本生成的元素') }}</b>{{ $t('{0}文字能找到原样的那一处才能直接改。', [selected.styleCount > 1 ? $t('改样式会作用到页面上同类的 {0} 个元素（比如每张卡片里的同一位置），', [$t(selected.styleCount)]) : $t('改样式只作用到它自己，')]) }}</p></div>
        <section class="property-section"><div class="section-label">{{ $t('内容') }}<span>{{ $t('当前元素') }}</span></div><label class="field-label" for="element-text">{{ $t('文字') }}</label><textarea id="element-text" class="text-property" v-model="textValue" :disabled="!canEdit || !textEditable" @change="edit('text', textValue)"></textarea><p v-if="!textEditable" class="field-hint">{{ !dynEdit ? $t('包含子元素，请点选具体文字进行编辑。') : !selected.leaf ? $t('包含子元素，请点选具体文字。') : inspection.literal_count > 1 ? $t('这段字在源码里出现了好几处，没法确定改哪一处，用评论交给 AI。') : $t('这是脚本算出来的内容（数字、统计结果），用评论交给 AI。') }}</p></section>
        <p v-if="dynEdit && selected.styleCount > 1" class="field-hint group-scope">{{ $t('下面的样式会作用到同类 {0} 个元素。', [$t(selected.styleCount)]) }}</p>
        <details class="prop-group" open>
          <summary>{{ $t('尺寸') }}</summary>
          <div v-for="axis in ['width', 'height']" :key="axis" class="size-row">
            <span class="prop-name">{{ axis === 'width' ? $t('宽') : $t('高') }}</span>
            <div class="seg" role="radiogroup" :aria-label="axis === 'width' ? $t('宽度') : $t('高度')"><button v-for="m in SIZE_MODES" :key="m.key" type="button" role="radio" :aria-checked="selected.size?.[axis] === m.key" :class="{ active: selected.size?.[axis] === m.key }" :title="$t(m.tip)" :disabled="!canEdit" @click="setSize(axis, m.key)">{{ $t(m.label) }}</button></div>
            <div class="number-control"><input type="number" min="0" max="999" :aria-label="axis === 'width' ? $t('宽度') : $t('高度')" :value="num(st(axis))" :disabled="!canEdit" @change="setNumber(axis, $event, { more: sizeMore(axis) })"><span>px</span></div>
          </div>
        </details>
        <details class="prop-group" open>
          <summary>{{ $t('布局') }}</summary>
          <div class="prop-row"><span class="prop-name">{{ $t('排列') }}</span><div class="seg" role="radiogroup" :aria-label="$t('排列方式')"><button v-for="a in ARRANGE" :key="a.key" type="button" role="radio" :aria-checked="arrange === a.key" :class="{ active: arrange === a.key }" :disabled="!canEdit" @click="setArrange(a.key)">{{ $t(a.label) }}</button></div></div>
          <p v-if="arrange === 'grid'" class="field-hint">{{ $t('这是网格布局，列数要交给 AI 改。') }}</p>
          <template v-if="arrange === 'row' || arrange === 'column'">
            <div class="prop-row"><span class="prop-name">{{ $t('对齐') }}</span><select class="prop-select" :aria-label="$t('交叉轴对齐')" :value="st('align-items')" :disabled="!canEdit" @change="edit('align-items', $event.target.value)"><option v-if="!ALIGN.some(([v]) => v === st('align-items'))" :value="st('align-items')" disabled>{{ st('align-items') === 'normal' || !st('align-items') ? $t('默认') : st('align-items') }}</option><option v-for="[v, label] in ALIGN" :key="v" :value="v">{{ $t(label) }}</option></select></div>
            <div class="prop-row"><span class="prop-name">{{ $t('分布') }}</span><select class="prop-select" :aria-label="$t('主轴分布')" :value="st('justify-content')" :disabled="!canEdit" @change="edit('justify-content', $event.target.value)"><option v-if="!JUSTIFY.some(([v]) => v === st('justify-content'))" :value="st('justify-content')" disabled>{{ st('justify-content') === 'normal' ? $t('默认') : st('justify-content') }}</option><option v-for="[v, label] in JUSTIFY" :key="v" :value="v">{{ $t(label) }}</option></select></div>
          </template>
          <div v-if="arrange !== 'none'" class="prop-row"><span class="prop-name">{{ $t('间距') }}</span><div class="number-control"><input type="number" min="0" max="999" :aria-label="$t('子元素间距')" :value="num(st('gap'))" placeholder="0" :disabled="!canEdit" @change="setNumber('gap', $event)"><span>px</span></div></div>
          <div class="box-label">{{ $t('内边距') }}</div>
          <div class="box-grid"><label v-for="[side, label] in BOX" :key="side"><span>{{ $t(label) }}</span><input type="number" min="0" max="999" :aria-label="$t('内边距') + label" :value="num(st('padding-' + side))" :disabled="!canEdit" @change="setNumber('padding-' + side, $event)"></label></div>
          <div class="box-label">{{ $t('外边距') }}</div>
          <div class="box-grid"><label v-for="[side, label] in BOX" :key="side"><span>{{ $t(label) }}</span><input type="number" min="-999" max="999" :aria-label="$t('外边距') + label" :value="num(st('margin-' + side))" :disabled="!canEdit" @change="setNumber('margin-' + side, $event, { neg: true })"></label></div>
        </details>
        <details class="prop-group" open>
          <summary>{{ $t('文字') }}</summary>
          <div class="pair-grid">
            <label><span>{{ $t('字号') }}</span><div class="number-control"><input type="number" min="0" max="999" :aria-label="$t('字号')" :value="num(st('font-size'))" :disabled="!canEdit" @change="setNumber('font-size', $event)"><span>px</span></div></label>
            <label><span>{{ $t('字重') }}</span><select class="prop-select" :aria-label="$t('字重')" :value="st('font-weight')" :disabled="!canEdit" @change="edit('font-weight', $event.target.value)"><option v-if="!WEIGHTS.some(([v]) => v === st('font-weight'))" :value="st('font-weight')" disabled>{{ st('font-weight') }}</option><option v-for="[v, label] in WEIGHTS" :key="v" :value="v">{{ $t(label) }} {{ $t(v) }}</option></select></label>
            <label><span>{{ $t('行高') }}</span><div class="number-control"><input type="number" min="0" max="999" :aria-label="$t('行高')" :value="num(st('line-height'))" :placeholder="$t('自动')" :disabled="!canEdit" @change="setNumber('line-height', $event)"><span>px</span></div></label>
            <label><span>{{ $t('字间距') }}</span><div class="number-control"><input type="number" min="-99" max="99" step="0.5" :aria-label="$t('字间距')" :value="st('letter-spacing') === 'normal' ? 0 : num(st('letter-spacing'))" :disabled="!canEdit" @change="setNumber('letter-spacing', $event, { max: 99, neg: true })"><span>px</span></div></label>
          </div>
          <div class="prop-row"><span class="prop-name">{{ $t('对齐') }}</span><div class="seg icons" role="radiogroup" :aria-label="$t('文字对齐')"><button v-for="a in TEXT_ALIGN" :key="a.key" type="button" role="radio" :aria-checked="textAlign === a.key" :aria-label="$t(a.label)" :title="$t(a.label)" :class="{ active: textAlign === a.key }" :disabled="!canEdit" @click="textAlign !== a.key && edit('text-align', a.key)"><component :is="a.icon" :size="14" /></button></div></div>
          <label class="color-field"><span>{{ $t('颜色') }}</span><div><input type="color" class="swatch" :aria-label="$t('自定义文字颜色')" :value="hex(st('color'))" :disabled="!canEdit" @change="edit('color', $event.target.value)"><select :aria-label="$t('文字颜色')" value="" :disabled="!canEdit" @change="edit('color', $event.target.value)"><option value="" disabled>{{ hex(st('color')) }}</option><option v-for="color in colors" :key="color.key" :value="`var(${color.key})`">{{ $t(color.label) }} · {{ $t(color.value) }}</option></select></div></label>
        </details>
        <details class="prop-group" open>
          <summary>{{ $t('填充') }}</summary>
          <label class="color-field"><span>{{ $t('背景') }}</span><div><input type="color" class="swatch" :class="{ empty: transparent(st('background-color')) }" :aria-label="$t('自定义背景颜色')" :value="hex(st('background-color'))" :disabled="!canEdit" @change="edit('background-color', $event.target.value)"><select :aria-label="$t('背景颜色')" value="" :disabled="!canEdit" @change="edit('background-color', $event.target.value)"><option value="" disabled>{{ transparent(st('background-color')) ? $t('无') : hex(st('background-color')) }}</option><option value="transparent">{{ $t('无（透明）') }}</option><option v-for="color in colors" :key="color.key" :value="`var(${color.key})`">{{ $t(color.label) }} · {{ $t(color.value) }}</option></select></div></label>
        </details>
        <details class="prop-group" open>
          <summary>{{ $t('边框') }}</summary>
          <div class="pair-grid">
            <label><span>{{ $t('圆角') }}</span><div class="number-control"><input type="number" min="0" max="999" :aria-label="$t('圆角')" :value="num(st('border-radius'))" :disabled="!canEdit" @change="setNumber('border-radius', $event)"><span>px</span></div></label>
            <label><span>{{ $t('描边') }}</span><div class="number-control"><input type="number" min="0" max="99" :aria-label="$t('描边粗细')" :value="st('border-style') === 'none' ? 0 : num(st('border-width'))" :disabled="!canEdit" @change="setNumber('border-width', $event, { max: 99, more: st('border-style') === 'none' ? { 'border-style': 'solid' } : null })"><span>px</span></div></label>
          </div>
          <div class="prop-row"><span class="prop-name">{{ $t('样式') }}</span><select class="prop-select" :aria-label="$t('描边样式')" :value="st('border-style')" :disabled="!canEdit" @change="edit('border-style', $event.target.value)"><option v-for="[v, label] in BORDER_STYLES" :key="v" :value="v">{{ $t(label) }}</option></select></div>
          <label v-if="st('border-style') !== 'none'" class="color-field"><span>{{ $t('颜色') }}</span><div><input type="color" class="swatch" :aria-label="$t('自定义描边颜色')" :value="hex(st('border-color'))" :disabled="!canEdit" @change="edit('border-color', $event.target.value)"><select :aria-label="$t('描边颜色')" value="" :disabled="!canEdit" @change="edit('border-color', $event.target.value)"><option value="" disabled>{{ hex(st('border-color')) }}</option><option v-for="color in colors" :key="color.key" :value="`var(${color.key})`">{{ $t(color.label) }} · {{ $t(color.value) }}</option></select></div></label>
        </details>
        <details class="prop-group" open>
          <summary>{{ $t('效果') }}</summary>
          <div class="prop-row"><span class="prop-name">{{ $t('不透明度') }}</span><div class="range-control"><input type="range" min="0" max="100" step="5" :aria-label="$t('不透明度')" :value="opacity" :disabled="!canEdit" @change="setOpacity"><b>{{ $t(opacity) }}%</b></div></div>
          <div class="prop-row"><span class="prop-name">{{ $t('阴影') }}</span><select class="prop-select" :aria-label="$t('阴影')" :value="st('box-shadow') === 'none' ? 'none' : ''" :disabled="!canEdit" @change="edit('box-shadow', $event.target.value)"><option value="" disabled>{{ $t('当前') }}</option><option v-for="[v, label] in SHADOWS" :key="v" :value="v">{{ $t(label) }}</option></select></div>
          <label class="visibility-control"><span>{{ $t('显示元素') }}</span><input type="checkbox" role="switch" :checked="selected.styles?.display !== 'none'" :disabled="!canEdit" @change="edit('display', $event.target.checked ? 'revert' : 'none')"><span class="switch-track"></span></label>
        </details>
      </template>
      <p v-if="!aiOnly" class="field-hint edit-hint">{{ $t('改动马上保存，可以用顶部撤销。要 AI 帮你改得更多，') }}<button class="link-btn" @click="setTool('comment')">{{ $t('切到评论') }}</button>{{ $t('。') }}</p>
    </template>

  </div>

</aside>
</template>
