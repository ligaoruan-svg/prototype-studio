// 把改动存进去：后台先给一个待确认的版本，前端在看不见的 iframe 里跑一遍，没有新报错才提交。
// 属性面板直接改、撤销、退回历史版本都走这里
import { adoptPresync, dropPresync, presync } from '../lib/expandStore.js'
import { PREVIEW_SANDBOX } from '../lib/previewMessage.js'
import { responseError } from '../lib/streamAgent.js'
import { dateLocale } from '../lib/i18n.js'

export function useCommit(s) {
  const { status, previewDoc, runtimeErrors, pendingHighlights, boardOpen, boardRoute, previewRoute, canvasWidth, previewHash,
    savedAt, validationDetails, post, locked, canEdit, playing, selected, dynEdit, saving, error, send, cardPatch, sourceInfo,
    endpoint, undoCount, toast, dialog, dialogBusy, dialogError } = s
  let patchSeq = 0
  async function checkAndCommit(candidate) {
    if (!candidate.changed || !candidate.pending_id) return {}
    status.value = '检查中'
    const response = await fetch(candidate.preview_url)
    if (!response.ok) throw responseError({ code: 'validation', message: '无法读取待确认的修改，请重试' })
    const previousDoc = previewDoc.value, baseline = [...runtimeErrors.value]
    const html = s.preparePreview(await response.text())
    pendingHighlights.value = candidate.targets || []
    previewDoc.value = html
    // 运行检查要一两秒：这段时间展开副本已经用候选版本去拍正在看的那页了
    { const html = previewDoc.value; presync(candidate.pending_id, boardOpen.value ? boardRoute.value : previewRoute.value, route => s.makeProbeDoc(route, html)) }
    try {
      const errors = await new Promise((resolve, reject) => {
        const frame = document.createElement('iframe')
        frame.title = '后台检查'; frame.setAttribute('sandbox', PREVIEW_SANDBOX); frame.setAttribute('aria-hidden', 'true'); frame.tabIndex = -1
        // 和展开的副本一样放在屏幕内、透明、点不到：放到屏幕外会被浏览器限速，慢一点的页面检查超时，好好的修改被拒
        Object.assign(frame.style, { position: 'fixed', left: '0', top: '0', width: (canvasWidth.value || 1200) + 'px', height: '800px', border: '0', opacity: '0', pointerEvents: 'none', zIndex: '-1' })
        const found = []; let finishTimer, ready = false
        const cleanup = () => { clearTimeout(timeout); clearTimeout(finishTimer); window.removeEventListener('message', listener); frame.remove() }
        const listener = event => {
          if (event.source !== frame.contentWindow || event.data?.source !== 'prototype-agent') return
          const message = event.data
          if (message.type === 'RUNTIME_ERROR' && !baseline.includes(message.message) && !found.includes(message.message)) found.push(message.message)
          if (message.type === 'READY') ready = true
          if (message.type === 'LOADED' && ready) finishTimer = setTimeout(() => { cleanup(); resolve(found) }, 700)
        }
        const timeout = setTimeout(() => { cleanup(); reject(responseError({ code: 'validation', message: '检查超时，已保留上一版，请重试' })) }, 15000)
        window.addEventListener('message', listener); frame.srcdoc = html; document.body.appendChild(frame)
      })
      const committed = await post('/api/candidates/' + candidate.pending_id + '/commit', { runtime_checked: true, errors })
      adoptPresync(candidate.pending_id, committed.hash)   // 必须在 previewHash 变之前：别让刚拍好的那页又排队同步一遍
      previewHash.value = committed.hash
      savedAt.value = new Date().toLocaleTimeString(dateLocale())
      validationDetails.value = candidate.validation?.syntax_checked ? '页面结构、脚本语法及页面启动检查通过；不代表所有交互均已验证' : '页面结构及页面启动检查通过；本机没有执行脚本语法检查'
      status.value = '已保存 · 刚刚'
      return committed
    } catch (e) {
      pendingHighlights.value = []; runtimeErrors.value = baseline
      // 候选版本把预览框带到了别处（浏览器错误页），只恢复同一份源码 iframe 不会重载：加个记号强制重载
      previewDoc.value = previousDoc ? s.forceReload(previousDoc) : previousDoc
      dropPresync(candidate.pending_id)
      if (e && typeof e === 'object') e.pending = candidate.pending_id   // 这一版后台还留着：修报错时在它上面接着改
      throw e
    }
  }
  async function edit(prop, value, more = null) {
    if (locked.value || (!prop.startsWith('--') && (!canEdit.value || playing.value))) return
    const selector = selected.value?.selector || ''
    const dyn = dynEdit.value && !prop.startsWith('--')
    saving.value = true; error.value = ''; status.value = '修改中'
    // 同类元素一起改：预览里先把同类的都改上
    const extra = prop === 'text' || prop.startsWith('--') ? {} : Object.fromEntries(Object.entries(more || {}).map(([k, v]) => [k, String(v)]))
    for (const [p, v] of [[prop, String(value)], ...Object.entries(extra)])
      send(dyn && p !== 'text' ? { type: 'PA_PREVIEW', selector: selected.value.styleSel, all: true, prop: p, value: v } : { type: 'PA_PREVIEW', selector, prop: p, value: v })
    const card = selected.value?.card
    let committed = false
    if (card || prop.startsWith('--')) cardPatch.value = { seq: ++patchSeq, prop, value: String(value), route: prop.startsWith('--') ? null : card.route, nodeId: prop.startsWith('--') ? null : card.nodeId, rels: card?.rels || [] }
    try {
      const result = await post(endpoint('/edit'), { selector, prop, value: String(value), expected_hash: sourceInfo.value.hash, more: extra,
        ...(dyn ? (prop === 'text' ? { literal: selected.value.text } : { style_selector: selected.value.styleSel }) : {}) })
      if (dyn && prop === 'text' && result.changed) selected.value = { ...selected.value, text: String(value) }
      await checkAndCommit(result); committed = !!result.changed
      if (committed && selected.value?.selector === selector && !prop.startsWith('--')) selected.value = { ...selected.value, styles: { ...(selected.value.styles || {}), [prop]: String(value), ...extra } }
      if (!result.changed) status.value = '没有新的改动'
      await s.refresh(false)
    } catch (e) {
      if (committed) status.value = '已保存 · 预览刷新失败'
      else {
        error.value = e.message; status.value = '修改未保存 · 已保留原页面'
        // 展开卡片上先改了样子，保存没成：卡片退回原样，别让它显示一个没存进去的值
        if (cardPatch.value) cardPatch.value = { ...cardPatch.value, seq: ++patchSeq, revert: true }
      }
      await s.refresh().catch(() => {})
    }
    finally {
      saving.value = false
      reselect()
    }
  }
  // 改完以后在预览里重新选中同一个元素，好让属性面板读到新值。
  // 多选、拉框、在展开卡片里选的不能这样做：预览只会退回成一个元素，甚至因为找不到而把选择清掉
  function reselect() { const sel = selected.value; if (sel && sel.kind !== 'region' && !sel.card && !(sel.targets?.length > 1)) send({ type: 'PA_SELECT', selector: sel.selector }) }
  async function undo(changeId = '') {
    if (locked.value || !undoCount.value) return
    saving.value = true; error.value = ''
    try {
      await checkAndCommit(await post(endpoint('/undo'), { change_id: typeof changeId === 'string' ? changeId : '' }))
      await s.refresh(false); toast('已撤销上一步')
    } catch (e) { error.value = e.message; status.value = '撤销失败 · 页面没变' }
    finally { saving.value = false; reselect() }
  }
  async function restore(version) {
    if (locked.value) { dialogError.value = 'AI 正在修改，等它完成再退回'; return }
    dialogBusy.value = true; error.value = ''; dialogError.value = ''
    try { const result = await post(endpoint(`/restore/${version}`)); await checkAndCommit(result); s.closeSelection(); await s.refresh(false); dialog.value.close(); toast(`已退回到 v${version}`) } catch (e) { dialogError.value = e.message; status.value = '退回失败 · 页面没变' } finally { dialogBusy.value = false }
  }
  return { checkAndCommit, edit, undo, restore }
}
