// 画笔：评论模式里在页面上拖动就是画。笔迹圈到的元素（源码位置）报上来；发送时再拍一张带红圈的截图
import { ref } from 'vue'

export function useDrawing(s) {
  const { send, selected, locked, model, reference, post, endpoint, annotations, error, toast } = s
  const drawing = ref(null), drawNote = ref(''), drawBusy = ref(false), drawInput = ref(null)
  let shotSeq = 0
  const shotWaiters = new Map()
  function requestShot() {
    return new Promise(resolve => {
      const id = ++shotSeq
      const timer = setTimeout(() => { shotWaiters.delete(id); resolve(null) }, 6000)
      shotWaiters.set(id, data => { clearTimeout(timer); resolve(data?.ok ? data : null) })
      send({ type: 'PA_DRAW_SHOT', id })
    })
  }
  // 预览把截图传回来了（DRAW_SHOT）：交给等着它的那一次
  function shotArrived(data) { if (shotWaiters.has(data.id)) { shotWaiters.get(data.id)(data); shotWaiters.delete(data.id) } }
  function drawClear() { send({ type: 'PA_DRAW_CLEAR' }); drawing.value = null; drawNote.value = ''; if (selected.value?.drawing) s.clearSelectionOnly() }
  async function drawSend() {
    const note = drawNote.value.trim()
    if (!note || !drawing.value || drawBusy.value || locked.value) { drawInput.value?.focus(); return }
    drawBusy.value = true
    try {
      // 模型能看图才带截图；看不了图就只给笔迹圈到的元素位置，照样能改
      if (model.value.supports_vision) {
        const shot = await requestShot()
        if (shot) reference.value = { data_url: shot.data_url, name: '页面上画的标记', regions: [] }
      }
      const selection = selected.value
      drawClear()
      await s.runAgent(note, '', { selection })
    } finally { drawBusy.value = false }
  }
  async function drawSave() {
    const note = drawNote.value.trim()
    if (!note || !drawing.value || !selected.value || drawBusy.value || locked.value) { drawInput.value?.focus(); return }
    drawBusy.value = true
    try {
      const shot = await requestShot()
      await post(endpoint('/annotations'), { ...selected.value, ...s.modalContext(selected.value), note, shot: shot?.thumb || '' })
      drawClear(); await s.refresh(false)
      toast(`已记下第 ${annotations.value.length} 条，可以接着画下一处`)
    } catch (e) { error.value = e.message } finally { drawBusy.value = false }
  }
  return { drawing, drawNote, drawBusy, drawInput, shotArrived, drawClear, drawSend, drawSave }
}
