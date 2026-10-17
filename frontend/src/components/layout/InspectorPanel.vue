<script setup>
// 从 App.vue 拆出来的一块界面：状态和函数都在 App 里，按同样的名字 inject 进来，模板原样不动
import { inject } from 'vue'
import { AlertCircle, ArrowUp, CheckCheck, Hand, Layers, LoaderCircle, MessageCircle, MessageSquare, MousePointer2, PanelLeftClose, PenLine, Pencil, Plus, Scan, SlidersHorizontal, X } from 'lucide-vue-next'
const {
  aiOnly, annotations, canEdit, changeNumber, closeSelection, colors, commentDraft, commentToAI,
  drawClear, drawing, dynEdit, edit, elementLabel, inspection, leftOpen, locked,
  model, numericFields, playing, removeAnnotation, rightOpen, runAgent, saveNote, saving,
  selected, selectionPlace, setTool, shotUrl, showChat, showPanel, textEditable, textValue,
  tool
} = inject('studio')
</script>

<template>
<aside class="inspector" :class="{ collapsed: !rightOpen }" aria-label="属性面板">
  <div class="panel-header"><div class="side-tabs" role="tablist" aria-label="左侧面板"><button type="button" role="tab" :aria-selected="!rightOpen" :class="{ active: !rightOpen }" @click="showChat"><MessageSquare :size="14" />对话</button><button type="button" role="tab" :aria-selected="rightOpen" :class="{ active: rightOpen }" @click="showPanel"><component :is="tool === 'comment' ? MessageCircle : SlidersHorizontal" :size="14" />{{ tool === 'comment' ? '评论' : '属性' }}<span v-if="tool === 'comment' && annotations.length" class="count">{{ annotations.length }}</span></button></div><button class="icon-button" aria-label="收起左侧面板" @click="leftOpen = false; rightOpen = false"><PanelLeftClose :size="16" /></button></div>
  <p class="side-hint">{{ tool === 'comment' ? '写下怎么改，交给 AI 修改' : aiOnly ? '这里要交给 AI 修改' : '直接改，马上生效，不调用 AI' }}</p>
  <div class="inspector-scroll">
    <div v-if="!selected && (tool !== 'comment' || !annotations.length)" class="inspector-empty"><component :is="tool === 'comment' ? MessageCircle : tool === 'edit' ? Pencil : Hand" :size="28" :stroke-width="1.3" /><h2>{{ tool === 'comment' ? '评论：告诉 AI 怎么改' : tool === 'edit' ? '编辑：自己动手改' : '浏览中' }}</h2><p v-if="tool === 'comment'">点一下要改的元素，或者<b>按住拖动直接在页面上画</b>（画圈、划线），<br>写下怎么改，交给 AI 去改代码。</p><p v-else-if="tool === 'edit'">点一下元素，在这里<b>直接改</b>文字、颜色、字号、间距，<br>马上生效，不调用 AI、不花 token。</p><p v-else>像用户一样点页面。<br>要改东西，切到「评论」或「编辑」。</p><p v-if="tool !== 'comment' && annotations.length" class="field-hint">页面上有 {{ annotations.length }} 条评论，切到「评论」（C）查看</p></div>
    <div v-else-if="!selected" class="noted-panel">
      <div class="section-label">已记下的意见<span class="count">{{ annotations.length }}</span></div>
      <div v-for="(a, i) in annotations" :key="a.id" class="annotation-row"><span class="annotation-number">{{ i + 1 }}</span><div><img v-if="a.shot" class="ann-shot" :src="shotUrl(a)" alt="评论截图"><b v-else>{{ a.kind === 'region' ? `框选 ${a.targets?.length || 0} 个元素` : (a.text?.slice(0, 30) || a.tag) }}</b><p>{{ a.note }}</p></div><button class="icon-button" aria-label="移除这条意见" :disabled="locked" @click="removeAnnotation(a.id)"><X :size="14" /></button></div>
      <p class="field-hint">{{ tool === 'comment' ? '继续点或框下一处，或一起交给 AI 修改。' : '按 C 切到评论，继续标下一处。' }}</p>
      <button class="primary full-width" :disabled="locked" @click="runAgent('请逐条处理已记下的修改意见，保留其他区域。', '', { intent: 'edit' })"><CheckCheck :size="15" />这 {{ annotations.length }} 条一起修改</button>
    </div>
    <template v-else-if="tool === 'comment' && selected.drawing">
      <div class="selected-heading"><span class="element-icon"><PenLine :size="17" /></span><div><h2>画了 {{ drawing?.count || 0 }} 笔</h2><small>圈到 {{ selected.targets?.length || 0 }} 个元素 · 在画布下方写说明</small></div><button class="icon-button" aria-label="取消这次标记" @click="drawClear"><X :size="14" /></button></div>
      <p class="field-hint draw-hint">可以接着画，几笔算一条评论。{{ model.supports_vision ? '发送时会带上这块页面的截图（红圈也在上面）。' : '当前模型看不了图片，只把圈到的元素位置交给 AI。' }}</p>
      <div v-if="annotations.length" class="noted-panel"><div class="section-label">已记下的评论<span class="count">{{ annotations.length }}</span></div><div v-for="(a, i) in annotations" :key="a.id" class="annotation-row"><span class="annotation-number">{{ i + 1 }}</span><div><img v-if="a.shot" class="ann-shot" :src="shotUrl(a)" alt="评论截图"><b v-else>{{ a.kind === 'region' ? `框选 ${a.targets?.length || 0} 个元素` : (a.text?.slice(0, 30) || a.tag) }}</b><p>{{ a.note }}</p></div><button class="icon-button" aria-label="移除这条评论" :disabled="locked" @click="removeAnnotation(a.id)"><X :size="14" /></button></div></div>
    </template>
    <template v-else-if="tool === 'comment'">
      <div class="selected-heading"><span class="element-icon"><MessageCircle :size="17" /></span><div><h2>{{ selected.kind === 'region' ? `框选了 ${selected.targets?.length || 0} 个元素` : elementLabel(selected) }}</h2><small>{{ selectionPlace || '写下这里要怎么改' }}</small></div><button class="icon-button" aria-label="取消选择" @click="closeSelection"><X :size="14" /></button></div>
      <section class="property-section comment-box">
        <div v-if="selected.kind === 'region'" class="region-list"><span v-for="(target, index) in selected.targets" :key="index">{{ target.text?.slice(0, 28) || target.tag }}</span></div>
        <textarea v-model="commentDraft" class="text-property" rows="4" maxlength="1000" placeholder="比如：这一块改成卡片布局；按钮换成描边样式" aria-label="评论内容" @keydown.meta.enter.prevent="commentToAI" @keydown.ctrl.enter.prevent="commentToAI"></textarea>
        <div class="comment-actions"><button class="outline" :disabled="locked || saving || !commentDraft.trim()" title="先记下，攒几条一起改" @click="saveNote(commentDraft)"><Plus :size="14" />添加评论</button><button class="primary" :disabled="locked || !commentDraft.trim()" title="⌘/Ctrl ↵" @click="commentToAI"><ArrowUp :size="14" />直接交给 AI</button></div>
        <p class="field-hint">点下一个元素会换成那一个；按住 Shift 可以多选。记下的评论会钉在页面上。</p>
      </section>
      <div v-if="annotations.length" class="noted-panel"><div class="section-label">已记下的评论<span class="count">{{ annotations.length }}</span></div><div v-for="(a, i) in annotations" :key="a.id" class="annotation-row"><span class="annotation-number">{{ i + 1 }}</span><div><img v-if="a.shot" class="ann-shot" :src="shotUrl(a)" alt="评论截图"><b v-else>{{ a.kind === 'region' ? `框选 ${a.targets?.length || 0} 个元素` : (a.text?.slice(0, 30) || a.tag) }}</b><p>{{ a.note }}</p></div><button class="icon-button" aria-label="移除这条评论" :disabled="locked" @click="removeAnnotation(a.id)"><X :size="14" /></button></div><button class="primary full-width" :disabled="locked" @click="runAgent('请逐条处理已记下的修改意见，保留其他区域。', '', { intent: 'edit' })"><CheckCheck :size="15" />这 {{ annotations.length }} 条一起修改</button></div>
    </template>
    <template v-else>
      <div class="selected-heading"><span class="element-icon"><MousePointer2 :size="17" /></span><div><h2>{{ elementLabel(selected) }}</h2><small>{{ aiOnly ? '只读' : '直接修改 · 不调用 AI' }}</small></div><button class="icon-button" aria-label="取消选择" @click="closeSelection"><X :size="14" /></button></div>
      <p v-if="!inspection" class="inspector-loading"><LoaderCircle class="spin" :size="14" />定位中…</p><p v-else-if="inspection.failed" class="inspector-loading">没能在源码里定位这个元素，不能直接改属性；可以在下面写意见交给 AI</p>
      <div v-else-if="aiOnly && (selected.card || selected.modal)" class="dynamic-note"><AlertCircle :size="16" /><div><b>{{ selected.kind === 'region' ? `已选中 ${selected.targets?.length || 0} 个元素` : '这里不能直接改' }}</b><p>{{ selected.kind === 'region' ? '多个元素一起改，用评论告诉 AI 怎么改。' : selected.modal ? '这是弹窗里的内容，弹窗是脚本临时生成的，要由 AI 改对应的代码。' : '这是页面脚本生成的内容，要由 AI 改对应的代码。' }}</p><button class="outline" @click="setTool('comment')"><MessageCircle :size="14" />改成评论</button></div></div>
      <div v-else-if="!inspection.editable && !dynEdit" class="dynamic-note"><Scan v-if="selected.kind === 'region'" :size="16" /><AlertCircle v-else :size="16" /><div><b>{{ selected.kind === 'region' ? `已选中 ${selected.targets.length} 个元素` : '这是代码生成的内容' }}</b><p>{{ selected.kind === 'region' ? '多个元素一起改，用评论告诉 AI 怎么改。' : '它是页面脚本渲染出来的（列表、模板里的数据），不能直接改。用评论告诉 AI 怎么改，它会去改对应的代码。' }}</p><button class="outline" @click="setTool('comment')"><MessageCircle :size="14" />改成评论</button><div v-if="selected.targets" class="region-targets"><span v-for="(target, index) in selected.targets" :key="index">{{ target.text?.slice(0, 28) || target.tag }}</span></div></div></div>
      <template v-else>
        <div v-if="playing" class="dynamic-note play-note"><Hand :size="16" /><div><b>浏览中 · 属性只读</b><p>浏览时的操作不会保存。要改这个元素，先切到编辑。</p><button class="outline" @click="setTool('edit')">切到编辑</button></div></div>
        <div v-if="dynEdit" class="dyn-note"><Layers :size="14" /><p><b>脚本生成的元素</b>{{ selected.styleCount > 1 ? `改样式会作用到页面上同类的 ${selected.styleCount} 个元素（比如每张卡片里的同一位置），` : '改样式只作用到它自己，' }}文字能找到原样的那一处才能直接改。</p></div>
        <section class="property-section"><div class="section-label">内容<span>当前元素</span></div><label class="field-label" for="element-text">文字</label><textarea id="element-text" class="text-property" v-model="textValue" :disabled="!canEdit || !textEditable" @change="edit('text', textValue)"></textarea><p v-if="!textEditable" class="field-hint">{{ !dynEdit ? '包含子元素，请点选具体文字进行编辑。' : !selected.leaf ? '包含子元素，请点选具体文字。' : inspection.literal_count > 1 ? '这段字在源码里出现了好几处，没法确定改哪一处，用评论交给 AI。' : '这是脚本算出来的内容（数字、统计结果），用评论交给 AI。' }}</p></section>
        <section class="property-section"><div class="section-label">外观<span>{{ dynEdit && selected.styleCount > 1 ? `同类 ${selected.styleCount} 个一起改` : '当前元素' }}</span></div><label v-for="field in [{ key: 'color', label: '文字颜色' }, { key: 'background-color', label: '背景颜色' }]" :key="field.key" class="color-field"><span>{{ field.label }}</span><div><i :style="{ background: selected.styles?.[field.key] }"></i><select :aria-label="field.label" value="" :disabled="!canEdit" @change="edit(field.key, $event.target.value)"><option value="" disabled>当前颜色</option><option v-for="color in colors" :key="color.key" :value="`var(${color.key})`">{{ color.label }} · {{ color.value }}</option></select></div></label><div class="number-grid"><label v-for="field in numericFields" :key="field.key"><span>{{ field.label }}</span><div class="number-control"><input type="number" min="0" max="160" :step="field.step" :aria-label="field.label" :value="Number.isFinite(parseFloat(selected.styles?.[field.key])) ? parseFloat(selected.styles[field.key]) : ''" placeholder="未读取" :disabled="!canEdit" @change="changeNumber(field.key, $event)"><span>px</span></div></label></div><label class="visibility-control"><span>显示元素</span><input type="checkbox" role="switch" :checked="selected.styles?.display !== 'none'" :disabled="!canEdit" @change="edit('display', $event.target.checked ? 'revert' : 'none')"><span class="switch-track"></span></label></section>
      </template>
      <p v-if="!aiOnly" class="field-hint edit-hint">改动马上保存，可以用顶部撤销。要 AI 帮你改得更多，<button class="link-btn" @click="setTool('comment')">切到评论</button>。</p>
    </template>

  </div>

</aside>
</template>
