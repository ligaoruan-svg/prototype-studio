// 导出：展开图（一页一棵树的独立 HTML，双击就能看、也能打印成 PDF）、源码文件、整个项目 zip
import { ref, watch } from 'vue'
import { expand, expandAll, isFresh } from '../lib/expandStore.js'
import { buildExpandExport } from '../lib/expandExport.js'
import { saveFile, downloadUrl } from '../lib/desktop.js'
import { t } from '../lib/i18n.js'

export function useExport(s) {
  const { project, page, boardRoute, previewRoute, annotations, toast, endpoint } = s
  // 导出前先看完不完整：有页面没展开、或者改过以后还没同步，先问要不要展开完再导出（展开完会自动导出）
  const pendingExport = ref(false)
  function requestExport() {
    if (!project.value || !page.value) return
    const routes = expand.routes
    const missing = routes.filter(r => !expand.entries[r.hash]?.result?.styles).length
    const stale = routes.filter(r => expand.entries[r.hash]?.result?.styles && !isFresh(r.hash)).length
    if (!routes.length || missing || stale) {
      const what = !routes.length ? t('还没有找过这个原型有哪些业务页面，现在只能导出已经展开的页面。')
        : [missing && t('{0} 个业务页面还没展开', [missing]), stale && t('{0} 个页面不是最新版本', [stale])].filter(Boolean).join(t('，')) + t('。')
      if (window.confirm(t('{0}\n\n确定：先把所有业务页面展开到最新，完成后自动导出（展开期间可以照常使用）\n取消：直接导出现在已有的', [what]))) {
        pendingExport.value = true; expandAll(boardRoute.value || previewRoute.value)
        toast('正在展开全部业务页面，完成后会自动导出'); return
      }
    }
    exportExpand()
  }
  // 等到全部展开好再导出；有的页面展开失败（原型没响应）就永远等不到「全部好」——
  // 所以后台没事可做了也导出，用现有的，并说清哪些没展开成。不能卡着，过很久又突然下载
  watch(() => {
    if (!pendingExport.value || expand.discovering || !expand.routes.length) return ''
    if (expand.routes.every(r => isFresh(r.hash))) return 'ready'
    return !Object.keys(expand.jobs).length && !expand.queued.length && !expand.batch ? 'idle' : ''
  }, state => {
    if (!state) return
    pendingExport.value = false
    const failed = state === 'idle' ? expand.routes.filter(r => !isFresh(r.hash)).length : 0
    exportExpand()
    if (failed) toast(`有 ${failed} 个页面没展开成功，导出的是其余页面${expand.error ? '（' + expand.error + '）' : ''}`)
  })
  watch(() => expand.scope, () => { pendingExport.value = false })   // 切到别的项目 / 页面就不再自动导出
  function exportExpand() {
    if (!project.value || !page.value) return
    const name = project.value.name || '原型', file = page.value.path || page.value.title || ''
    const { html, pages, views, missing } = buildExpandExport({ projectName: name, fileName: file, version: page.value.version, routes: expand.routes, entries: expand.entries, currentHash: expand.hash, notes: annotations.value })
    if (!pages) { toast('还没有展开好的页面可以导出'); return }
    const fileName = `${name}-${t('展开图')}-v${page.value.version}.html`.replace(/[\\/:*?"<>|]/g, '_')
    saveFile(fileName, html).then(saved => {
      if (saved) toast(`已导出 ${pages} 个业务页面、${views} 个视图${missing ? `；还有 ${missing} 个页面没展开，先点「一键展开」可以导出完整的` : ''}`)
    }, () => toast('导出失败，请重试'))
  }
  function download(zip = false) { if (project.value) downloadUrl(zip ? `/api/projects/${project.value.id}/export` : endpoint('/download')).catch(() => toast('导出失败，请重试')) }
  return { requestExport, download }
}
