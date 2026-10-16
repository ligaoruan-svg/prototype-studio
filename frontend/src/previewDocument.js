// Re-seed a remounted iframe with the latest scroll state, never a cached seed.
export function preparePreviewDocument(html, { stored = {}, route = '', scroll = null, probe = false } = {}) {
  const safe = value => JSON.stringify(value).replace(/</g, '\\u003c')
  const clean = html.replace(/<script data-pa-seed>[\s\S]*?<\/script>/g, '')
  const script = '<script data-pa-seed>window.__paStorageSeed=' + safe(stored) + ';window.__paRoute=' + safe(route) + ';window.__paScrollSeed=' + safe(scroll) + (probe ? ';window.__paProbe=true' : '') + ';</scr' + 'ipt>'
  // 没有 <head> 的页面也要放进去（以前直接跳过：路由、演示数据、展开标记全没了）
  if (/<head\b[^>]*>/i.test(clean)) return clean.replace(/<head\b[^>]*>/i, match => match + script)
  if (/<html\b[^>]*>/i.test(clean)) return clean.replace(/<html\b[^>]*>/i, match => match + script)
  return script + clean
}
