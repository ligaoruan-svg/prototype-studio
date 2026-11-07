"""页面外壳里的列表页模板 ListPage：写清楚这一页有什么（页签、筛选、列、行上的按钮、弹窗字段、详情），
模板负责画出来、接好 Store 里的数据和流转、必填校验、翻页。

以前 AI 一页手写五六千字 HTML + 一大段 bindPage，慢、容易断，列宽、操作列、详情抽屉每页各写一套；
现在一页写几百字的配置。数据和流转全走 Store，验收照常能点。
内置风格的外壳生成时就带着；别的外壳在 shell_add 时和 Store 一起补进去（shell_store.ensure）
"""
from __future__ import annotations

MARK = "const ListPage="

LIST_JS = r"""// ===== 列表页模板（ListPage）：写清楚这一页有什么，模板负责画、接数据和流转、校验、翻页 =====
// Pages 里写 repairs(){return ListPage({title:'报修工单',data:'工单',tabs:['待派单','处理中'],filters:[…],columns:[…],actions:[…],toolbar:[…],detail:{…}})}
// 行上的按钮写 flow:'派单' 就按 Store.can 出现、点了 Store.move；带 form 先弹窗填写（required 必填），check(值,行) 返回文字就拦下
const ListPage=(()=>{
  const reg={},state={};
  const STYLE=`.lp-tabs{display:flex;gap:2px;margin-bottom:12px;border-bottom:1px solid var(--line);overflow-x:auto}
.lp-tab{height:40px;padding:0 14px;border:0;border-bottom:2px solid transparent;background:none;color:var(--text-2);cursor:pointer;white-space:nowrap}
.lp-tab:hover{color:var(--primary)}.lp-tab.on{color:var(--primary);border-bottom-color:var(--primary);font-weight:500}
.lp-tab::after{content:attr(data-n);margin-left:6px;padding:0 6px;border-radius:9px;background:var(--head-bg);color:var(--text-3);font-size:12px}
.data-table .lp-ops{position:sticky;right:0;z-index:1;background:var(--card);box-shadow:-1px 0 0 var(--line)}.data-table th.lp-ops{background:var(--head-bg)}
.data-table tr.lp-danger td{background:var(--danger-weak)}.data-table tr.lp-danger td.t1{color:var(--danger);font-weight:600}
.field .lp-check{display:flex;align-items:center;gap:6px;min-height:32px;margin:0;color:var(--text-2);font-weight:400}.field .lp-check input{flex:none;width:16px;height:16px;min-height:0;margin:0;padding:0}.lp-h{margin:20px 0 8px;font-size:14px;color:var(--text-1)}
.lp-logs{margin:0;padding-left:18px;color:var(--text-2)}.lp-logs li{margin:4px 0}.lp-logs time{margin-left:8px;color:var(--text-3);font-size:12px}
.lp-dops{margin-bottom:14px}`;
  // 状态标签的颜色按字面猜：待xx 黄、xx中 蓝、完成 / 通过 绿、关闭 / 作废 灰、差异 / 超时 红；写 tag:{已签约:'success'} 可以指定
  const KIND=s=>/差异|超时|逾期|驳回|拒绝|失败|异常|告警/.test(s)?'danger':/完成|核对|通过|生效|签约|在职|正常|启用|已解决/.test(s)?'success':/关闭|取消|作废|停用|离职|过期|释放/.test(s)?'neutral':/^待/.test(s)?'warning':'info';
  const list=o=>typeof o==='function'?o():(o||[]);
  const fid=f=>f.key||f.label;
  const ov=o=>o&&typeof o==='object'?o.value:o,ol=o=>o&&typeof o==='object'?o.label:o;   // 选项可以写 {value:'W001',label:'张伟'}
  const valOf=(r,c)=>typeof c.value==='function'?c.value(r):r[c.key];
  const blank=v=>v==null||v===''||(Array.isArray(v)&&!v.length);
  function cell(r,c){
    if(c.render)return c.render(r);
    let v=valOf(r,c);
    if(typeof v==='boolean')v=c.bool?c.bool[v?0:1]:(v?'是':'否');
    if(blank(v))return '—';
    if(c.tag)return ZeroUI.Tag({text:String(v),kind:typeof c.tag==='object'?(c.tag[v]||'info'):KIND(String(v))});
    if(c.money)return `<span class="num">${Number(v).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}</span>`;
    return esc(String(v));
  }
  const plain=(r,c)=>{if(c.render||c.tag)return '';const v=valOf(r,c);return blank(v)||typeof v==='boolean'?'':String(v)};
  function match(r,f,v){
    if(blank(v)||v===false||v==='全部')return true;
    const x=typeof f.value==='function'?f.value(r):r[f.key];
    if(f.type==='check')return !!x;
    if(f.type==='select')return String(x)===String(v);
    if(f.type==='daterange'){const d=String(x||'').slice(0,10);return (!v[0]||d>=v[0])&&(!v[1]||d<=v[1])}
    return (f.keys||[f.key]).some(k=>String(r[k]??'').includes(String(v).trim()));
  }
  function filterField(f,v){
    const id=esc(fid(f)),label=`<label>${esc(f.label)}</label>`;
    if(f.type==='select')return `<div class="field">${label}<select data-lpf="${id}"><option>全部</option>${list(f.options).map(o=>`<option value="${esc(String(ov(o)))}" ${String(ov(o))===String(v??'')?'selected':''}>${esc(String(ol(o)))}</option>`).join('')}</select></div>`;
    if(f.type==='check')return `<div class="field">${label}<label class="lp-check"><input type="checkbox" data-lpf="${id}" ${v?'checked':''}>${esc(f.text||'是')}</label></div>`;
    if(f.type==='daterange')return [0,1].map(i=>`<div class="field"><label>${esc(f.label)}${i?'止':'起'}</label><input type="date" data-lpf="${id}" data-i="${i}" value="${esc((v||[])[i]||'')}"></div>`).join('');
    return `<div class="field">${label}<input data-lpf="${id}" value="${esc(v||'')}" placeholder="${esc(f.placeholder||'请输入'+f.label)}"></div>`;
  }
  function readFilters(cfg){
    const out={};
    for(const f of cfg.filters||[]){
      const els=[...document.querySelectorAll(`#content [data-lpf="${CSS.escape(fid(f))}"]`)];
      out[fid(f)]=f.type==='daterange'?els.map(e=>e.value):f.type==='check'?!!els[0]?.checked:(els[0]?.value||'');
    }
    return out;
  }
  const visible=(cfg,a,r)=>(!a.flow||Store.can(cfg.data,r.id,a.flow))&&(!a.show||a.show(r));
  const btn=(a,key,r)=>`<button type="button" class="${r?'lnk':'btn'}${a.primary?' primary':''}${a.danger?' danger':''}" data-lp="act" data-a="${key}"${r?` data-id="${esc(String(r.id))}"`:''}>${esc(a.label)}</button>`;
  function render(k,cfg){
    if(k&&typeof k==='object')cfg=k;
    k=Router.current();   // 页面 key 以路由为准：写成 ListPage('别的名',…) 也不会串页
    if(!document.getElementById('lp-css')){const s=document.createElement('style');s.id='lp-css';s.textContent=STYLE;document.head.appendChild(s)}
    if(!reg[k]&&typeof PageEvents!=='undefined')PageEvents.on(k,'click','[data-lp],[data-page-go]',el=>handle(k,el));
    reg[k]=cfg;lint(cfg);
    const tabs=cfg.tabs||[],st=state[k]||(state[k]={tab:tabs[0]||'',filter:{},page:1});
    let rows=Store.all(cfg.data);if(cfg.where)rows=rows.filter(cfg.where);
    const counts={};for(const t of tabs)counts[t]=t==='全部'?rows.length:rows.filter(r=>r.status===t).length;
    if(st.tab&&st.tab!=='全部')rows=rows.filter(r=>r.status===st.tab);
    for(const f of cfg.filters||[])rows=rows.filter(r=>match(r,f,st.filter[fid(f)]));
    const size=cfg.pageSize||10,pages=Math.max(1,Math.ceil(rows.length/size));st.page=Math.min(Math.max(1,st.page),pages);
    const shown=rows.slice((st.page-1)*size,st.page*size),cols=cfg.columns||[],acts=cfg.actions||[];
    const opsW=Math.min(280,Math.max(96,acts.reduce((n,a)=>n+a.label.length*14+16,24)));
    const minW=cols.reduce((n,c)=>n+(c.width||120),0)+(acts.length?opsW:0);
    const tabBar=tabs.length?`<div class="lp-tabs" role="tablist">${tabs.map(t=>`<button type="button" role="tab" class="lp-tab ${t===st.tab?'on':''}" aria-selected="${t===st.tab}" data-lp="tab" data-v="${esc(t)}" data-n="${counts[t]}">${esc(t)}</button>`).join('')}</div>`:'';
    const filter=(cfg.filters||[]).length?Card({title:'筛选',body:`<div class="filter">${cfg.filters.map(f=>filterField(f,st.filter[fid(f)])).join('')}<div class="filter-actions"><button type="button" class="btn primary" data-lp="query">查询</button><button type="button" class="btn" data-lp="reset">重置</button></div></div>`}):'';
    const head=`<tr>${cols.map(c=>`<th${c.width?` style="width:${c.width}px"`:''}>${esc(c.label)}</th>`).join('')}${acts.length?`<th class="lp-ops" style="width:${opsW}px">操作</th>`:''}</tr>`;
    const body=shown.length?shown.map(r=>{const cls=cfg.rowClass&&cfg.rowClass(r);return `<tr${cls?` class="lp-${esc(cls)}"`:''}>${cols.map((c,i)=>`<td${i===0?' class="t1"':''} title="${esc(plain(r,c))}">${cell(r,c)}</td>`).join('')}${acts.length?`<td class="lp-ops"><div class="ops">${acts.map((a,i)=>visible(cfg,a,r)?btn(a,'r'+i,r):'').join('')}</div></td>`:''}</tr>`}).join('')
      :`<tr><td colspan="${cols.length+(acts.length?1:0)}">${ZeroUI.Empty({title:'暂无数据',text:'当前条件下没有数据。',action:''})}</td></tr>`;
    const table=Card({title:cfg.listTitle||cfg.title+'列表',desc:`共 ${rows.length} 条`,body:`<div class="tw"><table class="data-table" style="min-width:${minW}px"><thead>${head}</thead><tbody>${body}</tbody></table></div>${ZeroUI.Pager({total:rows.length,page:st.page,pageSize:size})}`});
    return pageShell(cfg.title,cfg.desc||'',tabBar+filter+table+(cfg.extra?cfg.extra():''),(cfg.toolbar||[]).map((a,i)=>btn(a,'t'+i,null)).join(''));
  }
  // 配置写错了报到控制台（自检、check_page 会收到），页面照样能打开
  const said=new Set();
  function lint(cfg){
    const say=m=>{if(!said.has(m)){said.add(m);console.error(m)}};
    if(!Store.names().includes(cfg.data)){say(`ListPage「${cfg.title}」：Store 里没有「${cfg.data}」，先 Store.define('${cfg.data}',[…])`);return}
    const flow=Store.flow(cfg.data)||{};
    for(const a of [...(cfg.actions||[]),...(cfg.toolbar||[])]){
      if(a.flow&&!(a.flow in flow))say(`ListPage「${cfg.title}」的按钮「${a.label}」写了 flow:'${a.flow}'，但 Store.flow('${cfg.data}') 里没有这个动作`);
      // 自己写弹窗（run）的流转按钮也要写 flow，不然每个状态都出现（已完成的工单上还有「派单」）
      if(!a.flow&&!a.show&&(cfg.actions||[]).includes(a)&&a.label in flow)say(`ListPage「${cfg.title}」的按钮「${a.label}」是流转动作，要写 flow:'${a.label}'（run 自己弹窗也照样写），不然每个状态都会出现`);
    }
  }
  function handle(k,el){
    const cfg=reg[k],st=state[k];if(!cfg)return;
    if(el.dataset.pageGo!==undefined){if(el.disabled)return;st.page=+el.dataset.pageGo;Router.render();return}
    const kind=el.dataset.lp;
    if(kind==='tab'){st.tab=el.dataset.v;st.page=1;Router.render()}
    else if(kind==='query'){st.filter=readFilters(cfg);st.page=1;Router.render()}
    else if(kind==='reset'){st.filter={};st.page=1;Router.render()}
    else if(kind==='act'){
      const key=el.dataset.a,a=(key[0]==='t'?cfg.toolbar:cfg.actions)[+key.slice(1)],r=el.dataset.id!==undefined?Store.get(cfg.data,el.dataset.id):null;
      if(!a)return;
      if(el.closest('#activeDrawer')){document.getElementById('layerHost').innerHTML='';if(ZeroUI._unlockLayer)ZeroUI._unlockLayer()}   // 详情里点的：先收起详情再做
      act(cfg,a,r,el);
    }
  }
  function control(f,v){
    const attr=`data-lpf="${esc(f.key)}"${f.readonly?' disabled':''}`;
    if(f.type==='select')return `<select ${attr}><option value="">请选择</option>${list(f.options).map(o=>`<option value="${esc(String(ov(o)))}" ${String(ov(o))===String(v??'')?'selected':''}>${esc(String(ol(o)))}</option>`).join('')}</select>`;
    if(f.type==='textarea')return `<textarea ${attr} placeholder="${esc(f.placeholder||'请输入'+f.label)}">${esc(v??'')}</textarea>`;
    if(f.type==='check')return `<label class="lp-check"><input type="checkbox" ${attr} ${v?'checked':''}>${esc(f.text||'是')}</label>`;
    const type={money:'number',number:'number',date:'date',datetime:'datetime-local',file:'file'}[f.type]||'text';
    return `<input type="${type}" ${attr}${f.type==='money'?' step="0.01" min="0"':''}${type==='file'?'':` value="${esc(v??'')}"`} placeholder="${esc(f.placeholder||'请输入'+f.label)}">`;
  }
  function read(el,f){
    if(!el)return '';
    if(f.type==='check')return el.checked;
    if(f.type==='file')return el.files&&el.files[0]?el.files[0].name:'';
    if(f.type==='money'||f.type==='number')return el.value===''?'':Number(el.value);
    return String(el.value).trim();
  }
  function act(cfg,a,r,el){
    const ok=()=>UI.Toast(a.done||`已${a.label}`);
    if(a.go){location.hash=a.go;return}
    if(a.run){a.run(r);return}
    if(a.detail){detail(cfg,r,el);return}
    const apply=v=>{
      if(a.patch)v={...v,...(typeof a.patch==='function'?a.patch(r,v):a.patch)};   // 顺带要记的（派单时间、操作人）
      if(a.flow)return Store.move(cfg.data,r.id,a.flow,v);
      if(a.add){Store.add(cfg.data,{...(typeof a.defaults==='function'?a.defaults():a.defaults||{}),...v});return true}
      if(a.remove){Store.remove(cfg.data,r.id);return true}
      if(r)Store.update(cfg.data,r.id,v);
      return true;
    };
    if(!a.form){
      if(a.confirm||a.remove)UI.openModal(UI.ConfirmModal({title:a.title||'确认'+a.label,message:a.confirm||`${a.label}后不能恢复。`,danger:!!(a.danger||a.remove)}),close=>{close();if(apply({})!==false)ok()},el);
      else if(apply({})!==false)ok();
      return;
    }
    const fields=list(a.form);
    const initial=f=>typeof f.value==='function'?f.value(r):f.value!==undefined?f.value:(a.edit&&r?r[f.key]:'');
    const body=`<div class="form-grid">${fields.map(f=>`<div class="field${f.type==='textarea'||f.full?' full':''}" data-lpw="${esc(f.key)}"><label>${esc(f.label)}${f.required?'<span class="req">*</span>':''}</label>${control(f,initial(f))}${f.hint?`<div class="hint">${esc(f.hint)}</div>`:''}</div>`).join('')}</div>`;
    UI.openModal(UI.Modal({title:a.title||a.label,body,confirm:a.ok||'确定',wide:fields.length>6}),close=>{
      const v={},miss=[];
      for(const f of fields){
        if(f.readonly)continue;
        const x=read(document.querySelector(`#activeModal [data-lpf="${CSS.escape(f.key)}"]`),f);v[f.key]=x;
        const box=document.querySelector(`#activeModal [data-lpw="${CSS.escape(f.key)}"]`);
        if(f.required&&(blank(x)||x===false)){miss.push(f.label);if(box)box.classList.add('invalid')}else if(box)box.classList.remove('invalid');
      }
      if(miss.length){UI.Toast('请填写'+miss.join('、'),'error');return}
      const msg=a.check&&a.check(v,r);if(msg){UI.Toast(msg,'error');return}
      close();if(apply(v)!==false)ok();
    },el);
  }
  // 详情抽屉：字段（不写就用列）+ 这一条能做的按钮 + 流转记录
  function detail(cfg,r,el){
    const d=cfg.detail||{},fields=d.fields||cfg.columns||[];
    const acts=(cfg.actions||[]).map((a,i)=>!a.detail&&visible(cfg,a,r)?btn(a,'r'+i,r):'').join('');
    const logs=(r.logs||[]).length?`<h4 class="lp-h">流转记录</h4><ol class="lp-logs">${r.logs.map(l=>`<li><b>${esc(l.action)}</b>：${esc(l.from)} → ${esc(l.to)}<time>${esc(l.at)}</time></li>`).join('')}</ol>`:'';
    UI.openDrawer(UI.Drawer({title:d.title||cfg.data+'详情',body:`${acts?`<div class="ops lp-dops">${acts}</div>`:''}<dl class="kv">${fields.map(c=>`<dt>${esc(c.label)}</dt><dd>${cell(r,c)}</dd>`).join('')}</dl>${logs}`,footer:'none'}),null,el);
  }
  return render;
})();
"""

# 给 AI 的用法：shell_api（start_from_shell 返回）、内置风格 SKILL.md 都用这一份
LIST_GUIDE = [
    "列表类页面（页签 + 筛选 + 表格 + 行按钮 + 弹窗 + 详情）不用手写 HTML 和 bindPage：pages 里写 orders(){return ListPage({...})}，"
    "模板负责画、接 Store 数据和流转、必填校验、翻页；统计页、看板、大屏、向导、复杂表单还是手写 pageShell(...)，两种可以混用",
    "配置：title、desc、data:'Store 名'、tabs:['待派单','处理中',…]（按 status 分，可加 '全部'）、"
    "filters:[{key,label,type:'select'|'check'|'daterange',options,text}]（不写 type 是文字搜索，keys:[…] 多字段搜）、"
    "columns:[{key,label,width,tag:true 或 {值:'success'},money:true,bool:['紧急','普通'],value:r=>…}]、"
    "actions:[行按钮]、toolbar:[顶部按钮]、detail:{title,fields:[写法同 columns]}、rowClass:r=>'danger'（标红）",
    "按钮：{label:'查看',detail:true}；{label:'派单',flow:'派单',form:[{key:'worker',label:'维修工',type:'select',required:true,"
    "options:()=>Store.all('维修工').map(w=>({value:w.id,label:w.name}))}]}（flow 按 Store.can 出现，填完点确定就 Store.move）；"
    "{label:'接单',flow:'接单',confirm:'确认接单？'}；自己写弹窗用 run:r=>…，流转按钮照样写 flow（只管按状态出现，run 里自己 Store.move）；{label:'编辑',edit:true,form:[…]}；{label:'删除',remove:true}；"
    "顶部 {label:'新增工单',primary:true,add:true,defaults:{status:'待派单'},form:[…]}；跳页 {label:'看合同',go:'#contracts'}",
    "表单字段 type：text / select / textarea / date / datetime / number / money / file / check；required 必填，readonly 只读带出，value:r=>默认值；"
    "规则写成 check:(值,行)=>'不通过的提示'（返回文字就拦下），顺带要记的写 patch:(行,值)=>({dispatchAt:'…'})",
]
