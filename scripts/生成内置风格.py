"""生成软件自带的几套风格：prompts/styles/<名字>/SKILL.md + assets/页面外壳.html

一套风格 = 共用骨架 + 皮肤 + 布局 + 写法说明：
- 骨架（SKELETON）：所有风格一样——组件（ZeroUI）、菜单配置 NAV、页面 Pages、交互 bindPage、路由。
  AI 的写法只有这一套，换风格不用重新学
- 皮肤（tokens）：一组 CSS 变量，换一组整页变样
- 布局（LAYOUTS）：菜单放哪、页面多宽——左侧菜单 / 大屏顶部切换 / 手机底部 Tab
- 写法说明：SKILL.md，这套风格自己的规矩

改风格改这个文件，再跑一遍：python3 scripts/生成内置风格.py（不要直接改生成出来的文件）
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "prompts" / "styles"

SKELETON = r"""<!doctype html>
<!-- 页面外壳：原型工坊内置风格「%%NAME%%」（样式、布局、菜单、路由、弹窗、抽屉、Toast 都在这里）。
     新页面从这里起步，只需要写 NAV 菜单、Pages 页面内容、bindPage 交互绑定三处（代码里标着 PA:NAV / PA:PAGES / PA:BIND）。 -->
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>示例系统</title>
<style>
:root{
%%TOKENS%%
  --font-sans:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;
  --font-mono:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--outer-bg);color:var(--text-1);font-family:var(--font-sans);font-size:var(--fs);line-height:1.55;-webkit-font-smoothing:antialiased}
button,input,select,textarea{font:inherit;color:inherit}
a{color:inherit;text-decoration:none}
svg{display:block}
.breadcrumb{font-size:12px;color:var(--text-3);margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.page-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:16px}
.page-head h1{margin:0;font-family:var(--font-display);font-size:var(--fs-title);line-height:1.35;font-weight:600;color:var(--text-1)}
.page-head p{margin:4px 0 0;font-size:13px;color:var(--text-3)}
.page-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--card-radius);box-shadow:var(--card-shadow);overflow:hidden}
.card+.card,.grid+.card,.card+.grid,.metric-grid+.card,.metric-grid+.grid,.grid+.grid{margin-top:var(--gap)}
.card-hd{min-height:46px;padding:0 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px}
.card-title{display:flex;align-items:center;gap:8px;font-family:var(--font-display);font-size:15px;font-weight:600;color:var(--text-1)}
.card-title::before{content:"";display:var(--title-bar);width:3px;height:14px;border-radius:2px;background:var(--primary)}
.card-desc{color:var(--text-3);font-size:12px}
.card-bd{padding:16px}
.grid{display:grid;gap:var(--gap)}
.grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}
.grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}
.grid.four{grid-template-columns:repeat(4,minmax(0,1fr))}
.grid>.card+.card{margin-top:0}
.section{margin-bottom:var(--gap)}
.btn{height:var(--ctl-h);border:1px solid var(--line-strong);border-radius:var(--btn-radius);background:var(--control-bg);color:var(--text-2);padding:0 14px;display:inline-flex;align-items:center;justify-content:center;gap:6px;cursor:pointer;white-space:nowrap;font-size:var(--fs-control);transition:border-color .12s,color .12s,background .12s}
.btn:hover{border-color:var(--primary);color:var(--primary)}
.btn.primary{background:var(--primary);border-color:var(--primary);color:var(--on-primary);font-weight:500}
.btn.primary:hover{background:var(--primary-hover);border-color:var(--primary-hover);color:var(--on-primary)}
.btn.danger{color:var(--danger)}
.btn.danger:hover{border-color:var(--danger);color:var(--danger-hover)}
.btn.danger-solid{background:var(--danger);border-color:var(--danger);color:#fff;font-weight:500}
.btn.danger-solid:hover{background:var(--danger-hover);border-color:var(--danger-hover);color:#fff}
.btn.block{display:flex;width:100%}
.btn.loading{pointer-events:none}
.btn-spinner{width:12px;height:12px;border:1.5px solid currentColor;border-right-color:transparent;border-radius:50%;animation:spin .7s linear infinite}
.btn[disabled]{color:var(--text-3);background:var(--head-bg);border-color:var(--line);cursor:not-allowed}
.btn-ico{width:15px;height:15px;flex:0 0 auto}
.icon-btn{width:var(--ctl-h);height:var(--ctl-h);border:1px solid var(--line-strong);border-radius:var(--control-radius);background:var(--control-bg);color:var(--text-2);display:grid;place-items:center;cursor:pointer;padding:0}
.icon-btn:hover{border-color:var(--primary);color:var(--primary)}
.icon-btn svg{width:16px;height:16px}
.btn:focus-visible,.icon-btn:focus-visible,input:focus,select:focus,textarea:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-ring)}
.lnk{padding:2px 6px;border:0;border-radius:4px;background:transparent;color:var(--primary);font-size:inherit;cursor:pointer;white-space:nowrap}
.lnk:hover{background:var(--primary-weak)}
.lnk.danger{color:var(--danger)}
.lnk.danger:hover{background:var(--danger-weak)}
.lnk[disabled]{color:var(--text-3);cursor:not-allowed;background:transparent}
.ops{display:flex;align-items:center;gap:4px;white-space:nowrap}
.field{min-width:0}
.field label{display:block;color:var(--text-2);font-size:13px;margin-bottom:6px}
.req{color:var(--danger);margin-left:2px}
.field input,.field select,.field textarea{width:100%;height:var(--ctl-h);border:1px solid var(--line-strong);border-radius:var(--control-radius);background:var(--control-bg);color:var(--text-1);padding:0 12px}
.field select{appearance:none;padding-right:28px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%2386909C' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m8 10 4 4 4-4'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 8px center;background-size:14px}
.field textarea{height:84px;padding:8px 12px;resize:vertical}
.field input::placeholder,.field textarea::placeholder{color:var(--text-3)}
.field .hint{font-size:12px;color:var(--text-3);margin-top:5px}
.field .error{font-size:12px;color:var(--danger);margin-top:5px}
.field.invalid input,.field.invalid select,.field.invalid textarea{border-color:var(--danger)}
.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px 14px}
.field.full{grid-column:1/-1}
.filter{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:12px;align-items:end}
.filter-actions{display:flex;align-items:center;gap:8px}
.tag{display:inline-block;line-height:18px;padding:1px 8px;border-radius:999px;font-size:12px;white-space:nowrap}
.tag.info{background:var(--primary-weak);color:var(--primary)}
.tag.success{background:var(--success-weak);color:var(--success)}
.tag.warning{background:var(--warning-weak);color:var(--warning)}
.tag.danger{background:var(--danger-weak);color:var(--danger)}
.tag.neutral{background:var(--head-bg);color:var(--text-2);border:1px solid var(--line)}
.switch{width:36px;height:20px;border-radius:999px;border:0;background:var(--line-strong);position:relative;cursor:pointer;padding:0;display:inline-block;vertical-align:middle}
.switch::after{content:"";position:absolute;width:16px;height:16px;border-radius:50%;background:#fff;left:2px;top:2px;box-shadow:0 1px 3px rgba(0,0,0,.2);transition:left .15s}
.switch.on{background:var(--primary)}
.switch.on::after{left:18px}
.badge{min-width:18px;height:18px;line-height:18px;padding:0 5px;border-radius:9px;background:var(--danger);color:#fff;font-size:11px;text-align:center;display:inline-block}
/* 表格放不下就在自己的容器里横向滚：别的叫法（table-wrap 等）也认 */
.tw,.table-wrap,.table-wrapper,.table-container,.table-scroll{width:100%;overflow-x:auto}.card-bd,.card:has(>table){overflow-x:auto}
table.data-table{width:100%;min-width:var(--table-min);border-collapse:collapse;table-layout:fixed;background:var(--card)}
.data-table th,.data-table td{padding:0 14px;border-bottom:1px solid var(--line);text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.data-table th{height:var(--th-h);color:var(--text-3);font-weight:500;font-size:13px;background:var(--head-bg)}
.data-table td{height:var(--td-h);color:var(--text-2)}
.data-table tbody tr:hover td{background:var(--row-hover)}
.data-table td.t1{color:var(--text-1);font-weight:500}
.data-table .op-col{overflow:visible}
.code{font-family:var(--font-mono);font-size:.92em}
.num{font-variant-numeric:tabular-nums}
.pagination{border-top:1px solid var(--line);padding:10px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;color:var(--text-3);font-size:13px}
.pager-left{white-space:nowrap}
.pager-right{display:flex;align-items:center;gap:6px}
.page-btn{min-width:32px;height:32px;border:1px solid var(--line-strong);border-radius:var(--control-radius);background:var(--control-bg);color:var(--text-2);padding:0 8px;cursor:pointer;display:inline-grid;place-items:center}
.page-btn:hover{border-color:var(--primary);color:var(--primary)}
.page-btn.on{background:var(--primary);border-color:var(--primary);color:var(--on-primary)}
.page-btn[disabled]{background:var(--head-bg);color:var(--text-3);border-color:var(--line);cursor:not-allowed}
.pager-gap{color:var(--text-3);padding:0 2px}
.empty{padding:40px 18px;text-align:center}
.empty-icon{width:40px;height:40px;margin:0 auto 10px;color:var(--line-strong)}
.empty h3{margin:0;font-size:15px;font-weight:600}
.empty p{margin:6px 0 14px;color:var(--text-3)}
.empty .btn{margin:0 auto}
.metric-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--gap)}
.metric{border:1px solid var(--line);border-radius:var(--card-radius);padding:14px 16px;background:var(--card);box-shadow:var(--card-shadow);min-width:0}
.metric-label{color:var(--text-3);font-size:13px}
.metric-value{font-size:var(--metric-fs);font-weight:600;line-height:1.25;margin:6px 0 2px;color:var(--metric-color);font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.metric-foot{font-size:12px;color:var(--text-3)}
.up{color:var(--success)}.down{color:var(--danger)}
/* 图表：纯 CSS，离线也能看，不引外部图表库 */
.bars{display:flex;align-items:flex-end;gap:12px;height:180px;padding-top:6px;border-bottom:1px solid var(--line)}
.bar{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:6px;height:100%;min-width:0}
.bar i{display:block;width:100%;max-width:44px;border-radius:4px 4px 0 0;background:var(--primary);opacity:.6}
.bar.on i{opacity:1}
.bar span{font-size:11px;color:var(--text-3);white-space:nowrap}
.bar-x{display:flex;gap:12px;margin-top:6px}
.bar-x span{flex:1;min-width:0;text-align:center;font-size:11px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.meter{display:grid;gap:14px}
.meter-row{display:grid;gap:6px}
.meter-hd{display:flex;justify-content:space-between;gap:8px;font-size:13px;color:var(--text-2)}
.meter-hd b{color:var(--primary);font-weight:600;font-variant-numeric:tabular-nums}
.meter-track{height:8px;border-radius:4px;background:var(--head-bg);overflow:hidden}
.meter-track i{display:block;height:100%;border-radius:4px;background:var(--primary)}
.list{background:var(--card);border:1px solid var(--line);border-radius:var(--card-radius);overflow:hidden}
.card .list{border:0;border-radius:0}
.list-item{display:flex;align-items:center;gap:12px;padding:10px 16px;border:0;border-bottom:1px solid var(--line);min-height:var(--td-h);width:100%;background:transparent;text-align:left;color:inherit}
.list-item:last-child{border-bottom:0}
a.list-item,button.list-item{cursor:pointer}
a.list-item:hover,button.list-item:hover{background:var(--row-hover)}
.li-main{flex:1;min-width:0}
.li-title{display:block;color:var(--text-1);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.li-desc{display:block;color:var(--text-3);font-size:12px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.li-extra{flex:none;color:var(--text-2);text-align:right}
.kv{display:grid;grid-template-columns:110px minmax(0,1fr);row-gap:10px;column-gap:12px;margin:0}
.kv dt{color:var(--text-3)}
.kv dd{margin:0;color:var(--text-2)}
.modal-mask{position:fixed;inset:0;z-index:100;background:var(--mask);display:flex;align-items:center;justify-content:center;padding:20px;animation:fadeIn .15s ease}
.modal{width:var(--modal-w);max-width:100%;max-height:calc(100vh - 40px);background:var(--card);color:var(--text-1);border:1px solid var(--line);border-radius:var(--modal-radius);box-shadow:var(--modal-shadow);overflow:hidden;animation:popIn .18s ease;display:flex;flex-direction:column}
.modal.wide{width:var(--modal-wide)}
.modal-hd{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px}
.modal-hd b{font-size:16px;font-weight:600}
.modal-hd .icon-btn,.drawer-hd .icon-btn{border:0;background:transparent}
.modal-bd{padding:20px;overflow:auto}
.modal-ft{padding:14px 20px;border-top:1px solid var(--line);display:flex;justify-content:flex-end;gap:10px}
.confirm-copy{display:grid;grid-template-columns:36px minmax(0,1fr);gap:12px;align-items:start}
.confirm-ico{width:36px;height:36px;border-radius:50%;background:var(--danger-weak);color:var(--danger);display:grid;place-items:center}
.confirm-ico svg{width:18px;height:18px}
.confirm-copy h3{margin:0 0 5px;font-size:15px;font-weight:600;color:var(--text-1)}
.confirm-copy p{margin:0;color:var(--text-2);line-height:1.7}
.drawer-mask{position:fixed;inset:0;z-index:110;background:var(--mask);animation:fadeIn .15s ease}
.drawer-panel{position:absolute;top:0;right:0;width:min(560px,92vw);height:100%;background:var(--card);color:var(--text-1);box-shadow:var(--modal-shadow);display:flex;flex-direction:column;animation:drawerIn .2s ease}
.drawer-hd{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px}
.drawer-hd b{font-size:16px;font-weight:600}
.drawer-bd{padding:20px;overflow:auto;flex:1}
.drawer-ft{padding:14px 20px;border-top:1px solid var(--line);display:flex;justify-content:flex-end;gap:10px}
.toast-host{position:fixed;left:50%;top:72px;transform:translateX(-50%);z-index:160;pointer-events:none}
.toast{background:var(--toast);color:#fff;padding:10px 18px;border-radius:8px;font-size:13px;white-space:nowrap;box-shadow:var(--modal-shadow);animation:fadeIn .15s ease}
.toast.error{background:var(--toast-error)}
@keyframes fadeIn{from{opacity:0}to{opacity:1}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes drawerIn{from{transform:translateX(24px);opacity:.5}to{transform:translateX(0);opacity:1}}
@keyframes popIn{from{opacity:0;transform:scale(.96)}to{opacity:1;transform:scale(1)}}
@media(max-width:1100px){.grid.four,.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.filter{grid-template-columns:repeat(2,minmax(140px,1fr))}}
@media(max-width:720px){.grid.two,.grid.three,.grid.four,.form-grid,.filter{grid-template-columns:1fr}.page-head{flex-direction:column}.page-actions{justify-content:flex-start}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}
/* ===== 布局：%%LAYOUT%% ===== */
%%LAYOUT_CSS%%
</style>
</head>
<body>
<div id="app"></div>
<div id="layerHost"></div>
<div id="toastHost" class="toast-host"></div>
<script>
const APP_NAME='示例系统';
const SVG={
  logo:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><path d="M13 16.5h7M16.5 13v7"/></svg>`,
  chevron:`<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>`,
  plus:`<svg class="btn-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>`,
  search:`<svg class="btn-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`,
  reset:`<svg class="btn-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>`,
  close:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m6 6 12 12M18 6 6 18"/></svg>`,
  prev:`<svg class="btn-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>`,
  next:`<svg class="btn-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>`,
  empty:`<svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16v12H4z"/><path d="M4 7l2-3h12l2 3"/><path d="M9.5 12h5"/></svg>`,
  alert:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2.8 19h18.4L12 3Z"/><path d="M12 9v4"/><path d="M12 16h.01"/></svg>`,
  home:`<svg class="tab-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/></svg>`,
  grid:`<svg class="tab-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>`,
  list:`<svg class="tab-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01"/></svg>`,
  bell:`<svg class="tab-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/></svg>`,
  user:`<svg class="tab-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c1.2-3.6 3.8-5.5 7-5.5s5.8 1.9 7 5.5"/></svg>`
};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const ZeroUI={
  Button:({label,kind='',icon='',id='',disabled=false,loading=false})=>`<button type="button" class="btn ${kind} ${loading?'loading':''}" ${id?`id="${esc(id)}"`:''} ${(disabled||loading)?'disabled':''}>${loading?'<span class="btn-spinner" aria-hidden="true"></span>':(icon||'')}${esc(label)}</button>`,
  IconButton:({icon,title,id=''})=>`<button type="button" class="icon-btn" title="${esc(title)}" aria-label="${esc(title)}" ${id?`id="${esc(id)}"`:''}>${icon}</button>`,
  Tag:({text,kind='info'})=>`<span class="tag ${kind}">${esc(text)}</span>`,
  Field:({label,type='text',placeholder='',value='',options=[],required=false,hint='',invalid='',full=false,id='',disabled=false,readonly=false})=>`<div class="field ${full?'full':''} ${invalid?'invalid':''}"><label ${id?`for="${esc(id)}"`:''}>${esc(label)}${required?'<span class="req">*</span>':''}</label>${type==='select'?`<select ${id?`id="${esc(id)}"`:''} ${disabled?'disabled':''}>${options.map(x=>`<option ${x===value?'selected':''}>${esc(x)}</option>`).join('')}</select>`:type==='textarea'?`<textarea ${id?`id="${esc(id)}"`:''} placeholder="${esc(placeholder)}" ${disabled?'disabled':''} ${readonly?'readonly':''}>${esc(value)}</textarea>`:`<input ${id?`id="${esc(id)}"`:''} type="${esc(type)}" value="${esc(value)}" placeholder="${esc(placeholder)}" ${disabled?'disabled':''} ${readonly?'readonly':''}>`}${invalid?`<div class="error">${esc(invalid)}</div>`:hint?`<div class="hint">${esc(hint)}</div>`:''}</div>`,
  Pager:({total=26,page=1,pageSize=10})=>{const pages=Math.max(1,Math.ceil(total/pageSize));return `<div class="pagination" data-pager data-page="${page}" data-pages="${pages}"><div class="pager-left">共 ${total} 条，每页 ${pageSize} 条</div><div class="pager-right"><button type="button" class="page-btn" aria-label="上一页" data-page-go="${page-1}" ${page<=1?'disabled':''}>${SVG.prev}</button>${Array.from({length:pages},(_,i)=>i+1).filter(n=>pages<=7||n===1||n===pages||Math.abs(n-page)<=1).map((n,i,a)=>`${i&&n-a[i-1]>1?'<span class="pager-gap">…</span>':''}<button type="button" class="page-btn ${n===page?'on':''}" ${n===page?'aria-current="page"':`data-page-go="${n}"`}>${n}</button>`).join('')}<button type="button" class="page-btn" aria-label="下一页" data-page-go="${page+1}" ${page>=pages?'disabled':''}>${SVG.next}</button></div></div>`},
  Empty:({title='暂无数据',text='当前还没有可展示的数据。',action='立即新增'})=>`<div class="empty">${SVG.empty}<h3>${esc(title)}</h3><p>${esc(text)}</p>${action?ZeroUI.Button({label:action,kind:'primary',icon:SVG.plus,id:'emptyAction'}):''}</div>`,
  ListItem:({title,desc='',extra='',id='',href=''})=>{const inner=`<span class="li-main"><span class="li-title">${esc(title)}</span>${desc?`<span class="li-desc">${esc(desc)}</span>`:''}</span>${extra?`<span class="li-extra">${extra}</span>`:''}`;return href?`<a class="list-item" href="${esc(href)}" ${id?`id="${esc(id)}"`:''}>${inner}</a>`:id?`<button type="button" class="list-item" id="${esc(id)}">${inner}</button>`:`<div class="list-item">${inner}</div>`},
  Bars:({items=[],unit='',current=-1})=>{const max=Math.max(1,...items.map(x=>+x.value||0));return `<div class="bars">${items.map((x,i)=>`<div class="bar ${i===current?'on':''}"><span>${esc(x.value)}${esc(unit)}</span><i style="height:${Math.max(2,Math.round((+x.value||0)/max*82))}%"></i></div>`).join('')}</div><div class="bar-x">${items.map(x=>`<span>${esc(x.label)}</span>`).join('')}</div>`},
  Meter:({items=[],max=100,unit='%'})=>`<div class="meter">${items.map(x=>`<div class="meter-row"><div class="meter-hd"><span>${esc(x.label)}</span><b>${esc(x.value)}${esc(unit)}</b></div><div class="meter-track"><i style="width:${Math.min(100,Math.max(0,Math.round((+x.value||0)/max*100)))}%"></i></div></div>`).join('')}</div>`,
  Toast:(message,type='')=>{const host=document.getElementById('toastHost');if(!host)return;clearTimeout(ZeroUI._toastTimer);host.innerHTML=`<div class="toast ${type==='error'?'error':''}" role="status">${esc(message)}</div>`;ZeroUI._toastTimer=setTimeout(()=>host.innerHTML='',2200)},
  Modal:({title='新增',wide=false,body='',confirm='确定',cancel='取消',footer='double',confirmKind='primary'})=>`<div class="modal-mask" id="activeModal"><section class="modal ${wide?'wide':''}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal-hd"><b>${esc(title)}</b>${ZeroUI.IconButton({icon:SVG.close,title:'关闭',id:'modalClose'})}</div><div class="modal-bd">${body}</div>${footer==='none'?'':`<div class="modal-ft">${footer==='double'?ZeroUI.Button({label:cancel,id:'modalCancel'}):''}${ZeroUI.Button({label:confirm,kind:confirmKind,id:'modalConfirm'})}</div>`}</section></div>`,
  ConfirmModal:({title='确认操作',message='此操作执行后将立即生效。',confirm='确定',danger=false})=>ZeroUI.Modal({title,body:`<div class="confirm-copy"><div class="confirm-ico">${SVG.alert}</div><div><h3>${esc(title)}</h3><p>${esc(message)}</p></div></div>`,confirm,cancel:'取消',footer:'double',confirmKind:danger?'danger-solid':'primary'}),
  Drawer:({title='详情',body='',confirm='保存',cancel='取消',footer='double'})=>`<div class="drawer-mask" id="activeDrawer"><section class="drawer-panel" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="drawer-hd"><b>${esc(title)}</b>${ZeroUI.IconButton({icon:SVG.close,title:'关闭',id:'drawerClose'})}</div><div class="drawer-bd">${body}</div>${footer==='none'?'':`<div class="drawer-ft">${footer==='double'?ZeroUI.Button({label:cancel,id:'drawerCancel'}):''}${ZeroUI.Button({label:confirm,kind:'primary',id:'drawerConfirm'})}</div>`}</section></div>`,
  _lockLayer(trigger){ZeroUI._lastTrigger=trigger||document.activeElement;ZeroUI._prevOverflow=document.body.style.overflow;document.body.style.overflow='hidden'},
  _unlockLayer(){document.body.style.overflow=ZeroUI._prevOverflow||'';const t=ZeroUI._lastTrigger;ZeroUI._lastTrigger=null;if(t&&typeof t.focus==='function')setTimeout(()=>t.focus(),0)},
  openModal:(html,onConfirm,trigger)=>{const host=document.getElementById('layerHost');ZeroUI._lockLayer(trigger);host.innerHTML=html;const mask=document.getElementById('activeModal');const close=()=>{host.innerHTML='';document.removeEventListener('keydown',escClose);ZeroUI._unlockLayer()};const escClose=e=>{if(e.key==='Escape')close()};const closeBtn=document.getElementById('modalClose');if(closeBtn)closeBtn.onclick=close;const cancelBtn=document.getElementById('modalCancel');if(cancelBtn)cancelBtn.onclick=close;mask.addEventListener('click',e=>{if(e.target===mask)close()});const confirmBtn=document.getElementById('modalConfirm');if(confirmBtn)confirmBtn.onclick=()=>{if(onConfirm)onConfirm(close,confirmBtn);else close()};document.addEventListener('keydown',escClose);setTimeout(()=>{const target=mask.querySelector('input:not([disabled]),select:not([disabled]),textarea:not([disabled]),button');if(target)target.focus()},0)},
  openDrawer:(html,onConfirm,trigger)=>{const host=document.getElementById('layerHost');ZeroUI._lockLayer(trigger);host.innerHTML=html;const mask=document.getElementById('activeDrawer');const close=()=>{host.innerHTML='';document.removeEventListener('keydown',escClose);ZeroUI._unlockLayer()};const escClose=e=>{if(e.key==='Escape')close()};document.getElementById('drawerClose').onclick=close;const cancelBtn=document.getElementById('drawerCancel');if(cancelBtn)cancelBtn.onclick=close;mask.addEventListener('click',e=>{if(e.target===mask)close()});const confirmBtn=document.getElementById('drawerConfirm');if(confirmBtn)confirmBtn.onclick=()=>{if(onConfirm)onConfirm(close,confirmBtn);else close()};document.addEventListener('keydown',escClose)}
};
const UI=ZeroUI;

// ===== 业务菜单：只在这里配置（单一来源）。一级分组 + 二级页面，key 就是 URL hash =====
const NAV=[/*PA:NAV*/
  {key:'biz',label:'业务模块',items:[{key:'home',label:'首页'}]}
];
// 菜单写成了扁平的页面列表、或者多包了一层 [] 也认：散的页面收进一个不显示名字的分组，不会因为 g.items 是 undefined 整页崩掉
const navGroups=()=>NAV.flat().reduce((out,g)=>{if(!g)return out;if(Array.isArray(g.items))out.push(g);else{const last=out[out.length-1];if(last&&last.loose)last.items.push(g);else out.push({key:'main',label:'',items:[g],loose:true})}return out},[]);
const navItems=()=>navGroups().flatMap(g=>g.items.map(i=>({...i,group:g.label})));
const Card=({title,desc='',body='',extra=''})=>`<section class="card"><div class="card-hd"><div><div class="card-title">${esc(title)}</div>${desc?`<div class="card-desc">${esc(desc)}</div>`:''}</div>${extra}</div><div class="card-bd">${body}</div></section>`;

// ===== 业务页面：每个二级菜单一项，返回这一页的 HTML（用 pageShell 包一层）=====
const Pages={/*PA:PAGES*/
  home(){return pageShell('首页','',`${Card({title:'内容',body:'在这里写这一页的内容'})}`)}
};
const Shell={title:''};
function pageShell(title,desc,body,actions=''){
  const meta=navItems().find(i=>i.key===Router.current());
  Shell.title=title;
  return `<div class="breadcrumb">${meta&&meta.group?esc(meta.group)+' / ':''}${esc(title)}</div><div class="page-head"><div><h1>${esc(title)}</h1>${desc?`<p>${esc(desc)}</p>`:''}</div><div class="page-actions">${actions}</div></div>${body}`;
}
const Router={
  current(){const key=location.hash.replace(/^#/,''),items=navItems();return items.some(x=>x.key===key)?key:(items[0]||{key:'home'}).key},
  render(){const page=this.current();const meta=navItems().find(i=>i.key===page)||{key:page,label:'首页',group:''};Shell.title=meta.label;renderNav(page);document.getElementById('content').innerHTML=(Pages[page]||(()=>pageShell(meta.label,'',ZeroUI.Empty({title:'建设中',text:'这一页还没有内容。',action:'返回首页'}))))();const t=document.getElementById('pageTitle');if(t)t.textContent=Shell.title;bindPage(page)}
};
// ===== 布局（这套风格的菜单和页面框架）=====
%%LAYOUT_JS%%

// ===== 交互只对当前页生效，两种写法任选 =====
// 1. 在下面的 bindPage(page) 里按 page 给元素设 onclick（每次换页、重画都会重新绑）
// 2. 事件委托：PageEvents.on('页面key','click','选择器',(el,e)=>{...})，只在那一页触发
// 不要在 document 上挂 click 监听：它对所有页面一直生效，翻页、按钮会串到别的页面。
// 每页的状态（页码、筛选条件）也各放各的：const planState={page:1,...}，不要几页共用一个变量
const PageEvents={_list:[],on(page,type,selector,fn){this._list.push({page,type,selector,fn})}};
['click','change','input','keydown'].forEach(type=>document.addEventListener(type,e=>{const page=Router.current();for(const h of PageEvents._list){if(h.type!==type||h.page!==page)continue;const el=e.target.closest&&e.target.closest(h.selector);if(el)h.fn(el,e)}}));
// ===== 每页的交互绑定：页面渲染完会调用一次，按 page 分开写 =====
function bindPage(page){/*PA:BIND*/
  const empty=document.getElementById('emptyAction');if(empty)empty.onclick=()=>{location.hash='#'+navItems()[0].key};
}
// 等整页的脚本都加载完再渲染：每页的函数常写在后面单独的 <script> 里，提前渲染会报「xxxPage is not defined」
function boot(){renderLayout();window.addEventListener('hashchange',()=>{Router.render();window.scrollTo(0,0)});if(!location.hash&&navItems().length)location.hash='#'+navItems()[0].key;Router.render();}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
</script>
</body>
</html>
"""

# ---------- 布局 ----------
LAYOUTS = {
    "sidebar": {
        "label": "左侧菜单",
        "css": r"""
.app{display:flex;min-height:100vh;background:var(--bg)}
.sidebar{width:216px;flex:0 0 216px;position:sticky;top:0;height:100vh;overflow-y:auto;background:var(--side-bg);color:var(--side-text);padding:16px 12px 24px;box-shadow:inset -1px 0 var(--side-line)}
.brand{display:flex;align-items:center;gap:10px;padding:4px 8px 16px;color:var(--side-brand);font-size:15px;font-weight:600;min-width:0}
.brand-mark{width:28px;height:28px;border-radius:8px;background:var(--primary);color:#fff;display:grid;place-items:center;flex:0 0 auto}
.brand-mark svg{width:16px;height:16px}
.brand-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nav-label{font-size:12px;color:var(--side-muted);padding:14px 10px 4px}
.nav-i{display:block;padding:8px 10px;margin:1px 0;border-radius:8px;color:var(--side-text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nav-i:hover{background:var(--side-hover);color:var(--side-hover-text)}
.nav-i.on{background:var(--side-on);color:var(--side-on-text);font-weight:500}
.main{flex:1;min-width:0}
.content{padding:22px 28px 32px;min-width:0}
@media(max-width:960px){.app{flex-direction:column}.sidebar{position:sticky;z-index:20;width:100%;height:auto;flex:0 0 auto;display:flex;align-items:center;gap:8px;overflow-x:auto;padding:8px 12px}.brand{padding:0 8px 0 0}.nav{display:flex;gap:2px}.nav-group{display:flex;gap:2px}.nav-label{display:none}.content{padding:16px}}
""",
        "js": r"""function renderLayout(){document.getElementById('app').innerHTML=`<div class="app"><aside class="sidebar"><div class="brand"><div class="brand-mark">${SVG.logo}</div><span class="brand-name">${esc(APP_NAME)}</span></div><nav class="nav" id="nav"></nav></aside><main class="main"><section class="content" id="content"></section></main></div>`}
function renderNav(page){document.getElementById('nav').innerHTML=navGroups().map(g=>`<div class="nav-group">${g.label?`<div class="nav-label">${esc(g.label)}</div>`:''}${g.items.map(i=>`<a href="#${i.key}" class="nav-i ${i.key===page?'on':''}">${esc(i.label)}</a>`).join('')}</div>`).join('')}""",
    },
    "topbar": {
        "label": "中台 · 顶部一级导航 + 左侧二级菜单",
        "css": r"""
.app{min-height:100vh;display:flex;flex-direction:column;background:var(--bg)}
.top{height:56px;flex:0 0 56px;position:sticky;top:0;z-index:30;display:flex;align-items:stretch;gap:24px;padding:0 20px;background:var(--side-bg);color:var(--side-text);box-shadow:inset 0 -1px var(--side-line)}
.brand{display:flex;align-items:center;gap:10px;color:var(--side-brand);font-size:15px;font-weight:600;white-space:nowrap}
.brand-mark{width:28px;height:28px;border-radius:8px;background:var(--primary);color:#fff;display:grid;place-items:center;flex:0 0 auto}
.brand-mark svg{width:16px;height:16px}
.topnav{display:flex;align-items:stretch;gap:2px;min-width:0;overflow-x:auto}
.top-i{display:flex;align-items:center;padding:0 14px;color:var(--side-text);white-space:nowrap;box-shadow:inset 0 -2px transparent}
.top-i:hover{color:var(--side-hover-text);background:var(--side-hover)}
.top-i.on{color:var(--side-on-text);font-weight:500;box-shadow:inset 0 -2px var(--primary);background:var(--side-on)}
.body{flex:1;display:flex;align-items:flex-start;min-width:0}
.subnav{width:200px;flex:0 0 200px;position:sticky;top:56px;height:calc(100vh - 56px);overflow-y:auto;background:var(--card);border-right:1px solid var(--line);padding:14px 10px}
.subnav-title{font-size:12px;color:var(--text-3);padding:2px 10px 8px}
.nav-i{display:block;padding:8px 12px;margin:1px 0;border-radius:var(--control-radius);color:var(--text-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nav-i:hover{background:var(--row-hover);color:var(--text-1)}
.nav-i.on{background:var(--primary-weak);color:var(--primary);font-weight:500}
.content{flex:1;min-width:0;padding:20px 24px 32px}
.breadcrumb{display:none}
@media(max-width:960px){.body{flex-direction:column;align-items:stretch}.subnav{position:static;width:100%;height:auto;display:flex;gap:4px;overflow-x:auto;border-right:0;border-bottom:1px solid var(--line);padding:6px 10px}.subnav-title{display:none}.content{padding:16px}}
""",
        "js": r"""function renderLayout(){document.getElementById('app').innerHTML=`<div class="app"><header class="top"><div class="brand"><div class="brand-mark">${SVG.logo}</div><span>${esc(APP_NAME)}</span></div><nav class="topnav" id="topnav"></nav></header><div class="body"><aside class="subnav" id="nav"></aside><main class="content" id="content"></main></div></div>`}
function renderNav(page){const groups=navGroups(),cur=groups.find(g=>g.items.some(i=>i.key===page))||groups[0];document.getElementById('topnav').innerHTML=groups.map(g=>`<a href="#${g.items[0].key}" class="top-i ${g===cur?'on':''}">${esc(g.label||g.items[0].label)}</a>`).join('');const nav=document.getElementById('nav');nav.style.display=cur&&cur.items.length>1?'':'none';nav.innerHTML=cur?`<div class="subnav-title">${esc(cur.label)}</div>`+cur.items.map(i=>`<a href="#${i.key}" class="nav-i ${i.key===page?'on':''}">${esc(i.label)}</a>`).join(''):''}""",
    },
    "screen": {
        "label": "大屏 · 顶部切换",
        "css": r"""
.app{min-height:100vh;display:flex;flex-direction:column;background:radial-gradient(ellipse 80% 50% at 50% 0,var(--bg-glow),transparent 70%),var(--bg)}
.screen-hd{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;padding:16px 28px 14px;border-bottom:1px solid var(--line)}
.screen-hd .clock{color:var(--text-3);font-size:13px;font-variant-numeric:tabular-nums;white-space:pre}
.app-title{margin:0;font-size:26px;line-height:1.3;font-weight:600;letter-spacing:4px;color:#fff;text-align:center;white-space:nowrap}
.hd-right{color:var(--text-3);font-size:13px;text-align:right}
.nav{display:flex;justify-content:center;flex-wrap:wrap;gap:8px;padding:12px 28px 0}
.nav:empty{display:none}
.nav-i{padding:5px 16px;border:1px solid var(--line-strong);border-radius:999px;color:var(--text-2);font-size:13px}
.nav-i:hover{border-color:var(--primary);color:var(--primary)}
.nav-i.on{border-color:var(--primary);color:var(--primary);background:var(--primary-weak)}
.content{flex:1;padding:16px 28px 28px;min-width:0}
.breadcrumb{display:none}
.page-head{margin-bottom:14px;align-items:center}
.card-title{color:#fff}
.metric{background:linear-gradient(180deg,var(--card),var(--bg))}
.list-item{min-height:40px}
""",
        "js": r"""function renderLayout(){document.getElementById('app').innerHTML=`<div class="app"><header class="screen-hd"><span class="clock" id="clock"></span><h1 class="app-title">${esc(APP_NAME)}</h1><span class="hd-right">数据实时更新</span></header><nav class="nav" id="nav"></nav><main class="content" id="content"></main></div>`;const tick=()=>{const el=document.getElementById('clock');if(!el)return;const d=new Date(),p=n=>String(n).padStart(2,'0');el.textContent=`${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}  星期${'日一二三四五六'[d.getDay()]}  ${p(d.getHours())}:${p(d.getMinutes())}`};tick();clearInterval(window.__clockTimer);window.__clockTimer=setInterval(tick,30000)}
function renderNav(page){const items=navItems();document.getElementById('nav').innerHTML=items.length>1?items.map(i=>`<a href="#${i.key}" class="nav-i ${i.key===page?'on':''}">${esc(i.label)}</a>`).join(''):''}""",
    },
    "mobile": {
        "label": "手机 · 底部 Tab",
        "css": r"""
.app{max-width:430px;min-height:100vh;margin:0 auto;background:var(--bg);display:flex;flex-direction:column;position:relative;box-shadow:0 0 0 1px var(--line)}
.m-top{position:sticky;top:0;z-index:40;background:var(--card);padding:14px 16px 12px;border-bottom:1px solid var(--line)}
.m-top h1{margin:0;font-family:var(--font-display);font-size:var(--fs-title);line-height:1.35;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.content{flex:1;padding:12px 14px 88px;min-width:0}
.tabbar{position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:100%;max-width:430px;height:62px;background:var(--card);border-top:1px solid var(--line);display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);z-index:45;padding-bottom:env(safe-area-inset-bottom)}
.tab{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-size:11px;color:var(--text-3);min-width:0}
.tab .tab-ico{width:22px;height:22px}
.tab span{max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tab.on{color:var(--primary);font-weight:600}
.breadcrumb,.page-head h1{display:none}
.page-head{margin-bottom:12px;flex-direction:column;gap:8px}
.page-head p{margin:0}
.page-head:not(:has(p)):not(:has(.page-actions>*)){display:none}
.page-actions{justify-content:flex-start;width:100%}
.page-actions:empty{display:none}
.card-hd{min-height:44px;padding:0 14px;border-bottom:0}
.card-bd{padding:4px 14px 14px}
.metric-grid,.grid.four{grid-template-columns:repeat(2,minmax(0,1fr))}
.grid.two,.grid.three,.form-grid,.filter{grid-template-columns:1fr}
.metric{padding:12px 14px}
.list-item{min-height:56px}
.modal{width:min(340px,100%)}
.modal-ft .btn{flex:1}
.drawer-panel{top:auto;bottom:0;left:50%;right:auto;transform:translateX(-50%);width:100%;max-width:430px;height:auto;max-height:86vh;border-radius:var(--modal-radius) var(--modal-radius) 0 0;animation:sheetIn .22s ease}
.drawer-ft .btn{flex:1}
@keyframes sheetIn{from{transform:translate(-50%,40px);opacity:.4}to{transform:translate(-50%,0);opacity:1}}
""",
        "js": r"""const TAB_ICONS=['home','grid','list','bell','user'];
function renderLayout(){document.getElementById('app').innerHTML=`<div class="app"><header class="m-top"><h1 id="pageTitle">${esc(APP_NAME)}</h1></header><main class="content" id="content"></main><nav class="tabbar" id="nav"></nav></div>`}
function renderNav(page){const items=navItems().slice(0,5);const nav=document.getElementById('nav');nav.style.display=items.length>1?'':'none';nav.innerHTML=items.map((i,n)=>`<a href="#${i.key}" class="tab ${i.key===page?'on':''}">${SVG[i.icon]||SVG[TAB_ICONS[n]]}<span>${esc(i.label)}</span></a>`).join('')}""",
    },
}

# ---------- 皮肤 ----------
BASE_TOKENS = {
    "outer-bg": "var(--bg)", "title-bar": "none", "metric-color": "var(--text-1)", "gap": "14px",
    "fs-control": "var(--fs)", "table-min": "960px", "modal-w": "480px", "modal-wide": "680px",
    "toast": "rgba(17,24,39,.92)", "toast-error": "rgba(201,48,44,.95)",
    "font-display": "var(--font-sans)",
    # 菜单（左侧菜单、中台顶栏）默认是深色底白字；浅色菜单的风格自己覆盖
    "side-bg": "#14213d", "side-text": "#c9d2e3", "side-muted": "#7f8ba3", "side-hover": "rgba(255,255,255,.06)", "side-on": "rgba(255,255,255,.1)",
    "side-hover-text": "#ffffff", "side-on-text": "#ffffff", "side-brand": "#ffffff", "side-line": "transparent",
}
CATEGORY = {"sidebar": "后台", "topbar": "中台", "screen": "中台", "mobile": "手机"}
# 选风格时的排列：按分类，分类里按这个顺序
ORDER = ["简洁后台", "企业蓝", "极简黑白", "业务中台", "数据中台", "数据大屏", "移动端App", "温暖柔和", "活力电商"]

STYLES = [
    {
        "name": "简洁后台", "layout": "sidebar", "primary": "#2f6fed", "background": "#f6f7f9",
        "description": "PC 管理后台：左侧深色菜单、白底卡片、筛选 + 表格 + 分页。适合订单、用户、商品、配置这类增删改查页面。",
        "tokens": {
            "bg": "#f6f7f9", "card": "#ffffff", "control-bg": "#ffffff", "line": "#e6e8eb", "line-strong": "#d9dee5",
            "text-1": "#1f2328", "text-2": "#45484f", "text-3": "#6b7280",
            "primary": "#2f6fed", "primary-hover": "#1f55c8", "primary-weak": "#eaf1ff", "primary-ring": "rgba(47,111,237,.16)", "on-primary": "#ffffff",
            "danger": "#d93a32", "danger-hover": "#b9302a", "danger-weak": "#fdecea",
            "success": "#1a7442", "success-weak": "#e7f6ee", "warning": "#9a5a00", "warning-weak": "#fff4e0",
            "head-bg": "#fafbfc", "row-hover": "#f7f9fc", "mask": "rgba(17,24,39,.45)",
            "side-bg": "#14213d", "side-text": "#c9d2e3", "side-muted": "#7f8ba3", "side-hover": "#1c2c4f", "side-on": "#24345a",
            "card-radius": "12px", "control-radius": "8px", "btn-radius": "8px", "modal-radius": "12px",
            "card-shadow": "0 1px 2px rgba(16,24,40,.04)", "modal-shadow": "0 16px 48px rgba(16,24,40,.18)",
            "fs": "14px", "fs-title": "20px", "ctl-h": "34px", "th-h": "40px", "td-h": "48px", "metric-fs": "24px",
        },
        "rules": """\
## 用途
做 PC 端管理后台：列表、详情、表单、配置，以及简单的数据概览。

## 这套风格的规矩
- 菜单：NAV 里一级分组 + 二级页面，左侧深色菜单会把分组名显示成小标题。分组不超过 6 个，每组不超过 8 页；不要在页面里再加一层主 Tabs 当导航。
- 一页从上到下：页面头（标题 + 一句说明 + 右上按钮）→ 指标卡（可选，一排最多 4 张）→ 筛选栏 + 表格卡片。
- 页面头右上最多 1 个主按钮（新建、导出这类），其余用默认按钮。
- 列表页：卡片里先放 `<div class="card-bd"><div class="filter">字段…<div class="filter-actions">查询 / 重置</div></div></div>`，再放表格和 ZeroUI.Pager。
- 表格包在 `<div class="tw">` 里，`table.data-table` 用 `<colgroup>` 定列宽；第一列重要信息用 `td.t1`，金额、数量加 `num`；操作列在最右，最多 3 个 `.lnk` 文字链接。
- 状态用 ZeroUI.Tag：info 进行中 / success 已完成 / warning 待处理 / danger 异常 / neutral 草稿、停用。
- 新建、编辑用 Modal（字段 ≤ 6 个，两列 `.form-grid`）；字段多或长详情用 Drawer；删除、停用必须 ConfirmModal({danger:true})。
""",
    },
    {
        "name": "数据大屏", "layout": "screen", "primary": "#3ad1ff", "background": "#070f1f",
        "description": "深色数据大屏：顶部标题和时间、大号指标、柱状图和占比条。适合投屏、监控、经营看板，一屏看全。",
        "tokens": {
            "bg": "#070f1f", "bg-glow": "rgba(32,96,190,.28)", "card": "#0e1d38", "control-bg": "#0b1830", "line": "#1b2c4d", "line-strong": "#2a3f66",
            "text-1": "#ffffff", "text-2": "#dce7f7", "text-3": "#8da2c4",
            "primary": "#3ad1ff", "primary-hover": "#8ae6ff", "primary-weak": "rgba(58,209,255,.12)", "primary-ring": "rgba(58,209,255,.25)", "on-primary": "#04121f",
            "danger": "#ff6b6b", "danger-hover": "#ff8f8f", "danger-weak": "rgba(255,107,107,.14)",
            "success": "#4ade80", "success-weak": "rgba(74,222,128,.14)", "warning": "#fbbf24", "warning-weak": "rgba(251,191,36,.14)",
            "head-bg": "#12244a", "row-hover": "#13284f", "mask": "rgba(2,6,16,.72)", "toast": "rgba(18,36,74,.96)",
            "title-bar": "block", "metric-color": "var(--primary)",
            "card-radius": "10px", "control-radius": "8px", "btn-radius": "8px", "modal-radius": "12px",
            "card-shadow": "0 8px 24px rgba(0,0,0,.25)", "modal-shadow": "0 20px 60px rgba(0,0,0,.5)",
            "fs": "14px", "fs-title": "16px", "ctl-h": "32px", "th-h": "38px", "td-h": "42px", "metric-fs": "34px", "table-min": "560px",
        },
        "rules": """\
## 用途
做投屏用的数据大屏、监控看板、经营驾驶舱：以「看」为主，一屏看全，不做复杂表单。

## 这套风格的规矩
- 按 1920×1080 设计，1440 宽也不能乱；内容尽量一屏放下、不出纵向滚动：一排 4~6 个指标，下面 2 行图表卡（`.grid.three` 或 `.grid.two`）。
- 一屏最多 8 张卡。卡片标题带主题色竖条（外壳已经做好），标题短，4~8 个字。
- 指标数字用 `.metric-value`（大号、主题色），涨跌写在 `.metric-foot` 里，用 `.up` / `.down`。
- 图表用 ZeroUI.Bars（柱状图）、ZeroUI.Meter（占比 / 进度条），或者纯 CSS / 内联 SVG 自己画；不要引外部图表库（离线也要能看）。
- 颜色：深色底，主题色只用在数字、图表和选中态上；不要出现大块白底、浅色卡片。
- 多个看板写成 NAV 里的多个页面，外壳会显示成标题下方的切换按钮；只有一页时不显示。
- 少按钮：交互只做切换时间范围、点卡片或条目看详情（Drawer）。页面头的标题用一句话说明这屏看什么。
- 明细用 `.list` + ZeroUI.ListItem 做「最新 N 条」滚动条目，不要带分页的大表格。
""",
    },
    {
        "name": "移动端App", "layout": "mobile", "primary": "#1f7a5c", "background": "#f2f4f7",
        "description": "手机 App / H5：430px 宽居中、顶部标题、底部 Tab 栏、圆角卡片和列表。适合用户端的下单、订单、个人中心这类页面。",
        "tokens": {
            "bg": "#f2f4f7", "outer-bg": "#e4e7ec", "card": "#ffffff", "control-bg": "#ffffff", "line": "#e5e8ec", "line-strong": "#d9dee5",
            "text-1": "#1f2328", "text-2": "#45484f", "text-3": "#6b7280",
            "primary": "#1f7a5c", "primary-hover": "#155c45", "primary-weak": "#e7f3ee", "primary-ring": "rgba(31,122,92,.18)", "on-primary": "#ffffff",
            "danger": "#d93a32", "danger-hover": "#b9302a", "danger-weak": "#fdecea",
            "success": "#1a7442", "success-weak": "#e7f6ee", "warning": "#9a5a00", "warning-weak": "#fff4e0",
            "head-bg": "#f5f6f8", "row-hover": "#f7f8fa", "mask": "rgba(17,24,39,.5)",
            "card-radius": "14px", "control-radius": "10px", "btn-radius": "999px", "modal-radius": "16px",
            "card-shadow": "none", "modal-shadow": "0 16px 48px rgba(16,24,40,.22)", "gap": "12px",
            "fs": "15px", "fs-title": "20px", "ctl-h": "40px", "th-h": "38px", "td-h": "44px", "metric-fs": "22px",
            "fs-control": "14px", "table-min": "520px",
        },
        "rules": """\
## 用途
做手机 App 或 H5 页面：首页、列表、详情、下单、个人中心。外壳把页面限制在 430px 宽、居中，顶部是页面标题，底部是 Tab 栏。

## 这套风格的规矩
- 底部 Tab = NAV 里按顺序排的前 5 个页面（分组名不显示）；页面可以加 `icon:'home'|'grid'|'list'|'bell'|'user'` 指定图标。超过 5 个的页面（详情、设置）用链接 `#页面key` 进入。
- NAV 和别的风格一样写成分组，页面放在 items 里，不要直接写页面数组：shell_add 的 nav 写 `{key:'app',label:'App',items:[{key:'home',label:'首页',icon:'home'},{key:'orders',label:'订单',icon:'list'},{key:'me',label:'我的',icon:'user'}]}`。
- 页面标题显示在顶部栏里（pageShell 的第一个参数），页面里不用再写大标题。
- 列表用 `.list` + ZeroUI.ListItem({title,desc,extra,id}) 或一张张卡片；不要横向很宽的表格。
- 点击区域至少 44px 高；一屏底部的主操作用 `ZeroUI.Button({label:'提交',kind:'primary block'})` 撑满宽度。
- 表单字段一列排；选项多、或要选择的内容用 Drawer（外壳里是从底部弹出的面板）。
- 确认、提示用 ConfirmModal / Toast，不要 alert。
- 指标卡一排 2 张；一屏不要塞太多卡片，留白比 PC 多。
""",
    },
    {
        "name": "企业蓝", "layout": "sidebar", "primary": "#1677ff", "background": "#f5f5f5",
        "description": "国内最常见的企业后台：白色侧边菜单、标准蓝、紧凑表格，接近 Ant Design 的观感。适合审批、CRM、ERP 这类信息量大的系统。",
        "tokens": {
            "bg": "#f5f5f5", "card": "#ffffff", "control-bg": "#ffffff", "line": "#f0f0f0", "line-strong": "#d9d9d9",
            "text-1": "#1f1f1f", "text-2": "#595959", "text-3": "#8c8c8c",
            "primary": "#1677ff", "primary-hover": "#0958d9", "primary-weak": "#e6f4ff", "primary-ring": "rgba(22,119,255,.15)", "on-primary": "#ffffff",
            "danger": "#ff4d4f", "danger-hover": "#d9363e", "danger-weak": "#fff1f0",
            "success": "#389e0d", "success-weak": "#f6ffed", "warning": "#d46b08", "warning-weak": "#fff7e6",
            "head-bg": "#fafafa", "row-hover": "#fafafa", "mask": "rgba(0,0,0,.45)", "toast": "rgba(0,0,0,.82)",
            "side-bg": "#ffffff", "side-text": "#595959", "side-muted": "#8c8c8c", "side-hover": "#f5f5f5", "side-on": "#e6f4ff",
            "side-hover-text": "#1f1f1f", "side-on-text": "#1677ff", "side-brand": "#1f1f1f", "side-line": "#f0f0f0",
            "card-radius": "8px", "control-radius": "6px", "btn-radius": "6px", "modal-radius": "8px",
            "card-shadow": "none", "modal-shadow": "0 6px 16px rgba(0,0,0,.08),0 9px 28px 8px rgba(0,0,0,.05)",
            "fs": "14px", "fs-title": "20px", "ctl-h": "32px", "th-h": "44px", "td-h": "50px", "metric-fs": "26px",
        },
        "rules": """\
## 用途
国内企业后台：审批流、CRM、ERP、工单、配置中心。信息量大，讲究规整、密度适中、一眼找到操作。

## 视觉基调
白色侧边菜单 + 浅灰底 + 白卡片，标准蓝只用在主按钮、链接、选中态。整体克制、规整，像成熟的企业软件。

## 配色怎么用
- 主色蓝 = 能点的东西（主按钮、链接、选中菜单），别拿来做大面积背景。
- 状态四色：success 绿通过、warning 橙待处理、danger 红驳回或异常、info 蓝进行中；neutral 灰是草稿、停用。

## 布局
- 菜单分组 ≤ 6 个、每组 ≤ 8 页；页面头 → 筛选卡片 → 表格卡片，和 Ant Design Pro 的列表页一个结构。
- 筛选项多于 4 个时，只露常用的 3 个，其余收进「展开」。
- 表格行高 50、表头 44；金额右对齐加 `num`；操作列固定在最右，最多 3 个文字链接。

## 要做 / 不要做
- 要：表单两列 `.form-grid`，标签在上；详情用 Drawer（560 宽）分组展示。
- 不要：彩色大卡片、渐变、插画；不要一页放两个主按钮。
""",
    },
    {
        "name": "极简黑白", "layout": "sidebar", "primary": "#171717", "background": "#fafafa",
        "description": "黑白灰极简：浅灰侧栏、细边框、黑色主按钮，参考 Linear、Vercel 这类工具的克制感。适合 SaaS 控制台、开发者工具、设置页。",
        "tokens": {
            "bg": "#fafafa", "card": "#ffffff", "control-bg": "#ffffff", "line": "#ebebeb", "line-strong": "#d4d4d4",
            "text-1": "#0a0a0a", "text-2": "#404040", "text-3": "#737373",
            "primary": "#171717", "primary-hover": "#404040", "primary-weak": "#f2f2f2", "primary-ring": "rgba(23,23,23,.12)", "on-primary": "#ffffff",
            "danger": "#dc2626", "danger-hover": "#b91c1c", "danger-weak": "#fef2f2",
            "success": "#15803d", "success-weak": "#f0fdf4", "warning": "#a16207", "warning-weak": "#fefce8",
            "head-bg": "#fafafa", "row-hover": "#f7f7f7", "mask": "rgba(0,0,0,.4)", "toast": "rgba(10,10,10,.92)",
            "side-bg": "#fafafa", "side-text": "#525252", "side-muted": "#a3a3a3", "side-hover": "#f0f0f0", "side-on": "#ebebeb",
            "side-hover-text": "#0a0a0a", "side-on-text": "#0a0a0a", "side-brand": "#0a0a0a", "side-line": "#ebebeb",
            "card-radius": "10px", "control-radius": "8px", "btn-radius": "8px", "modal-radius": "12px",
            "card-shadow": "0 1px 2px rgba(0,0,0,.03)", "modal-shadow": "0 24px 64px rgba(0,0,0,.16)",
            "fs": "14px", "fs-title": "22px", "ctl-h": "32px", "th-h": "38px", "td-h": "44px", "metric-fs": "28px",
        },
        "rules": """\
## 用途
SaaS 控制台、开发者工具、团队设置、账单页。用户是熟练用户，要的是安静、快、信息清楚。

## 视觉基调
几乎只有黑白灰，靠字重、间距和 1px 细线分层次，不靠颜色。留白大，标题偏大、正文偏小，对比鲜明。

## 配色怎么用
- 黑色是主色：主按钮、选中态、重点数字。彩色只出现在状态（绿成功、红错误、黄提醒），而且只用在小标签和小圆点上。
- 不要蓝色链接：链接用黑字 + 悬停底色（外壳的 .lnk 已经是这样）。

## 布局
- 页面头标题 22px，下面一句灰色说明；内容区宽，表格用细线分隔、不加斑马纹。
- 设置类页面用一列卡片：每张卡片左边标题和说明、右边控件（`.grid.two` 左窄右宽）。
- 数字、编号、时间用 `code` 类（等宽），对齐整齐。

## 要做 / 不要做
- 要：大量留白、少而准的文字；空状态一句话 + 一个按钮。
- 不要：阴影、渐变、彩色图标、圆角大于 12px；不要用颜色区分本来用文字就能区分的东西。
""",
    },
    {
        "name": "业务中台", "layout": "topbar", "primary": "#1f6feb", "background": "#f2f4f7", "category": "中台",
        "description": "顶部深色一级导航 + 左侧二级菜单：多个业务模块并列、每个模块下若干页面。适合运营中台、订单中台、供应链这类模块多的系统。",
        "tokens": {
            "bg": "#f2f4f7", "card": "#ffffff", "control-bg": "#ffffff", "line": "#e6e8ec", "line-strong": "#d5d9e0",
            "text-1": "#1d2129", "text-2": "#4e5969", "text-3": "#86909c",
            "primary": "#1f6feb", "primary-hover": "#1858c2", "primary-weak": "#e8f0fe", "primary-ring": "rgba(31,111,235,.16)", "on-primary": "#ffffff",
            "danger": "#e5484d", "danger-hover": "#c93a3f", "danger-weak": "#fdeced",
            "success": "#16a34a", "success-weak": "#eafaf0", "warning": "#c2620a", "warning-weak": "#fff4e5",
            "head-bg": "#f7f8fa", "row-hover": "#f7f9fc", "mask": "rgba(15,27,45,.5)",
            "side-bg": "#0f1b2d", "side-text": "#a9b4c4", "side-hover": "rgba(255,255,255,.06)", "side-on": "rgba(255,255,255,.08)",
            "card-radius": "8px", "control-radius": "6px", "btn-radius": "6px", "modal-radius": "10px",
            "card-shadow": "0 1px 2px rgba(15,27,45,.04)", "modal-shadow": "0 16px 48px rgba(15,27,45,.2)",
            "fs": "14px", "fs-title": "18px", "ctl-h": "32px", "th-h": "42px", "td-h": "46px", "metric-fs": "24px",
        },
        "rules": """\
## 用途
模块多的业务中台：订单、商品、库存、结算、会员……每个模块下面若干页面，用户经常在模块之间跳。

## 视觉基调
顶部深色导航条压住整页，下面是浅灰工作区 + 白卡片。信息密，层级靠「顶部模块 → 左侧页面 → 卡片」三层清楚分开。

## 布局（外壳已经做好）
- NAV 的每个分组 = 顶部一个模块；分组里的 items = 左侧二级菜单。模块 4~8 个最合适，每个模块 2~8 页；只有一页的模块不显示左侧菜单。
- 中台首页常用「工作台」：上面一排待办数字（指标卡，点了跳到对应列表），下面左宽右窄 `.grid.two`：左边待办列表、右边快捷入口和公告。
- 列表页、详情页的写法和后台一样：筛选卡片 + 表格卡片 + 分页；详情用 Drawer。

## 配色怎么用
- 主色蓝只给主按钮、链接和选中态；顶栏深色不要再放彩色按钮。
- 跨模块的状态颜色保持一致：同一个「待处理」在所有模块都是 warning。

## 要做 / 不要做
- 要：每个模块名短（2~4 字）；指标卡带「去处理」链接。
- 不要：在页面里再做一排 Tabs 当模块导航（顶部已经有了）；不要一页塞两张以上的大表格。
""",
    },
    {
        "name": "数据中台", "layout": "topbar", "primary": "#5b5bd6", "background": "#f6f7fb", "category": "中台",
        "description": "浅色顶栏 + 左侧二级菜单，指标卡和图表卡为主：数据看板、经营分析、报表中心。比大屏更适合日常在电脑上看和筛选。",
        "tokens": {
            "bg": "#f6f7fb", "card": "#ffffff", "control-bg": "#ffffff", "line": "#e7e8f0", "line-strong": "#d6d8e3",
            "text-1": "#151827", "text-2": "#454a5e", "text-3": "#80869a",
            "primary": "#5b5bd6", "primary-hover": "#4848c4", "primary-weak": "#efeffd", "primary-ring": "rgba(91,91,214,.18)", "on-primary": "#ffffff",
            "danger": "#e5484d", "danger-hover": "#c93a3f", "danger-weak": "#fdeced",
            "success": "#12a150", "success-weak": "#e7f8ee", "warning": "#b8650a", "warning-weak": "#fff3e3",
            "head-bg": "#f8f8fc", "row-hover": "#f7f7fd", "mask": "rgba(21,24,39,.45)",
            "side-bg": "#ffffff", "side-text": "#545a70", "side-hover": "#f4f4fa", "side-on": "#efeffd",
            "side-hover-text": "#151827", "side-on-text": "#151827", "side-brand": "#151827", "side-line": "#e7e8f0",
            "title-bar": "block", "metric-color": "var(--primary)",
            "card-radius": "12px", "control-radius": "8px", "btn-radius": "8px", "modal-radius": "14px",
            "card-shadow": "0 1px 3px rgba(21,24,39,.05)", "modal-shadow": "0 20px 56px rgba(21,24,39,.18)",
            "fs": "14px", "fs-title": "20px", "ctl-h": "32px", "th-h": "40px", "td-h": "44px", "metric-fs": "28px",
        },
        "rules": """\
## 用途
数据看板、经营分析、报表中心、指标管理：在电脑上天天看、要能筛选和下钻。要投屏就用「数据大屏」。

## 视觉基调
浅色、干净、偏冷的靛蓝。数字是主角：指标卡数字大、用主题色；图表卡标题带竖条。

## 布局（外壳已经做好）
- NAV 分组 = 顶部一级（如「经营看板」「用户分析」「报表中心」），items = 左侧具体看板。
- 一个看板从上到下：页面头右上放时间范围（今天 / 近 7 天 / 近 30 天，用一组按钮，选中的是 primary）→ 一排 4 个指标卡 → 2~3 列图表卡 → 明细表格。
- 图表用 ZeroUI.Bars、ZeroUI.Meter，或内联 SVG 画折线；每张图表卡标题写清单位和时间（「近 7 日成交额（万元）」）。

## 配色怎么用
- 一张图只用一个主色，最多再加一个灰色做对比；涨用 `.up` 绿、跌用 `.down` 红。
- 不要彩虹色的饼图和柱子。

## 要做 / 不要做
- 要：每个指标写清口径（metric-foot 里写「较昨日」「近 30 天」）；点指标卡或图表能下钻到明细（跳页或 Drawer）。
- 不要：一屏超过 12 个指标；不要只有图没有数字。
""",
    },
    {
        "name": "温暖柔和", "layout": "mobile", "primary": "#c2603d", "background": "#f6f2ec",
        "description": "米色底、陶土色主色、大圆角、标题用衬线字，温和有质感。适合内容、阅读、生活方式、预约类的手机页面。",
        "tokens": {
            "bg": "#f6f2ec", "outer-bg": "#ebe5dc", "card": "#fffdf9", "control-bg": "#fffdf9", "line": "#ece5da", "line-strong": "#ddd3c5",
            "text-1": "#2b2620", "text-2": "#5a5248", "text-3": "#8a8073",
            "primary": "#c2603d", "primary-hover": "#a44e30", "primary-weak": "#f7e9e2", "primary-ring": "rgba(194,96,61,.18)", "on-primary": "#ffffff",
            "danger": "#b3402f", "danger-hover": "#953426", "danger-weak": "#f8e5e1",
            "success": "#4c7a52", "success-weak": "#e9f1e8", "warning": "#9a6a1c", "warning-weak": "#f8efdc",
            "head-bg": "#f3ede4", "row-hover": "#f8f3ec", "mask": "rgba(43,38,32,.45)", "toast": "rgba(43,38,32,.92)",
            "font-display": "Georgia,\"Songti SC\",\"STSong\",\"Noto Serif SC\",serif",
            "card-radius": "18px", "control-radius": "12px", "btn-radius": "14px", "modal-radius": "22px",
            "card-shadow": "0 1px 2px rgba(43,38,32,.04)", "modal-shadow": "0 18px 48px rgba(43,38,32,.2)", "gap": "14px",
            "fs": "15px", "fs-title": "22px", "ctl-h": "44px", "th-h": "38px", "td-h": "46px", "metric-fs": "24px",
            "fs-control": "15px", "table-min": "520px",
        },
        "rules": """\
## 用途
手机上的内容、阅读、生活方式、预约、社区类页面：要让人觉得舒服、有温度，而不是工具感。

## 视觉基调
米色纸张底 + 奶白卡片 + 陶土色点缀；标题用衬线字（外壳已经设好），正文无衬线。圆角大、间距松，像一本杂志。

## 配色怎么用
- 陶土色只用在主按钮、选中的 Tab、少量强调文字；大面积是米色和奶白。
- 不要纯黑纯白：文字是深棕灰，背景是米色（外壳变量已经是这样）。

## 布局（外壳已经做好）
- 底部 Tab 和「移动端App」一样：NAV 写一个分组，页面放 items 里，前 5 个是 Tab。
- 首页常用：一句问候或标题 → 一张大的推荐卡片 → 一列内容卡片（图片占位 + 标题 + 一行摘要）。图片用带圆角的色块占位，不要外链图片。
- 一屏一个重点；主操作放在底部，用 `kind:'primary block'` 撑满宽。

## 要做 / 不要做
- 要：文案口语、亲切（「今天想读点什么？」）；卡片之间留足间距。
- 不要：密集表格、小字号、硬朗的直角；不要冷色调的蓝色按钮。
""",
    },
    {
        "name": "活力电商", "layout": "mobile", "primary": "#ff5a1f", "background": "#f5f5f7",
        "description": "橙红主色、价格醒目、商品卡片两列排，热闹有购买欲。适合商城、外卖、团购、会员这类用户端手机页面。",
        "tokens": {
            "bg": "#f5f5f7", "outer-bg": "#e8e8ec", "card": "#ffffff", "control-bg": "#ffffff", "line": "#eeeeef", "line-strong": "#dcdce0",
            "text-1": "#1a1a1a", "text-2": "#4a4a4f", "text-3": "#8e8e93",
            "primary": "#ff5a1f", "primary-hover": "#e8470f", "primary-weak": "#fff0e8", "primary-ring": "rgba(255,90,31,.2)", "on-primary": "#ffffff",
            "danger": "#e5252a", "danger-hover": "#c81d22", "danger-weak": "#fdeaea",
            "success": "#1a9f5a", "success-weak": "#e8f7ef", "warning": "#b25e00", "warning-weak": "#fff3e0",
            "head-bg": "#f7f7f9", "row-hover": "#f7f7f9", "mask": "rgba(0,0,0,.5)",
            "metric-color": "var(--primary)",
            "card-radius": "12px", "control-radius": "8px", "btn-radius": "999px", "modal-radius": "16px",
            "card-shadow": "none", "modal-shadow": "0 16px 48px rgba(0,0,0,.2)", "gap": "10px",
            "fs": "14px", "fs-title": "18px", "ctl-h": "40px", "th-h": "36px", "td-h": "44px", "metric-fs": "22px",
            "fs-control": "14px", "table-min": "520px",
        },
        "rules": """\
## 用途
用户端的商城、外卖、团购、会员页面：首页、商品列表、商品详情、购物车、订单、我的。

## 视觉基调
浅灰底 + 白卡片 + 橙红主色，价格和促销醒目，信息排得紧凑但不乱，有逛街的热闹感。

## 配色怎么用
- 橙红 = 价格、主按钮（加入购物车、立即购买）、促销标签；同一屏橙红元素不要超过 3 处，否则什么都不突出。
- 价格写法：`<b style="color:var(--primary)">¥<span style="font-size:20px">99</span>.00</b>`，原价用灰色删除线。

## 布局（外壳已经做好）
- 底部 Tab 一般是：首页、分类、购物车、订单、我的（icon 用 home / grid / list / bell / user）。
- 商品列表两列卡片 `.grid.two`：图片色块占位（1:1）+ 两行标题 + 价格 + 销量；详情页底部固定一条「加入购物车 / 立即购买」。
- 搜索框放在首页顶部第一屏；分类页左边一列分类、右边商品。

## 要做 / 不要做
- 要：数字真实可信（¥ 129.00、已售 2.3 万）；按钮写清动作。
- 不要：满屏渐变和闪烁动效；不要把重要信息只用颜色表达（促销要有文字「限时」「满减」）。
""",
    },
]

COMMON_RULES = """\
## 通用写法（所有内置风格都一样）
- 新页面从外壳起步：页面还是空的就 start_from_shell，已经是外壳就直接 apply_operations 一条 shell_add 写 nav / pages / bind / script。
- 样式只用外壳里的类和 CSS 变量（var(--primary) 等），不要另写一套颜色、字号、圆角；确实要加样式，也引用这些变量。
- 不要僵尸交互：分页、筛选、开关、按钮、行操作都要有真实效果，至少 ZeroUI.Toast 一句。提交时按钮进 loading 防止重复点。
- 示例数据用中性的名字和编号（张三、李四、王五；SO-20261018-0012），不用真实人名。

## 体验底线
- 每页先想清楚「用户来这页干什么」：最重要的数字或操作放在最显眼的位置，其余往后放。
- 列表要有空状态（ZeroUI.Empty）；表单必填标星、错误写在字段下面、提交后有结果反馈。
- 危险操作二次确认，并写清后果（「删除后不能恢复」）；按钮写具体动作（「提交审核」「加入购物车」），少用「确定」「OK」。
- 状态不能只靠颜色：标签里要有文字。正文不要用浅灰字，放在彩色底上的字要够清楚。

## 不要做（一眼就像 AI 做的）
- 紫蓝渐变、霓虹发光、到处加阴影；用 emoji 当图标。
- 什么都包一张卡片、卡片里再套卡片；一排三张一模一样的「图标 + 标题 + 一段话」卡片。
- 所有内容居中；每个区块都加一个大标题和一句空洞的介绍。
- 弹跳、抖动的动画；随手发明新的颜色、字号、圆角（用外壳的变量）。

## 外壳里现成的组件
- ZeroUI.Button({label,kind:'primary'|'danger'|'danger-solid',icon:SVG.plus,id}) · ZeroUI.Tag({text,kind:'info'|'success'|'warning'|'danger'|'neutral'}) · ZeroUI.Field({label,type:'text'|'select'|'textarea',options,required,full,id})
- ZeroUI.Pager({total,page,pageSize}) · ZeroUI.Empty({title,text,action}) · ZeroUI.ListItem({title,desc,extra,id,href}) · ZeroUI.Toast('已保存')
- ZeroUI.Bars({items:[{label,value}],unit,current}) 柱状图 · ZeroUI.Meter({items:[{label,value}],max,unit}) 占比条
- ZeroUI.openModal(ZeroUI.Modal({title,body,wide}), (close,btn)=>{…}) · ZeroUI.openModal(ZeroUI.ConfirmModal({title,message,danger:true}), close=>{…}) · ZeroUI.openDrawer(ZeroUI.Drawer({title,body}), close=>{…})
- Card({title,desc,body,extra}) · 指标卡 `<div class="metric-grid"><div class="metric"><div class="metric-label">今日订单</div><div class="metric-value">1,284</div><div class="metric-foot"><span class="up">+8.2%</span> 较昨日</div></div></div>`
- 栅格 `.grid.two/.three/.four`，键值详情 `<dl class="kv"><dt>…</dt><dd>…</dd></dl>`，开关 `<button class="switch on">`
"""


def build(style: dict) -> tuple[str, str]:
    layout = LAYOUTS[style["layout"]]
    tokens = {**BASE_TOKENS, **style["tokens"]}
    token_css = "\n".join(f"  --{k}:{v};" for k, v in tokens.items())
    shell = (SKELETON.replace("%%NAME%%", style["name"]).replace("%%TOKENS%%", token_css)
             .replace("%%LAYOUT%%", layout["label"]).replace("%%LAYOUT_CSS%%", layout["css"].strip())
             .replace("%%LAYOUT_JS%%", layout["js"].strip()))
    category = style.get("category") or CATEGORY[style["layout"]]
    order = ORDER.index(style["name"]) + 1 if style["name"] in ORDER else len(ORDER) + STYLES.index(style) + 1
    skill = (f"---\nname: {style['name']}\ndescription: {style['description']}\n"
             f"category: {category}\norder: {order}\nlayout: {style['layout']}\n"
             f"primary: \"{style['primary']}\"\nbackground: \"{style['background']}\"\nside: \"{tokens['side-bg']}\"\n---\n"
             f"# {style['name']}\n\n{style['rules']}\n{COMMON_RULES}")
    return skill, shell


def main() -> None:
    for style in STYLES:
        skill, shell = build(style)
        folder = OUT / style["name"]
        (folder / "assets").mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(skill, "utf-8")
        (folder / "assets" / "页面外壳.html").write_text(shell, "utf-8")
        print(f"{style['name']}: SKILL.md {len(skill)} 字，外壳 {len(shell)} 字")


if __name__ == "__main__":
    main()
