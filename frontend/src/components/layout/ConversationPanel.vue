<script setup>
// 从 App.vue 拆出来的一块界面：状态和函数都在 App 里，按同样的名字 inject 进来，模板原样不动
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ArrowUp, Brain, Check, CheckCheck, ChevronDown, Copy, ImagePlus, LoaderCircle, MessageCircle, MessageSquare, PanelLeftClose, Pencil, Plus, SlidersHorizontal, Sparkles, Square, SquareMousePointer, X } from 'lucide-vue-next'
import ExecutionCard from '../chat/ExecutionCard.vue'
import ResultCard from '../chat/ResultCard.vue'
import AttachCard from '../chat/AttachCard.vue'
// 很长的一条（以前程序替你发的那种详细指令）：先只露几行，点「展开全部」再看
const openLong = ref(new Set())
const isLong = text => String(text || '').length > 160 || String(text || '').split('\n').length > 5
const preview = text => String(text || '').replace(/\s+/g, ' ').slice(0, 90).trim() + '…'
function toggleLong(id) { const next = new Set(openLong.value); next.has(id) ? next.delete(id) : next.add(id); openLong.value = next }
const {
  activeRun, annotations, applySuggestion, archOpen, busy, chatBox, chooseAnswer, chooseProject, closeSelection,
  composer, composerIntent, copyMessage, currentRuns, customSuggestion, repairRun, selftests, discussSuggestion, dragging, dropImage, editAndResend,
  elementLabel, forgetFromCard, formatTime, hideGuide, imageInput, input, lastResult, leftOpen,
  locked, memoryCount, messages, model, modelMenu, openDialog, openMemory, page,
  pasteImage, pendingRef, pendingUser, pendingDisplay, syncAttach, pointAt, project, projects, reference, rightOpen,
  runAgent, saveNote, selected, selectionPlace, setMode, showChat, showGuide, showPanel,
  smallerRequest, stopAgent, switchModel, switchingModel, toAI, tool, undo, useRephrase, drawSpec, reviseSpec, drawPlan, revisePlan
} = inject('studio')
// 对话方式：参照 Claude，收进输入框左下角一个小菜单，不再单独占一行
const modes = computed(() => [{ value: 'auto', label: '自动', tip: '提问先聊，指令再改' }, { value: 'discuss', label: '只讨论', tip: '只聊，不改代码' }, { value: 'edit', label: '直接改', tip: '直接动手局部修改' },
  ...(archOpen.value ? [{ value: 'architecture', label: '架构', tip: '只改画布上的页面树，不碰原型' }] : [])])
const modeMenu = ref(false)
const currentMode = computed(() => modes.value.find(m => m.value === composerIntent.value) || modes.value[0])
const closeMenus = () => { modeMenu.value = false }
onMounted(() => document.addEventListener('click', closeMenus))
onUnmounted(() => document.removeEventListener('click', closeMenus))
// 用户消息气泡里显示的字：卡片消息只显示补充的话；很长的先露一小段
function bubbleText(message) {
  if (message.display) return message.display.note || ''
  return isLong(message.content) && !openLong.value.has(message.id) ? preview(message.content) : message.content
}
const modelName = computed(() => model.value.has_key ? ((model.value.profiles || []).find(p => p.active)?.name || model.value.model) : '连接模型')
// 业务梳理卡、页面清单卡：后面已经按它画了架构 → drawn；后面又出了新版 → replaced；
// 梳理卡后面出了页面清单 → confirmed；不然还在等你确认
function laterArch(message) {
  return messages.value.slice(messages.value.indexOf(message) + 1).filter(m => m.role === 'assistant' && m.intent === 'architecture')
}
function specState(message) {
  if (!message.spec) return 'open'
  const later = laterArch(message)
  if (later.some(m => m.arch_mode === 'draw' && m.arch_changed)) return 'drawn'
  return later.some(m => m.spec) ? 'replaced' : later.some(m => m.plan) ? 'confirmed' : 'open'
}
// 清单卡确认时勾了哪些、问题选了什么：从后面那条「按页面清单画架构」读回来，刷新后卡片照当时的样子显示
function planConfirmed(message) {
  if (!message.plan) return null
  const sent = messages.value.slice(messages.value.indexOf(message) + 1).find(m => m.role === 'user' && /^按页面清单画架构/.test(m.content || ''))
  if (!sent) return null
  const line = sent.content.match(/可选页要：(.*)/)?.[1] || ''
  return { picked: line === '都不要' ? [] : line.split('、').filter(Boolean),
    answers: Object.fromEntries([...sent.content.matchAll(/^- (.+?)：(.+)$/gm)].map(m => [m[1], m[2]])) }
}
function planState(message) {
  if (!message.plan) return 'open'
  const later = laterArch(message)
  if (later.some(m => m.arch_mode === 'draw' && m.arch_changed)) return 'drawn'
  return later.some(m => m.plan || m.spec) ? 'replaced' : 'open'
}
// 讨论卡上的建议有没有已经照着改好：后面有一条「按已讨论的建议修改」带着它的做法，
// 而且紧跟着的回复真的改了页面（失败、停止的不算）
function appliedFor(message) {
  const list = message.discussion?.suggestions
  if (!list?.length) return []
  const all = messages.value, at = all.indexOf(message), done = []
  for (let j = at + 1; j < all.length; j++) {
    const m = all[j]
    if (m.role !== 'user' || !String(m.content || '').startsWith('按已讨论的建议修改')) continue
    const rest = all.slice(j + 1)
    const replyIndex = rest.findIndex(x => x.role === 'assistant'), nextUser = rest.findIndex(x => x.role === 'user')
    if (replyIndex === -1 || (nextUser !== -1 && nextUser < replyIndex) || !(rest[replyIndex].changed || rest[replyIndex].arch_changed)) continue
    for (const s of list) if (s.instruction && m.content.includes(s.instruction)) done.push(s.instruction)
  }
  return done
}
</script>

<template>
<aside class="conversation-panel" :class="{ collapsed: !leftOpen || rightOpen }" :aria-label="$t('对话')">
  <label class="mobile-project-picker"><span>{{ $t('当前项目') }}</span><select :aria-label="$t('切换当前项目')" :value="project?.id || ''" :disabled="locked || !projects.length" @change="chooseProject($event.target.value)"><option v-if="!projects.length" value="">{{ $t('尚未创建项目') }}</option><option v-for="p in projects" :key="p.id" :value="p.id">{{ $t(p.name) }}</option></select></label>
  <div class="panel-header"><div class="side-tabs" role="tablist" :aria-label="$t('左侧面板')"><button type="button" role="tab" :aria-selected="!rightOpen" :class="{ active: !rightOpen }" @click="showChat"><MessageSquare :size="14" />{{ $t('对话') }}</button><button type="button" role="tab" :aria-selected="rightOpen" :class="{ active: rightOpen }" @click="showPanel"><component :is="tool === 'comment' ? MessageCircle : SlidersHorizontal" :size="14" />{{ tool === 'comment' ? $t('评论') : $t('属性') }}<span v-if="tool === 'comment' && annotations.length" class="count">{{ $t(annotations.length) }}</span></button></div><button class="icon-button" :aria-label="$t('收起左侧面板')" @click="leftOpen = false"><PanelLeftClose :size="16" /></button></div>

    <!-- 参照 Claude：不写「你」「设计助手」；你的话是右边一个气泡，AI 的回复直接铺在背景上；复制、重发、时间悬停才出来 -->
    <div ref="chatBox" class="messages" aria-live="polite">
      <div v-if="!messages.length && !pendingUser && showGuide" class="conversation-empty compact-guide"><span class="empty-mark"><Sparkles :size="18" /></span><h2>{{ $t('先聊清楚，再动手。') }}</h2><p>{{ $t('可以一起评价设计、比较方案；确定方向后，只改需要调整的位置。') }}</p><div class="prompt-chips"><button v-for="suggestion in ['现在的设计怎么样？', '有哪些地方值得优化？', selected ? '调整选中区域的对齐' : '检查一下交互有没有漏的']" :key="suggestion" class="prompt-suggestion" :disabled="!page" @click="input = suggestion; toAI()">{{ $t(suggestion) }}</button></div><button class="text-button dismiss-guide" @click="hideGuide">{{ $t('不再显示') }}</button></div>
      <article v-for="message in messages" :key="message.id" class="message" :class="message.role">
        <template v-if="message.role === 'user'">
          <AttachCard v-if="message.display" :kind="message.display.kind" :title="message.display.title" :items="message.display.items" />
          <p v-if="bubbleText(message)" class="bubble">{{ bubbleText(message) }}</p>
          <button v-if="!message.display && isLong(message.content)" class="text-button more-text" @click="toggleLong(message.id)">{{ openLong.has(message.id) ? $t('收起') : $t('展开全部') }}</button>
        </template>
        <ResultCard v-else-if="message.report || message.clarification || message.discussion || message.changed || message.spec || message.plan" :result="message" :applied="appliedFor(message)" :spec-state="specState(message)" :plan-state="planState(message)" :plan-confirmed="planConfirmed(message)" :selftest="selftests[message.change_id]" :locked="locked" :can-undo="page?.last_undo_id === message.change_id" @undo="undo" @choose="chooseAnswer" @apply="applySuggestion" @discuss="discussSuggestion" @custom="customSuggestion" @rephrase="useRephrase" @forget="forgetFromCard" @draw-spec="drawSpec" @revise-spec="reviseSpec" @draw-plan="drawPlan" @revise-plan="revisePlan" />
        <p v-else class="reply">{{ message.content }}</p>
        <span v-if="message.role === 'user' && message.target" class="message-target"><SquareMousePointer :size="12" />{{ $t('指着：{0}', [$t(message.target)]) }}</span>
        <img v-if="message.role === 'user' && message.image" class="message-shot" loading="lazy" :src="`/api/projects/${project.id}/chat-images/${message.image}`" :alt="message.image_name || $t('参考截图缩略图')" @error="$event.target.style.display = 'none'">
        <div class="message-tools"><time>{{ formatTime(message.created_at) }}</time><button class="icon-button" :aria-label="$t('复制这条内容')" :title="$t('复制')" @click="copyMessage(message.report?.summary || message.discussion?.answer || message.content)"><Copy :size="13" /></button><button v-if="message.role === 'user'" class="icon-button" :aria-label="$t('编辑后重新发送')" :title="$t('编辑后重发')" :disabled="locked" @click="editAndResend(message)"><Pencil :size="13" /></button></div>
      </article>
      <article v-if="pendingUser && !messages.some(m => m.role === 'user' && m.content === pendingUser && m === messages[messages.length - 1])" class="message user"><template v-if="pendingDisplay"><AttachCard :kind="pendingDisplay.kind" :title="pendingDisplay.title" :items="pendingDisplay.items" /><p v-if="pendingDisplay.note" class="bubble">{{ pendingDisplay.note }}</p></template><p v-else class="bubble">{{ isLong(pendingUser) ? preview(pendingUser) : pendingUser }}</p><img v-if="pendingRef" class="message-shot" :src="pendingRef.data_url" :alt="$t(pendingRef.name)"></article>
      <ExecutionCard v-for="run in currentRuns" :key="run.id" :run="run" :locked="locked" @retry="runAgent(run.request, '', run.options)" @repair="repairRun(run)" @settings="openDialog('settings')" @select="setMode('select')" @fill="smallerRequest(run)" @point="pointAt(run)" @dismiss="run.status = 'dismissed'" @stop="stopAgent" />
    </div>

    <!-- 输入框：附件（同步卡片、截图、点选的位置）在框里最上面；左下角加图、对话方式，右下角模型、发送 -->
    <div class="composer-area">
      <button v-if="annotations.length" class="annotation-count batch-action" :disabled="locked" @click="runAgent($t('请逐条处理已记下的修改意见，保留其他区域。'), '', { intent: 'edit' })"><CheckCheck :size="14" />{{ $t('已记下 {0} 条，一起修改', [$t(annotations.length)]) }}<ArrowUp :size="14" /></button>
      <div class="composer" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave.self="dragging = false" @drop.prevent="dropImage">
        <div v-if="syncAttach || reference || selected" class="composer-attachments">
          <AttachCard v-if="syncAttach" class="in-composer" :title="syncAttach.title" :items="syncAttach.items" removable @remove="syncAttach = null" />
          <div v-if="reference" class="reference-attachment"><button class="reference-open" @click="openDialog('image')"><img :src="reference.data_url" :alt="$t('参考截图缩略图')"><span>{{ $t(reference.name) }}<small :class="{ warn: !model.supports_vision }">{{ !model.supports_vision ? $t('当前模型看不了图片') : reference.regions.length ? reference.regions.length + $t(' 个框选区域 · 点开修改') : $t('参考整张图 · 点开可圈选') }}</small></span></button><button class="icon-button" :aria-label="$t('移除参考截图')" :disabled="locked" @click="reference = null"><X :size="13" /></button></div>
          <div v-if="selected" class="selection-context"><SquareMousePointer :size="14" /><span>{{ elementLabel(selected) }}<small v-if="selectionPlace">{{ $t(selectionPlace) }}</small></span><button class="icon-button" :aria-label="$t('清除选中目标')" @click="closeSelection"><X :size="12" /></button></div>
        </div>
        <textarea ref="composer" v-model="input" rows="1" @paste="pasteImage" :aria-label="$t('对话内容')" :placeholder="busy ? $t('可以先写好下一条消息…') : syncAttach ? $t('可以补一句（不写也行，直接发送）') : composerIntent === 'architecture' ? $t('说说要加哪些菜单、页面、弹窗和字段') : selected ? $t('聊聊这个位置，或者告诉我怎么改…') : $t('说说想怎么改，或者问问这个设计…')"></textarea>
        <div class="composer-actions">
          <button class="icon-button" :title="model.supports_vision ? $t('加截图：也可以直接粘贴（⌘/Ctrl + V）或拖进输入框') : $t('加截图（当前模型看不了图片，发送前要在设置里换模型）')" :aria-label="$t('添加参考截图')" :disabled="locked" @click="imageInput.click()"><ImagePlus :size="17" /></button>
          <button type="button" class="mode-button" :class="composerIntent" :aria-expanded="modeMenu" :title="$t(currentMode.tip)" :disabled="busy" @click.stop="modeMenu = !modeMenu; modelMenu = false">{{ $t(currentMode.label) }}<ChevronDown :size="12" /></button>
          <span class="composer-spacer"></span>
          <button v-if="selected" class="quiet" :disabled="locked || !input.trim()" @click="saveNote">{{ $t('先记下') }}</button>
          <button class="model-pick" :aria-expanded="modelMenu" :title="lastResult?.usage?.total_tokens ? $t('切换模型 · 上次用了 {0} tokens', [lastResult.usage.total_tokens.toLocaleString()]) : $t('切换模型')" @click.stop="modeMenu = false; model.has_key ? (modelMenu = !modelMenu) : openDialog('settings')"><span class="status-dot" :class="{ connected: model.has_key }"></span><span class="model-name">{{ $t(modelName) }}</span><ChevronDown :size="12" /></button>
          <button v-if="activeRun" type="button" class="send-button stop-run" :disabled="!activeRun.runId || activeRun.stopping" :aria-label="$t('停止')" :title="$t('停在下一步之前；已经改好的部分会保留并检查，可以撤销')" @click="stopAgent"><Square :size="11" fill="currentColor" /></button>
          <button v-else class="send-button direct-modify" :disabled="locked || (!input.trim() && !annotations.length && !syncAttach) || !page" :aria-label="composerIntent === 'edit' ? $t('执行修改') : $t('发送消息')" :title="$t('发送 · ⌘ / Ctrl ↵')" @click="runAgent()"><LoaderCircle v-if="busy" :size="15" class="spin" /><ArrowUp v-else :size="16" /></button>
        </div>
      </div>
      <div v-if="modeMenu" class="composer-menu mode-menu" role="menu" @click.stop><button v-for="option in modes" :key="option.value" type="button" role="menuitemradio" :aria-checked="composerIntent === option.value" @click="composerIntent = option.value; modeMenu = false"><span><b>{{ $t(option.label) }}</b><small>{{ $t(option.tip) }}</small></span><Check v-if="composerIntent === option.value" :size="14" /></button></div>
      <div v-if="modelMenu" class="composer-menu model-menu" role="menu" @click.stop><p>{{ $t('切换模型') }}</p><button v-for="p in model.profiles || []" :key="p.id" type="button" role="menuitemradio" :aria-checked="p.active" :class="{ active: p.active }" :disabled="locked || switchingModel" @click="switchModel(p)"><Check v-if="p.active" :size="13" /><i v-else></i><span><b>{{ p.name || p.model }}</b><small>{{ p.name ? p.model + ' · ' : '' }}{{ $t(p.host) }}{{ p.has_key ? '' : $t(' · 缺密钥') }}</small></span><em v-if="p.supports_vision">{{ $t('看图') }}</em></button><button type="button" class="manage" @click="modelMenu = false; openDialog('settings')"><Plus :size="13" />{{ $t('绑定或管理模型…') }}</button><small v-if="locked" class="menu-note">{{ $t('AI 正在处理，等它做完再切换') }}</small></div>
      <div class="composer-foot"><button v-if="project" class="memory-status" :title="$t('AI 记住的约定和习惯：点开看、改、删')" @click="openMemory"><Brain :size="12" />{{ $t('记忆 {0}', [$t(memoryCount)]) }}</button><span v-if="lastResult?.usage?.total_tokens" :title="lastResult.usage.cached_tokens ? $t('输入里有 {0} tokens 命中了模型服务的缓存，这部分通常按一折计费', [lastResult.usage.cached_tokens.toLocaleString()]) : undefined">{{ lastResult.usage.total_tokens.toLocaleString() }} tokens<template v-if="lastResult.usage.cached_tokens && lastResult.usage.prompt_tokens"> · {{ $t('缓存 {0}%', [Math.round(lastResult.usage.cached_tokens / lastResult.usage.prompt_tokens * 100)]) }}</template></span></div>
    </div>
</aside>
</template>
