// 交给 AI：发需求、收流式进度、改好后检查保存、做完自检、出错自动修一轮；以及讨论卡片、结果卡片上的各种「接着做」
import { computed, nextTick, ref } from 'vue'
import { consumeAgentStream } from '../lib/streamAgent.js'
import { selfTest, selfTestRequest } from '../lib/probe.js'
import { locale } from '../lib/i18n.js'

export function useAgentRun(s) {
  const { input, annotations, locked, pageId, model, reference, dialogError, selected, composerIntent, runs, project, busy, error,
    pendingUser, pendingRef, lastResult, status, leftOpen, previewRoute, recentClicks, runtimeErrors, canvasWidth, previewDoc,
    projects, chatBox, composer, commentDraft, api, post, toast } = s
  // 每次修改的自检结果（按 change_id 挂到对应的结果卡片上；只在这次打开期间有）
  const selftests = ref({})
  // 预览现场：停在哪一页、最近 5 分钟里点过什么、页面报过什么错
  function previewScene() {
    const since = Date.now() - 5 * 60_000
    return { route: previewRoute.value || '', clicks: recentClicks.value.filter(c => c.at >= since).map(({ at, ...c }) => c), errors: runtimeErrors.value.slice(-5) }
  }
  async function runAgent(text = '', runtimeFeedback = '', options = {}) {
    const message = (typeof text === 'string' && text ? text : input.value).trim() || (annotations.value.length ? '请逐条处理已记下的修改意见，保留其他区域。' : '')
    if (locked.value || !message || !pageId.value) return
    if (!model.value.has_key || (reference.value && !model.value.supports_vision)) { s.openDialog('settings'); dialogError.value = reference.value ? '这张截图需要支持图片输入和工具调用的模型。' : '请先配置模型密钥。'; return }
    const activeSelection = options.selection === undefined ? selected.value : options.selection
    const target = activeSelection ? { selector: activeSelection.selector, text: activeSelection.text, tag: activeSelection.tag, outer_html: activeSelection.outer_html, targets: activeSelection.targets || [], ...s.modalContext(activeSelection) } : null
    const intent = options.intent || composerIntent.value
    const run = { intent, options: { ...options, intent }, id: Date.now(), projectId: project.value.id, pageId: pageId.value, request: message, started: Date.now(), status: 'running', label: '理解需求中', steps: [], error: null, streamText: '', plan: [] }
    runs.value.push(run)
    const current = runs.value[runs.value.length - 1]
    busy.value = true; error.value = ''; pendingUser.value = message
    // 截图跟着这一条发出去就算用过了：从输入框上方拿掉，挂到这条消息上；停止或失败再放回来
    const sentRef = reference.value
    // 自检发现问题：这次结束后自动再修一轮；修完再查，如果修出了新的报错，再修第二轮，之后不再自动修
    let followUp = '', followRound = 0, followFeedback = '', followOptions = null
    const selfRound = options.selfReview || 0
    pendingRef.value = sentRef
    if (!text || input.value.trim() === message) input.value = ''
    reference.value = null
    lastResult.value = null; status.value = intent === 'edit' ? '正在读页面' : '思考中'; leftOpen.value = true
    try {
      const response = await fetch('/api/projects/' + project.value.id + '/agent/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ page_id: pageId.value, message, selection: target, runtime_feedback: runtimeFeedback, reference: sentRef, scene: previewScene(), intent, include_annotations: options.includeAnnotations !== false, repair_pending: options.repairPending || '', lang: locale.value }) })
      const result = await consumeAgentStream(response, event => {
        if (event.type === 'started' && event.run_id) current.runId = event.run_id
        // 模型服务忙：后台自动等几秒重试，这里只记一笔，让人知道不是卡住了
        if (event.type === 'model_retry') current.steps.push({ id: `retry-${event.round}-${event.attempt}`, label: event.label, state: 'done' })
        if (event.type === 'intent') { current.intent = event.intent; current.options.intent = event.intent; status.value = event.intent === 'discuss' ? '讨论中 · 不会修改文件' : '正在读页面' }
        if (event.type === 'plan') { current.plan = event.steps; if (event.brief) current.brief = event.brief }
        if (event.type === 'model_wait') { current.streamText = ''; current.round = event.round }
        if (event.type === 'text_delta') current.streamText += event.text
        if (event.type === 'note_delta') {
          // 模型的旁白按轮次接在步骤列表里，和它接下来做的事排在一起。
          // 以前所有文字共用一个 streamText，每换一轮就被擦掉，
          // 于是你只看得到工具名，看不到它为什么要查这个。
          const tail = current.steps[current.steps.length - 1]
          if (tail?.kind === 'note' && tail.round === current.round) tail.label += event.text
          else current.steps.push({ id: 'note-' + current.steps.length, kind: 'note', round: current.round, label: event.text })
        }
        if (event.label) current.label = event.label
        if (event.type.startsWith('step_')) {
          let step = current.steps.find(item => item.id === event.id)
          if (!step) { current.steps.push({ id: event.id, label: event.label }); step = current.steps[current.steps.length - 1] }
          step.state = event.type === 'step_start' ? 'running' : event.type === 'step_done' ? 'done' : 'error'
          step.error = event.error?.message || event.error?.error || ''
          if (event.detail) step.detail = event.detail
          // 记下真的动过文件的那一刻，卡片标题在那之前不该说"修改中"。
          if (event.tool === 'apply_operations' && event.type === 'step_done') { current.editing = true; status.value = '修改中' }
        }
      })
      current.result = result
      // 改好保存了：页面已经变了，之前点选 / 框选的那几个元素（还显示着改之前的文字）就不再挂着
      if (result.changed) { current.status = 'checking'; Object.assign(result, await s.checkAndCommit(result)); current.committed = true; s.closeSelection() }
      // 做完自检：改动不小（新做一页、一大块）时，像验收那样把每页按钮点一遍，有问题自动交回去修一轮
      if (result.changed && current.intent !== 'discuss' && (options.selfReview || (result.diff?.additions || 0) >= 30 || (result.change_count || 0) >= 6)) {
        status.value = '自检中 · 把每页的按钮点一遍'
        current.steps.push({ id: 'selftest', label: '做完自检：把每页的按钮点一遍', state: 'running' })
        const step = current.steps[current.steps.length - 1], html = previewDoc.value
        const report = await selfTest({ makeDoc: route => s.makeProbeDoc(route, html), width: canvasWidth.value || 1200 })
        const again = report.issues.length && (selfRound === 0 || (selfRound === 1 && report.issues.some(i => i.kind === '报错')))
        result.selftest = { ...report, round: selfRound + 1, final: !again }
        if (result.change_id) selftests.value = { ...selftests.value, [result.change_id]: result.selftest }
        step.state = 'done'
        step.label = report.skipped ? '自检没跑完：' + report.skipped
          : report.issues.length ? `自检发现 ${report.issues.length} 个问题${again ? '，接着自动修一轮' : ''}`
          : `自检通过：${report.routes} 个页面、${report.clicked} 个按钮都点过`
        if (again) { followUp = selfTestRequest(report.issues); followRound = selfRound + 1 }
        status.value = again ? '自检发现问题 · 马上自动修一轮' : report.issues.length ? `已保存 · 自检还剩 ${report.issues.length} 个问题` : '已保存 · 自检通过'
      }
      // 改好了、没跑自检：状态栏留着检查保存时写的「已保存 · 刚刚」。以前这里不看改没改，小改动保存了也显示「没有改动页面」
      else if (!result.changed) status.value = result.clarification ? '等待你确认' : result.discussion ? '讨论完成 · 未修改文件' : '没有改动页面'
      lastResult.value = result
      await s.refresh(false); projects.value = await api('/api/projects')
      current.status = 'complete'
      s.refreshMemoryCount(); setTimeout(s.refreshMemoryCount, 20_000)   // 后台整理记忆要一会儿，过一阵再看一次
    } catch (e) {
      if (e.code === 'stopped') {   // 自己点的停止、而且还没改动：不是失败，原需求放回输入框
        current.status = 'stopped'; current.error = { code: 'stopped', message: '已停止，当前文件没有改动' }
        current.steps.filter(st => st.state === 'running').forEach(st => { st.state = 'done' })
        if (!input.value.trim()) input.value = message
        if (!reference.value && sentRef) reference.value = sentRef
        status.value = '已停止 · 页面没有改动'; return
      }
      if (current.committed) {   // 已经存进去了，只是刷新预览没成功：不能报「未保存」，否则重试会再改一遍
        current.status = 'complete'; lastResult.value = current.result
        status.value = '已保存 · 预览刷新失败'; toast('修改已保存，但预览刷新失败，可以刷新页面')
        await s.refresh(false).catch(() => {}); return
      }
      current.status = 'failed'
      current.steps.filter(st => st.state === 'running').forEach(st => { st.state = 'error'; st.error = '本次处理已停止' })
      current.error = { code: e.code || 'network', message: e.message, detail: e.detail || e.message, pending: e.pending || '' }
      // 改完运行检查报错：自动带着报错、在那一版上修一次（不从头再做）；修完还报错才交给你
      if (e.code === 'validation' && e.pending && !options.repairPending) {
        followUp = '【自动修复】刚才那一版运行检查报错了，在它的基础上修掉报错，别的不要动，也不要从头再做。'
        followFeedback = e.detail || e.message
        followOptions = { intent: 'edit', includeAnnotations: false, selection: null, repairPending: e.pending }
        current.error.message = '改完运行检查报错，正在自动修复'
      }
      if (!input.value.trim()) input.value = message
      if (!reference.value && sentRef) reference.value = sentRef
      status.value = current.intent === 'discuss' ? '本次回复未完成 · 可以重试' : '本次修改未保存'
      await s.refresh(false).catch(() => {})
    } finally {
      current.finished = Date.now(); busy.value = false; pendingUser.value = ''; pendingRef.value = null
      await nextTick(); if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
      if (followUp) setTimeout(() => runAgent(followUp, followFeedback, followOptions || { intent: 'edit', includeAnnotations: false, selection: null, selfReview: followRound }), 0)
    }
  }
  // 停止：告诉后台在下一步之前停下。已经改好的部分照常检查、保存，可以一键撤销；还没改就什么都不动
  const activeRun = computed(() => [...runs.value].reverse().find(r => r.status === 'running') || null)
  async function stopAgent() {
    const run = activeRun.value
    if (!run?.runId || run.stopping || !project.value) return
    run.stopping = true; run.label = '正在停止…已经改好的部分会保留并检查'
    try { await post(`/api/projects/${project.value.id}/agent/stop`, { run_id: run.runId }) } catch { run.stopping = false }
  }
  // 「让 AI 修复」：后台还留着那一版就在它上面修，没有了（过期、页面被改过）才按原需求重做
  function repairRun(run) {
    if (run.error?.pending) return runAgent('【修复】刚才那一版运行检查报错了，在它的基础上修掉报错，别的不要动，也不要从头再做。', run.error.detail, { ...run.options, includeAnnotations: false, selection: null, repairPending: run.error.pending })
    return runAgent(run.request, run.error?.detail || '', run.options)
  }
  async function chooseAnswer({ option, clarification }) {
    await runAgent('原需求：' + clarification.request + '\n你的问题：' + clarification.question + '\n我的选择：' + option, '', { intent: clarification.intent || 'discuss' })
  }
  // 讨论卡片上勾了几条就一起改：一条照原样发，几条编号列出来，模型逐条做完再汇报
  async function applySuggestion({ suggestion, suggestions, discussion }) {
    const list = suggestions?.length ? suggestions : [suggestion]
    const message = list.length === 1 ? '按已讨论的建议修改：' + list[0].instruction
      : `按已讨论的建议修改，这 ${list.length} 条都要做：\n` + list.map((sg, i) => `${i + 1}. ${sg.label}：${sg.instruction}`).join('\n')
    await runAgent(message, '', { intent: 'edit', includeAnnotations: false, selection: discussion?.selection || null })
  }
  // 建议清单底下的「其他」：跟着这次讨论的选区，按输入框当前的模式发出去
  async function customSuggestion({ text, discussion }) {
    await runAgent(text, '', { includeAnnotations: false, selection: discussion?.selection || null })
  }
  async function discussSuggestion(suggestion) {
    composerIntent.value = 'discuss'; input.value = '关于“' + suggestion.label + '”：'; await s.toAI()
  }
  async function commentToAI() {
    const text = commentDraft.value.trim()
    if (!text || !selected.value) return
    input.value = text; commentDraft.value = ''
    await runAgent()
  }
  async function useRephrase(hint) { input.value = hint; await s.toAI() }
  async function copyMessage(text) {
    try { await navigator.clipboard.writeText(text); toast('已复制') } catch { toast('复制失败，请手动选中') }
  }
  async function editAndResend(message) {
    input.value = message.content
    await s.toAI()
    composer.value?.setSelectionRange(input.value.length, input.value.length)
  }
  // 「拆小一点」：以前是在原话前面加「先只修改一个位置：」就直接再发一遍，AI 拿到的信息和上次一模一样，照样找不到。
  // 现在把原话放回输入框，由你删成一小步再发
  async function smallerRequest(run) { input.value = run.request; leftOpen.value = true; await nextTick(); composer.value?.focus(); toast('要求放回输入框了，删成一小步再发，比如先只改一处') }
  // 「指给它看」：找不到通常是没指位置。点了没反应这类先切到交互把问题点一遍（AI 能看到你点了什么），别的切到点选点一下
  async function pointAt(run) {
    // 已经选中了：原话照发，选中的位置本来就会跟着需求一起交给 AI。以前在前面加「只修改当前选中的位置」，
    // 要整体重做的需求也被限死在一个元素上
    if (selected.value) { input.value = run.request; await s.toAI(); return }
    input.value = run.request; leftOpen.value = true
    const clicky = /没反应|点击|点了|点不|报错|跳转|打不开|切换|不动/.test(run.request)
    s.setMode(clicky ? 'interact' : 'select')
    toast(clicky ? '先在预览里把出问题的操作点一遍，再按发送：AI 能看到你点了什么、有没有报错' : '在页面上点一下要改的地方，再按发送')
  }
  return { selftests, runAgent, activeRun, stopAgent, repairRun, chooseAnswer, applySuggestion, customSuggestion, discussSuggestion,
    commentToAI, useRephrase, copyMessage, editAndResend, smallerRequest, pointAt }
}
