// 备用构建：编译 SFC 并输出浏览器原生 ES 模块，不需要 vite 的平台原生二进制。
// 正常请用 `npm run build`（vite）；只有在当前机器装不上原生依赖时才用 `npm run build:esm`。
// 用法：node scripts/build-esm.mjs <frontend 目录>
import { readFileSync, writeFileSync, mkdirSync, rmSync, readdirSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { parse, compileScript, compileStyle, rewriteDefault } from '@vue/compiler-sfc'

const root = process.argv[2]
const src = `${root}/src`, out = `${root}/dist`, nm = `${root}/node_modules`
// 连接的文件夹可能不允许删除，构建不该因此失败：删不掉就直接覆盖写。
try { rmSync(out, { recursive: true, force: true }) } catch { /* 覆盖写即可 */ }
mkdirSync(`${out}/assets`, { recursive: true })

const css = [readFileSync(`${src}/style.css`, 'utf8')]
const icons = new Set()
const rewrite = code => code
  .replace(/(\bfrom\s*)(['"])vue\2/g, "$1'./vue.js'")
  .replace(/(\bfrom\s*)(['"])lucide-vue-next\2/g, "$1'./lucide.js'")
  .replace(/(\bfrom\s*)(['"])(\.\/[\w./-]+)\.vue\2/g, "$1'$3.js'")
  .replace(/^\s*import\s+['"][^'"]+\.css['"];?\s*$/gm, '')

for (const file of readdirSync(src)) {
  const source = readFileSync(`${src}/${file}`, 'utf8')
  for (const m of source.matchAll(/from\s*['"]lucide-vue-next['"]/g)) void m
  if (/lucide-vue-next/.test(source))
    for (const block of source.matchAll(/import\s*\{([^}]*)\}\s*from\s*['"]lucide-vue-next['"]/g))
      for (const part of block[1].split(',')) icons.add(part.trim().split(/\s+as\s+/)[0].trim())
  if (file.endsWith('.js')) { writeFileSync(`${out}/assets/${file}`, rewrite(source)); continue }
  if (!file.endsWith('.vue')) continue
  const filename = `${src}/${file}`
  const id = createHash('sha256').update(file).digest('hex').slice(0, 8)
  const { descriptor } = parse(source, { filename })
  const scoped = descriptor.styles.some(s => s.scoped)
  const scopeId = `data-v-${id}`
  const script = compileScript(descriptor, { id, inlineTemplate: true,
    templateOptions: { compilerOptions: scoped ? { scopeId } : {} } })
  let code = rewrite(rewriteDefault(script.content, '_sfc_main'))
  if (scoped) code += `\n_sfc_main.__scopeId = ${JSON.stringify(scopeId)}\n`
  code += '\nexport default _sfc_main\n'
  writeFileSync(`${out}/assets/${file.replace(/\.vue$/, '.js')}`, code)
  for (const style of descriptor.styles)
    css.push(compileStyle({ source: style.content, filename, id: scopeId, scoped: style.scoped }).code)
}

// Only the icons the app actually imports, inlined into one module.
const esm = `${nm}/lucide-vue-next/dist/esm`
const strip = f => readFileSync(f, 'utf8').replace(/^\s*import[^\n]*\n/gm, '').replace(/^export \{[^}]*\};?\s*$/gm, '').replace(/\/\/# sourceMappingURL.*$/gm, '').replace(/\/\*\*[\s\S]*?\*\//g, '')
const files = {}
for (const [, names, path] of readFileSync(`${esm}/lucide-vue-next.js`, 'utf8').matchAll(/export \{([^}]*)\} from '([^']*)';/g))
  for (const part of names.split(',')) {
    const name = part.trim().split(/\s+as\s+/).pop().trim()
    if (icons.has(name)) (files[path] ||= []).push(name)
  }
const missing = [...icons].filter(n => !Object.values(files).flat().includes(n))
if (missing.length) throw new Error('未找到图标：' + missing.join(', '))
let lucide = `import { h } from './vue.js'\n`
for (const util of readdirSync(`${esm}/shared/src/utils`).filter(f => f.endsWith('.js')))
  lucide += strip(`${esm}/shared/src/utils/${util}`)
lucide += strip(`${esm}/defaultAttributes.js`) + strip(`${esm}/Icon.js`) + strip(`${esm}/createLucideIcon.js`)
for (const [path, names] of Object.entries(files)) {
  const body = strip(`${esm}/${path.replace('./', '')}`)
  const local = body.match(/^const (\w+) = createLucideIcon\(/m)[1]
  lucide += body + names.map(n => n === local ? '' : `const ${n} = ${local};\n`).join('')
  lucide += `export { ${names.map(n => n === local ? n : n).join(', ')} };\n`
}
writeFileSync(`${out}/assets/lucide.js`, lucide)
writeFileSync(`${out}/assets/vue.js`, readFileSync(`${nm}/vue/dist/vue.runtime.esm-browser.prod.js`, 'utf8'))
writeFileSync(`${out}/assets/app.css`, css.join('\n'))
writeFileSync(`${out}/index.html`, readFileSync(`${root}/index.html`, 'utf8')
  .replace('</head>', '<link rel="stylesheet" href="/assets/app.css"></head>')
  .replace('/src/main.js', '/assets/main.js'))
console.log('built', readdirSync(`${out}/assets`).join(' '))
