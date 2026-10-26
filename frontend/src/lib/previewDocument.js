// Re-seed a remounted iframe with the latest scroll state, never a cached seed.
export function preparePreviewDocument(html, { stored = {}, route = '', scroll = null, probe = false } = {}) {
  const safe = value => JSON.stringify(value).replace(/</g, '\\u003c')
  const clean = html.replace(/<script data-pa-seed>[\s\S]*?<\/script>/g, '')
  const cleaned = probe ? clean.replace(/(<[a-z][^>]*?)\sautofocus(?=[\s>=\/])(="[^"]*"|='[^']*')?/gi, '$1') : clean
  // 后台展开的副本（probe）不许抢焦点：原型自己调 focus()、autofocus、showModal 都会把焦点从你正在打字的输入框拽走
  const noFocus = probe ? ';HTMLElement.prototype.focus=SVGElement.prototype.focus=function(){};window.focus=function(){};if(window.HTMLDialogElement){HTMLDialogElement.prototype.showModal=function(){this.setAttribute("open","")}}' : ''
  const script = '<script data-pa-seed>window.__paStorageSeed=' + safe(stored) + ';window.__paRoute=' + safe(route) + ';window.__paScrollSeed=' + safe(scroll) + (probe ? ';window.__paProbe=true' : '') + noFocus + ';</scr' + 'ipt>'
  // 没有 <head> 的页面也要放进去（以前直接跳过：路由、演示数据、展开标记全没了）
  if (/<head\b[^>]*>/i.test(cleaned)) return cleaned.replace(/<head\b[^>]*>/i, match => match + script)
  if (/<html\b[^>]*>/i.test(cleaned)) return cleaned.replace(/<html\b[^>]*>/i, match => match + script)
  return script + cleaned
}
