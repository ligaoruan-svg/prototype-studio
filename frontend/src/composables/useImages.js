// 截图：可以直接粘贴（⌘/Ctrl + V）、拖进输入框，也可以点按钮选文件。
// 附上后在输入框上方显示缩略图；要圈出具体位置再点缩略图。还没打开项目时才弹出对话框（要选新建还是改当前）
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { dateLocale } from '../lib/i18n.js'

export function useImages(s) {
  const { locked, toast, reference, project, model, leftOpen, composer, input, dialogError, dialogBusy, post } = s
  const dragging = ref(false)
  async function uploadImage(event) {
    const file = event.target.files?.[0]; if (!file) return
    event.target.value = ''
    await attachImage(file)
  }
  function imageFrom(list) { return [...(list || [])].map(x => (x.kind === 'file' ? x.getAsFile() : x)).find(f => f && /^image\/(png|jpe?g|webp|gif)$/.test(f.type)) }
  async function pasteImage(event) {
    const file = imageFrom(event.clipboardData?.items)
    if (!file) return
    event.preventDefault()
    await attachImage(file)
  }
  async function dropImage(event) {
    dragging.value = false
    const file = imageFrom(event.dataTransfer?.files)
    if (!file) { if (event.dataTransfer?.files?.length) toast('只能放 PNG、JPG、WebP 图片'); return }
    await attachImage(file)
  }
  // 焦点不在输入框时截完图直接 ⌘V 也能贴进来
  function globalPaste(event) {
    const el = event.target
    if (el instanceof Element && el.closest('input, textarea, [contenteditable=""], [contenteditable="true"], dialog[open]')) return
    if (imageFrom(event.clipboardData?.items)) pasteImage(event)
  }
  onMounted(() => window.addEventListener('paste', globalPaste))
  onUnmounted(() => window.removeEventListener('paste', globalPaste))
  async function attachImage(file) {
    if (locked.value) { toast('AI 正在修改，等它完成再加截图'); return }
    if (file.size > 8 * 1024 * 1024) { toast('请用 8 MB 以内的截图'); return }
    const pasted = !file.name || /^image\.(png|jpe?g|webp|gif)$/i.test(file.name)
    const name = pasted ? `粘贴的截图 ${new Date().toLocaleTimeString(dateLocale(), { hour: '2-digit', minute: '2-digit' })}` : file.name
    try {
      const dataUrl = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('截图读取失败')); reader.readAsDataURL(file) })
      const img = await new Promise((resolve, reject) => { const image = new window.Image(); image.onload = () => resolve(image); image.onerror = () => reject(new Error('无法识别这张图片')); image.src = dataUrl })
      const scale = Math.min(1, 1800 / Math.max(img.width, img.height)), canvas = document.createElement('canvas')
      canvas.width = Math.round(img.width * scale); canvas.height = Math.round(img.height * scale)
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height)
      reference.value = { name, data_url: canvas.toDataURL('image/png'), width: canvas.width, height: canvas.height, regions: [] }
      if (!project.value) { await s.openDialog('image'); return }
      leftOpen.value = true
      toast(model.value.supports_vision ? '截图已附上，发送时一起带上；点缩略图可以圈出要改的地方' : '截图已附上，但当前模型看不了图片，发送前要在设置里换成支持图片的模型')
      nextTick(() => composer.value?.focus())
    } catch (e) { toast(e.message) }
  }
  async function useReference(createNew = false) {
    if (locked.value) { dialogError.value = 'AI 正在修改，等它完成再用截图'; return }
    if (createNew || !project.value) {
      dialogBusy.value = true
      const carried = reference.value
      try { const result = await post('/api/projects/new', { name: carried.name.replace(/\.[^.]+$/, '') }); reference.value = null; await s.loadProjects(result.id); reference.value = carried } catch (e) { dialogError.value = e.message; return } finally { dialogBusy.value = false }
    }
    if (!input.value.trim()) input.value = reference.value.regions.length ? '参考截图中框选区域的意见，修改对应位置，保留其他区域。' : '参考这张截图，调整当前原型的布局和样式。'
    s.closeDialog(); await s.toAI(); toast('截图和框选意见已加入本轮需求')
  }
  return { dragging, uploadImage, pasteImage, dropImage, useReference }
}
