// 桌面版（原型工坊.app）里没有浏览器的下载栏：存文件走原生的「存储为」对话框。
// 在浏览器里打开时照旧用浏览器下载。window.pywebview.api 由桌面外壳 desktop/app.py 注入
const api = () => (typeof window !== 'undefined' && window.pywebview?.api) || null
export const isDesktop = () => Boolean(api())

// 把一段文字存成文件；返回 false 表示用户在对话框里点了取消
export async function saveFile(name, text, type = 'text/html;charset=utf-8') {
  const bridge = api()
  if (bridge?.save_text) return Boolean(await bridge.save_text(name, text))
  const url = URL.createObjectURL(new Blob([text], { type }))
  const a = document.createElement('a')
  a.href = url; a.download = name
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000)
  return true
}

// 下载服务端生成的文件（导出 HTML、整个项目 ZIP）
export async function downloadUrl(url) {
  const bridge = api()
  if (bridge?.download) return Boolean(await bridge.download(url))
  window.location.assign(url)
  return true
}
