"""Early, sandbox-compatible inspector. All editor visuals are separate overlays."""
import json

_TEMPLATE = r'''
<script data-prototype-agent-bridge>
(() => {
  const CFG = __CFG__;
  const send = (type, payload={}) => parent.postMessage({source:'prototype-agent', ...CFG, type, ...payload}, '*');
  // 选中是一组，不是一个。点一下换一个，按住 Shift/⌘ 点是往里加——
  // 同一种改动落在好几处时（表单里散着的那些「手工填写」标签），
  // 一个一个点、一条一条写实在不合理。
  let mode='interact', picked=[], hover=null, box, pickBoxes=[], caption, dragStart=null, dragBox=null, markers=[];
  // 后台展开用的副本：原生 alert/confirm 会把真实对话框弹到用户屏幕上，
  // 打开新窗口、打印同理。副本里点什么都只是为了看会弹出什么，统统静音。
  const PROBE=!!window.__paProbe;
  if(PROBE){try{window.alert=()=>{};window.confirm=()=>false;window.prompt=()=>null;window.open=()=>null;window.print=()=>{};}catch{}}
  const esc = value => CSS.escape(String(value));
  const scrollContainers = new Set(); let scrollTimer, restoringScroll=false;
  // Opaque sandbox origins cannot use native localStorage. Keep demo data scoped
  // to this project/page; only the trusted host persists it after receiving events.
  const data = {...(window.__paStorageSeed || {})};
  const store = {getItem:k=>Object.hasOwn(data,k)?data[k]:null,
    setItem:(k,v)=>{data[k]=String(v);send('STORAGE',{data});},
    removeItem:k=>{delete data[k];send('STORAGE',{data});},
    clear:()=>{Object.keys(data).forEach(k=>delete data[k]);send('STORAGE',{data});},
    key:i=>Object.keys(data)[i]??null, get length(){return Object.keys(data).length;}};
  try { Object.defineProperty(window,'localStorage',{value:store}); Object.defineProperty(window,'sessionStorage',{value:store}); } catch {}
  if(window.__paRoute&&String(window.__paRoute).startsWith('#')) location.hash=window.__paRoute;
  window.addEventListener('hashchange',()=>send('ROUTE',{hash:location.hash}));
  window.addEventListener('error',e=>{if(e.message)send('RUNTIME_ERROR',{message:e.message,lineno:e.lineno});});
  window.addEventListener('unhandledrejection',e=>send('RUNTIME_ERROR',{message:String(e.reason?.message||e.reason||'Promise rejection')}));
  const originalError=console.error;
  console.error=(...args)=>{send('RUNTIME_ERROR',{message:args.map(x=>String(x?.message||x)).join(' ').slice(0,1200)});originalError.apply(console,args);};

  function selectorFor(el){
    const pid=el.getAttribute('data-pid');
    if(pid && document.querySelectorAll(`[data-pid="${esc(pid)}"]`).length===1)return `[data-pid="${esc(pid)}"]`;
    if(el.id && document.querySelectorAll('#'+esc(el.id)).length===1)return '#'+esc(el.id);
    const parts=[]; let node=el;
    while(node && node.nodeType===1){
      let part=node.tagName.toLowerCase();
      const classes=[...node.classList].slice(0,2);
      if(classes.length)part+='.'+classes.map(esc).join('.');
      const siblings=node.parentElement?[...node.parentElement.children].filter(n=>n.tagName===node.tagName):[];
      if(siblings.length>1)part+=`:nth-of-type(${siblings.indexOf(node)+1})`;
      parts.unshift(part);
      const path=parts.join(' > ');
      if(document.querySelectorAll(path).length===1)return path;
      node=node.parentElement;
    }
    return parts.join(' > ');
  }
  function describe(el){
    const cs=getComputedStyle(el);
    return {selector:selectorFor(el),pid:el.dataset.pid||'',tag:el.tagName.toLowerCase(),
      text:(el.innerText||el.textContent||'').trim().slice(0,500),outer_html:el.outerHTML.slice(0,5000),modal:modalOf(el),
      styles:Object.fromEntries(['color','background-color','font-size','border-radius','padding-top','padding-bottom','padding-left','padding-right','display'].map(k=>[k,cs.getPropertyValue(k)]))};
  }
  function scrollState(){return {window:{x:scrollX,y:scrollY},containers:[...scrollContainers].filter(el=>el.isConnected).slice(0,40).map(el=>({selector:selectorFor(el),x:el.scrollLeft,y:el.scrollTop}))};}
  function restoreScroll(){
    const state=window.__paScrollSeed;if(!state)return;restoringScroll=true;
    for(const item of state.containers||[]){try{const el=document.querySelector(item.selector);if(el){el.scrollLeft=item.x;el.scrollTop=item.y;scrollContainers.add(el);}}catch{}}
    window.scrollTo(state.window?.x||0,state.window?.y||0);
    requestAnimationFrame(()=>{restoringScroll=false;paint();});
  }
  function highlight(targets){
    const elements=(targets||[]).filter(t=>!t.deleted).flatMap(t=>{try{const el=document.querySelector(t.selector);return el?[el]:[];}catch{return [];}});
    const first=elements[0];if(first){const r=first.getBoundingClientRect();if(r.bottom<0||r.top>innerHeight||r.right<0||r.left>innerWidth)first.scrollIntoView({block:'center',inline:'nearest'});}
    for(const el of elements){const out=overlay('2px solid #b8532f'),r=el.getBoundingClientRect();Object.assign(out.style,{display:'block',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px',background:'#b8532f16'});if(!matchMedia('(prefers-reduced-motion: reduce)').matches)out.animate([{opacity:1},{opacity:.2},{opacity:1}],{duration:650,iterations:3});setTimeout(()=>out.remove(),2000);}
  }
  function overlay(border){
    const el=document.createElement('div');el.dataset.paOverlay='1';
    Object.assign(el.style,{position:'fixed',pointerEvents:'none',zIndex:'2147483646',border,boxSizing:'border-box',display:'none',borderRadius:'2px'});
    document.documentElement.appendChild(el);return el;
  }
  function paintPicks(){
    while(pickBoxes.length>picked.length){const x=pickBoxes.pop();x.frame.remove();x.tag.remove();}
    while(pickBoxes.length<picked.length){
      const frame=overlay('2px solid #b8532f');
      const tag=overlay('0');
      Object.assign(tag.style,{width:'18px',height:'18px',borderRadius:'50%',background:'#b8532f',
        color:'#fff',font:'10px/18px system-ui',textAlign:'center',display:'none'});
      pickBoxes.push({frame,tag});
    }
    picked.forEach((el,i)=>{
      const {frame,tag}=pickBoxes[i];
      if(!el?.isConnected||mode==='interact'){frame.style.display='none';tag.style.display='none';return;}
      const r=el.getBoundingClientRect();
      Object.assign(frame.style,{display:'block',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px',background:'#b8532f10'});
      // 只有选了不止一个才标序号；只有一个时序号是噪音
      tag.textContent=i+1;
      tag.style.display=picked.length>1?'block':'none';
      tag.style.left=(r.left-9)+'px';tag.style.top=(r.top-9)+'px';
    });
  }
  function reportPicks(){
    if(!picked.length){send('SELECTION_CLEARED',{});return;}
    if(picked.length===1){send('SELECTED',describe(picked[0]));return;}
    // 多选走和拉框同一条路：targets 数组、「已选中 N 个元素」、一次说清怎么改
    const targets=picked.map(describe);
    let ancestor=picked[0];
    while(ancestor&&picked.some(n=>!ancestor.contains(n)))ancestor=ancestor.parentElement;
    send('REGION_SELECTED',{...describe(ancestor||document.body),kind:'region',
      text:targets.map(n=>n.text||n.tag).join(' · ').slice(0,500),targets});
  }
  function place(out,el){
    if(!out)return;
    if(!el?.isConnected || mode==='interact'){out.style.display='none';return;}
    const r=el.getBoundingClientRect();
    Object.assign(out.style,{display:'block',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});
  }
  function paint(){place(box,hover);paintPicks();for(const {el,pin} of markers){const r=el.getBoundingClientRect();pin.style.display=el.isConnected&&r.width?'grid':'none';pin.style.left=(r.right-10)+'px';pin.style.top=(r.top-10)+'px';}if(caption){caption.style.display=(mode==='select'&&hover?.isConnected)?'block':'none';if(hover?.isConnected){const r=hover.getBoundingClientRect();caption.textContent=hover.dataset.pid||hover.tagName.toLowerCase();caption.style.left=Math.max(4,r.left)+'px';caption.style.top=Math.max(4,r.top-26)+'px';}}}
  window.addEventListener('mousemove',e=>{if(mode!=='select')return;hover=e.target instanceof Element&&!e.target.closest('[data-pa-overlay]')?e.target:null;paint();},true);
  window.addEventListener('click',e=>{
    const el=e.target instanceof Element?e.target:null;if(!el)return;
    if(mode==='box'){e.preventDefault();e.stopImmediatePropagation();return;}
    if(mode==='select'){
      e.preventDefault();e.stopImmediatePropagation();hover=null;
      if(e.shiftKey||e.metaKey||e.ctrlKey){
        const at=picked.indexOf(el);
        if(at>=0)picked.splice(at,1);else if(picked.length<16)picked.push(el);
      }else picked=[el];
      paint();reportPicks();return;
    }
    const link=el.closest('a[href]');const href=link?.getAttribute('href')||'';
    if(href.startsWith('#')){e.preventDefault();location.hash=href;return;}
    if(/\.html?(?:[?#].*)?$/i.test(href) && !/^(?:https?:)?\/\//i.test(href)){e.preventDefault();send('NAVIGATE',{href});}
  },true);
  for(const type of ['pointerdown','mousedown'])window.addEventListener(type,e=>{if(mode==='select'){e.preventDefault();e.stopImmediatePropagation();}},true);
  function dragDown(e){
    if(mode!=='box'||e.button!==0)return;e.preventDefault();e.stopImmediatePropagation();
    if(dragStart)return;
    dragStart={x:e.clientX,y:e.clientY};if(!dragBox)dragBox=overlay('2px solid #b8532f');
    Object.assign(dragBox.style,{display:'block',left:e.clientX+'px',top:e.clientY+'px',width:'0',height:'0',background:'#b8532f12'});
  }
  function dragMove(e){
    if(!dragStart)return;e.preventDefault();e.stopImmediatePropagation();
    Object.assign(dragBox.style,{left:Math.min(dragStart.x,e.clientX)+'px',top:Math.min(dragStart.y,e.clientY)+'px',width:Math.abs(e.clientX-dragStart.x)+'px',height:Math.abs(e.clientY-dragStart.y)+'px'});
  }
  function dragUp(e){
    if(!dragStart)return;e.preventDefault();e.stopImmediatePropagation();
    const r={left:Math.min(dragStart.x,e.clientX),top:Math.min(dragStart.y,e.clientY),right:Math.max(dragStart.x,e.clientX),bottom:Math.max(dragStart.y,e.clientY)};dragStart=null;
    if(r.right-r.left<8||r.bottom-r.top<8){dragBox.style.display='none';return;}
    selectRegion(r);
  }
  // 只按几何位置筛，会把弹窗背后的元素一起选进来——它们确实在框里，
  // 但用户看不见，改的也不是它们。这里用命中测试确认"这个点上露在最前面的
  // 就是它"，遮罩、弹窗、固定头都会自然地挡住后面的内容。
  // 自己的 overlay 都是 pointer-events:none，不会被 elementFromPoint 命中。
  function visibleAt(el,x,y){
    const top=document.elementFromPoint(x,y);
    // top.contains(el)：元素自身被 CSS 设了 pointer-events:none，命中的是它的祖先，
    // 这种情况它是看得见的，不该被排除。
    return !!top&&(top===el||el.contains(top)||top.contains(el));
  }
  function selectRegion(r){
    const inBox=[...document.body.querySelectorAll('button,a,input,select,textarea,h1,h2,h3,h4,p,label,th,td,span,li')].filter(el=>{
      const b=el.getBoundingClientRect(),x=b.left+b.width/2,y=b.top+b.height/2;
      return b.width>0&&b.height>0&&x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom;
    });
    const nodes=inBox.filter(el=>{
      const b=el.getBoundingClientRect();
      return visibleAt(el,b.left+b.width/2,b.top+b.height/2);
    }).filter((el,_,all)=>!all.some(n=>n!==el&&el.contains(n))).slice(0,16);
    if(!nodes.length){
      send('NOTICE',{message:inBox.length
        ? '这片区域被弹窗或遮罩挡住了，只能框选当前看得见的内容'
        : '框内没有可定位的元素，请扩大范围或使用点选'});
      return;
    }
    let ancestor=nodes[0];while(ancestor&&nodes.some(n=>!ancestor.contains(n)))ancestor=ancestor.parentElement;
    const targets=nodes.map(describe);
    send('REGION_SELECTED',{...describe(ancestor||document.body),kind:'region',text:targets.map(n=>n.text||n.tag).join(' · ').slice(0,500),targets,bounds:r});
  }
  for(const prefix of ['pointer','mouse']){
    window.addEventListener(prefix+'down',dragDown,true);
    window.addEventListener(prefix+'move',dragMove,true);
    window.addEventListener(prefix+'up',dragUp,true);
  }
  window.addEventListener('submit',e=>{e.preventDefault();if(mode==='select')e.stopImmediatePropagation();},true);
  window.addEventListener('scroll',e=>{paint();if(restoringScroll)return;if(e.target instanceof Element&&!e.target.closest('[data-pa-overlay]'))scrollContainers.add(e.target);clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>send('SCROLL_STATE',{state:scrollState()}),80);},true);
  window.addEventListener('resize',()=>{paint();send('WIDTH',{width:innerWidth});});
  window.addEventListener('keydown',e=>{if(!e.isTrusted||e.target?.isContentEditable||e.target?.closest?.('input,textarea,select'))return;const key=e.key.toLowerCase(),command=e.metaKey||e.ctrlKey;if((!command&&!e.altKey&&['h','v','b','e','escape'].includes(key))||(command&&['z','/','enter'].includes(key))){e.preventDefault();send('SHORTCUT',{key:e.key,metaKey:e.metaKey,ctrlKey:e.ctrlKey,altKey:e.altKey,shiftKey:e.shiftKey});}},true);
  // ===== 展开：找出这一页能打开的所有弹窗 =====
  // 原型里的弹窗大多是 JS 现拼的，源码里搜不到、预览里要点好几层才看得见。
  // 这里在一个后台副本里把按钮挨个点一遍：点完多出来一层遮罩，就是它打开的弹窗；
  // 再顺着弹窗里的按钮（下一步、新排放源……）往下点，整条链就出来了。
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const LAYER_SEL='[role=dialog],[aria-modal=true],dialog,[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog],[class*=drawer],[class*=popup],[class*=mask],[class*=overlay]';
  const LAYER_NAME=/modal|dialog|drawer|popup|mask|overlay|layer/i;
  const CLICKABLE='button,a[href],[data-action],[data-cx],[onclick],[role=button],.btn,[class*=btn]';
  // 导航、页签、分页只是换内容，不会弹窗；跳过它们省掉大半次数。
  // 不用 [class*=tab]：那会把 table 里的「编辑」也一起跳过。
  const SKIP_NAME=/(^|[\s_-])(tabs?|tab-?bar|sidebar|side-?nav|menu|pager|pagination|breadcrumb)($|[\s_-])/i;
  function inSkipZone(el){
    if(el.closest('nav,aside,#nav,[role=tab],[role=tablist],[data-pa-overlay]'))return true;
    for(let n=el,i=0;n&&n!==document.body&&i<8;n=n.parentElement,i++)if(SKIP_NAME.test(String(n.className)))return true;
    return false;
  }
  const CLOSE_TEXT=/^(×|✕|✖|x|X|取消|关闭|返回)$/;
  // 会真的落数据的按钮不点：在真实预览里复现路径时，点了就是改了用户的演示数据
  const COMMIT_TEXT=/^(保存|确定|确认|提交|完成|删除|移除|确认删除|启用|停用|发布|撤回|通过|驳回)$/;
  const NOISE_TEXT=/^(查询|搜索|重置|刷新|导出.*|下载.*|全屏|退出.*|打印|返回.*|收起|展开|更多|上一页|下一页)$/;
  const WIZARD_TEXT=/^(下一步|继续|下一页|next)/i;
  // vis：按钮、下拉这种小东西看得见就行；shown：够大才算得上一层弹窗
  function vis(el){
    if(!el?.isConnected)return false;const cs=getComputedStyle(el);
    if(cs.display==='none'||cs.visibility==='hidden'||Number(cs.opacity)===0)return false;
    const r=el.getBoundingClientRect();return r.width>0&&r.height>0;
  }
  function shown(el){if(!vis(el))return false;const r=el.getBoundingClientRect();return r.width>40&&r.height>30;}
  function isLayer(el){
    if(el.closest('[data-pa-overlay]')||!shown(el))return false;
    if(el.matches('[role=dialog],[aria-modal=true],dialog[open]'))return true;
    const cs=getComputedStyle(el);if(cs.position!=='fixed')return false;
    const r=el.getBoundingClientRect(),area=r.width*r.height/(innerWidth*innerHeight);
    return area>=0.5||(area>=0.1&&LAYER_NAME.test(String(el.className)+' '+el.id));
  }
  function layers(){
    const pool=new Set([...document.body.children,...[...document.body.children].flatMap(c=>[...c.children]),...document.querySelectorAll(LAYER_SEL)]);
    const out=[...pool].filter(isLayer);
    return out.filter(el=>!out.some(o=>o!==el&&o.contains(el)));
  }
  function titleOf(el){
    const t=el.querySelector('[class*=title],[class*=Title],h1,h2,h3,h4,[class*=header],[class*=head]');
    const line=((t&&t.innerText)||el.innerText||'').trim().split('\n')[0].trim();
    return line.slice(0,40)||'弹窗';
  }
  // 一层弹窗的身份：标题 + 它有哪些字段。
  // 同一个 #modal 换了内容就是新弹窗——哪怕标题一样（「新增因子」选完类型点下一步，标题还叫新增因子，字段全换了）；
  // 字段没变、只是多了几行（弹窗里点「新增气体」）不算。
  function keyOf(el){
    const fields=[...new Set([...el.querySelectorAll('label,th,legend,[class*=label]')].map(n=>(n.innerText||'').trim().split('\n')[0].slice(0,16)).filter(Boolean))].sort().slice(0,40);
    return titleOf(el)+'#'+fields.join(',');
  }
  function snapshot(){return new Map(layers().map(el=>[el,keyOf(el)]));}
  function opened(base){return layers().filter(el=>!base.has(el)||base.get(el)!==keyOf(el));}
  function topOpen(base){const list=opened(base);return list[list.length-1]||null;}
  function modalOf(el){
    try{const L=layers().find(l=>l.contains(el)&&(l.matches('[role=dialog],[aria-modal=true],dialog')||l.getBoundingClientRect().width*l.getBoundingClientRect().height>=innerWidth*innerHeight*0.5||LAYER_NAME.test(String(l.className)+' '+l.id)));
      return L?titleOf(L):'';}catch{return '';}
  }
  function labelOf(el){
    let text=(el.innerText||el.value||el.getAttribute('aria-label')||el.title||'').replace(/\s+/g,' ').trim().slice(0,30);
    // 「+」「⋯」这种按钮光看字不知道是干嘛的，带上它所在的标题
    if(text.length<=1){const ctx=(el.parentElement?.innerText||'').replace(text,'').replace(/\s+/g,' ').trim().slice(0,12);if(ctx)text=ctx+' '+(text||'按钮');}
    if(el.closest('tr'))text='表格行 · '+text;
    return text;
  }
  function targetOf(el){
    const attr=['data-action','data-cx','onclick'].find(a=>el.hasAttribute(a))||'';
    return {selector:selectorFor(el),attr,value:attr?el.getAttribute(attr):'',text:labelOf(el),tag:el.tagName.toLowerCase()};
  }
  function findTarget(t,scope){
    scope=scope||document;let el=null;
    if(t.attr){const pool=[...scope.querySelectorAll(`[${t.attr}="${esc(t.value)}"]`)].filter(shown);el=pool.find(n=>labelOf(n)===t.text)||pool[0]||null;}
    if(!el){try{const n=scope.querySelector(t.selector);if(n&&vis(n))el=n;}catch{}}
    if(!el&&t.text)el=[...scope.querySelectorAll(CLICKABLE)].find(n=>vis(n)&&labelOf(n)===t.text)||null;
    return el;
  }
  // 应用外壳（固定的顶栏、侧栏）里的按钮是全局的：全屏、折叠菜单、账号下拉，不属于这一页
  function inChrome(el){
    for(let n=el.parentElement;n&&n!==document.body;n=n.parentElement){const p=getComputedStyle(n).position;if(p==='fixed'||p==='sticky')return true;}
    return false;
  }
  const bare=el=>(el.innerText||el.value||'').replace(/\s+/g,' ').trim().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu,'');
  function triggersIn(scope,inLayer,skip){
    const seen=new Set(),groups={},out=[],open=inLayer?[]:layers();
    for(const el of scope.querySelectorAll(CLICKABLE)){
      if(out.length>=40)break;
      if(!vis(el)||el.disabled||el.closest('[data-pa-overlay]'))continue;
      if(!inLayer&&(inSkipZone(el)||inChrome(el)||open.some(l=>l.contains(el))))continue;
      const outer=el.parentElement?.closest(CLICKABLE);if(outer&&scope.contains(outer))continue;
      const raw=bare(el);
      if(CLOSE_TEXT.test(raw)||COMMIT_TEXT.test(raw)||NOISE_TEXT.test(raw))continue;
      if(el.matches('[class*=close]')||(skip&&skip.includes(el)))continue;
      const href=el.getAttribute('href')||'';
      if(el.tagName==='A'&&!el.matches('[data-action],[data-cx],[onclick]')&&(href.startsWith('#')||/\.html?(?:[?#].*)?$/i.test(href)||/^(?:https?:)?\/\//i.test(href)))continue;
      const t=targetOf(el);if(!t.text)continue;
      const group=t.attr?t.attr+'='+t.value.replace(/\d+/g,'#'):t.tag+'|'+t.text,key=group+'|'+t.text;
      // 同一个动作挂在一排按钮上（行业列表、每一行的编辑）只试两个，试多了全是重复
      if(seen.has(key)||(groups[group]||0)>=2)continue;
      seen.add(key);groups[group]=(groups[group]||0)+1;out.push(t);
    }
    return out;
  }
  // 「选类型 → 下一步」这种向导：同一个按钮，下拉选不同的值会走到不同的弹窗
  function wizardOf(L){
    const buttons=[...L.querySelectorAll('button,[role=button],.btn')].filter(shown);
    const next=buttons.find(b=>WIZARD_TEXT.test((b.innerText||'').trim()));
    const select=[...L.querySelectorAll('select')].find(s=>vis(s)&&s.options.length>=2&&s.options.length<=8);
    if(!next||!select)return {next:null,branches:[]};
    const nt=targetOf(next),st=targetOf(select);
    return {next,branches:[...select.options].map(o=>({label:(next.innerText||'').trim()+' · '+o.text.trim(),step:{target:nt,select:{target:st,value:o.value}}}))};
  }
  function freeze(node){
    const clone=node.cloneNode(true);
    const a=node.querySelectorAll('input,select,textarea'),b=clone.querySelectorAll('input,select,textarea');
    a.forEach((el,i)=>{const c=b[i];if(!c)return;
      if(el.tagName==='SELECT')[...c.options].forEach((o,j)=>o.toggleAttribute('selected',j===el.selectedIndex));
      else if(el.type==='checkbox'||el.type==='radio')c.toggleAttribute('checked',el.checked);
      else if(el.tagName==='TEXTAREA')c.textContent=el.value;else c.setAttribute('value',el.value);});
    clone.querySelectorAll('script,[data-pa-overlay]').forEach(n=>n.remove());
    // 卡片里点选时，从这一层往下算路径；拼上这一层在真实页面里的选择器，就能对回原元素
    clone.setAttribute('data-pa-layer','');
    let html=clone.outerHTML;
    // 弹窗样式常挂在祖先上（.app #modal.show），副本把祖先链的标签和类带上
    for(let p=node.parentElement;p&&p!==document.body&&p!==document.documentElement;p=p.parentElement){
      const tag=p.tagName.toLowerCase();
      html=`<${tag}${p.id?` id="${p.id}"`:''}${p.className?` class="${String(p.className).replace(/"/g,'&quot;')}"`:''}>${html}</${tag}>`;
    }
    return html;
  }
  // 截图卡片只框住弹窗本体，不要整片遮罩
  function boxOf(L){
    let best=null,bestArea=0;const full=innerWidth*innerHeight;
    for(const el of [L,...L.querySelectorAll('*')].slice(0,400)){
      const r=el.getBoundingClientRect(),area=r.width*r.height;if(area<full*0.03||area>full*0.92)continue;
      // 半透明的是遮罩，不是弹窗本体；只认几乎不透明的底色
      const bg=getComputedStyle(el).backgroundColor,alpha=/rgba\([^)]*,\s*([\d.]+)\)/.exec(bg);if(bg==='transparent'||(alpha&&Number(alpha[1])<0.9))continue;
      if(area>bestArea){best=r;bestArea=area;}
    }
    const r=best||L.getBoundingClientRect();
    return {x:Math.max(0,r.left),y:Math.max(0,r.top),w:Math.min(innerWidth,r.width),h:Math.min(innerHeight,r.height)};
  }
  // 页面现在是哪一屏：路由 + 内容区的标题 + 内容区有哪些按钮。
  // 侧栏、顶栏不算——以前标题里混进了侧栏的「智慧双碳管理」，列表点进详情页认不出页面换了
  function pageSig(){
    const open=layers();
    const inside=el=>vis(el)&&!open.some(l=>l.contains(el))&&!inSkipZone(el)&&!inChrome(el);
    const heads=[...document.querySelectorAll('h1,h2,h3,h4,[class*=page-title],[class*=title],[class*=panel-head]')].filter(inside).slice(0,12).map(el=>(el.innerText||'').trim().split('\n')[0].slice(0,30));
    const btns=[...new Set([...document.querySelectorAll('button,[role=button],.btn')].filter(inside).slice(0,60).map(el=>(el.innerText||'').replace(/\s+/g,' ').trim().slice(0,12)))].sort();
    return location.hash+'|'+heads.join('/')+'|'+btns.join(',');
  }
  function pageTitle(){
    const h=[...document.querySelectorAll('h1,h2,[class*=page-title],[class*=title],[class*=panel-head]')].find(el=>vis(el)&&!inSkipZone(el)&&!inChrome(el)&&!layers().some(l=>l.contains(el))&&(el.innerText||'').trim().length>=2);
    return ((h&&h.innerText)||document.title||'当前页面').trim().split('\n')[0].slice(0,40);
  }
  function stylesOf(){
    const parts=[...document.querySelectorAll('style,link[rel~=stylesheet]')].filter(n=>!n.closest('[data-pa-overlay]')).map(n=>n.tagName==='STYLE'?'<style>'+n.textContent+'</style>':'<link rel="stylesheet" href="'+n.href+'">');
    return {head:parts.join('\n'),base:document.baseURI,html:{class:document.documentElement.className,style:document.documentElement.getAttribute('style')||''},body:{class:document.body.className,style:document.body.getAttribute('style')||''}};
  }
  async function press(step,base){
    const scope=step.inLayer?topOpen(base):document;if(!scope)return false;
    const el=findTarget(step.target,scope);if(!el)return false;
    if(step.select){const s=findTarget(step.select.target,scope);if(!s)return false;s.value=step.select.value;s.dispatchEvent(new Event('input',{bubbles:true}));s.dispatchEvent(new Event('change',{bubbles:true}));await sleep(60);}
    el.click();return true;
  }
  async function waitOpen(before,ms){
    const end=Date.now()+ms;
    while(Date.now()<end){await sleep(50);const L=topOpen(before);if(L){await sleep(140);return topOpen(before)||L;}}
    return null;
  }
  // 页内跳转：点了没弹窗，但页面换了一套内容（列表 → 详情），这是「第二层」
  async function waitChange(before,ms){
    const end=Date.now()+ms;
    while(Date.now()<end){await sleep(60);if(pageSig()!==before){await sleep(220);return true;}}
    return false;
  }
  function subpageOf(){
    const triggers=triggersIn(document,false);
    let html='';try{html=freeze(document.body).replace(/^<body[^>]*>|<\/body>$/g,'');}catch{}
    if(html.length>1500000)html='';
    // 同一种详情页（不同行点进去长得一样）只算一个：按它上面有哪些按钮认
    // 取不到内容区标题时 pageTitle 会退回整站标题，那对子页面没意义，交给宿主用按钮文字
    const t=pageTitle(),site=(document.title||'').trim().split('\n')[0].slice(0,40);
    const nb=navBox(),nr=nb&&nb.getBoundingClientRect();const left=nr&&nr.left<40&&nr.height>innerHeight*0.5?Math.round(nr.right):0;
    return {title:t===site?'':t,html,triggers,box:left?{x:left,y:0,w:innerWidth-left,h:innerHeight}:null,sig:'sub|'+triggers.map(t=>t.text).sort().join(',').slice(0,400)};
  }
  async function closeAll(base){
    for(let i=0;i<5;i++){
      const L=topOpen(base);if(!L)return true;const title=keyOf(L);
      const btn=[...L.querySelectorAll('[data-cx="m-x"],[data-action*="close"],[class*=close],[aria-label*="关闭"],[aria-label*="lose"],button,.btn')].find(b=>vis(b)&&(b.matches('[data-cx="m-x"],[data-action*="close"],[class*=close],[aria-label]')||CLOSE_TEXT.test((b.innerText||'').trim())));
      if(btn)btn.click();else document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
      await sleep(90);
      if(L.isConnected&&shown(L)&&keyOf(L)===title&&topOpen(base)===L){L.classList.remove('show','open','active','visible','in','is-open');await sleep(60);if(topOpen(base)===L)return false;}
    }
    return !topOpen(base);
  }
  // ===== 业务页面导航：按长相和行为认，不依赖原型怎么写 =====
  // 导航区：语义标签 / 类名像菜单的，或者贴着左边的一长条、贴着顶部的一横条；里面能点的短文字最多的那个
  const NAV_SEL='nav,aside,[role=navigation],[class*=sidebar],[class*=side-nav],[class*=sidenav],[class*=menu],[class*=Menu],[class*=nav]';
  const pointer=el=>{try{return getComputedStyle(el).cursor==='pointer'}catch{return false}};
  const ownText=el=>(el.innerText||'').replace(/\s+/g,' ').trim();
  function navItems(box){
    const pool=[...box.querySelectorAll('a,button,li,[role=menuitem],[role=treeitem],[onclick],[class*=item],[class*=Item],div,span')].filter(el=>vis(el)&&(el.matches('a,button,[role=menuitem],[role=treeitem],[onclick]')||pointer(el)));
    const ok=pool.filter(el=>{const t=ownText(el);return t.length>=2&&t.length<=24&&!t.includes(' › ')});
    // 同一个菜单项常常是 li > a > span 三层都能点：留最外层那个文字相同的
    const outer=ok.filter(el=>!ok.some(o=>o!==el&&o.contains(el)&&ownText(o)===ownText(el)));
    // 一个里面装着好几个菜单项的（分组容器）不算菜单项
    const items=outer.filter(el=>!outer.some(o=>o!==el&&el.contains(o)));
    const seen=new Set();return items.filter(el=>{const t=ownText(el);if(seen.has(t))return false;seen.add(t);return true});
  }
  let navCache=null;
  function navBox(){
    if(navCache&&navCache.isConnected&&vis(navCache))return navCache;
    const W=innerWidth,H=innerHeight;
    const cand=new Set([...document.querySelectorAll(NAV_SEL)].filter(vis));
    for(const el of document.body.querySelectorAll('*')){if(!vis(el)||el.closest('[data-pa-overlay]'))continue;const r=el.getBoundingClientRect();
      if((r.left<40&&r.width<W*0.35&&r.height>H*0.55)||(r.top<90&&r.height<130&&r.width>W*0.6))cand.add(el);}
    let best=null,score=2;
    for(const el of cand){if(layers().some(l=>l.contains(el)))continue;const r=el.getBoundingClientRect();if(r.width>W*0.6&&r.height>H*0.6)continue;
      const n=navItems(el).length;if(n>score||(n===score&&best&&best.contains(el))){best=el;score=n;}}
    navCache=best;return best;
  }
  const ACTIVE=/(^|[\s_-])(active|current|selected|is-active|on|checked|router-link-active|router-link-exact-active)($|[\s_-])/i;
  // 当前高亮的菜单项：先认 class / aria，再认「颜色和其他项都不一样」的那一个
  function activeNav(){
    const box=navBox();if(!box)return '';const items=navItems(box);
    const hit=items.find(el=>el.matches('[aria-current]:not([aria-current=false]),[aria-selected=true]')||ACTIVE.test(String(el.className))||ACTIVE.test(String(el.parentElement?.className||'')));
    if(hit)return ownText(hit);
    const look=el=>{const c=getComputedStyle(el);return c.color+'|'+c.backgroundColor+'|'+c.fontWeight};
    const counts={};items.forEach(el=>{const k=look(el);counts[k]=(counts[k]||0)+1});
    const odd=items.filter(el=>counts[look(el)]===1);return odd.length===1?ownText(odd[0]):'';
  }
  // 一页内容的指纹：不含导航区，免得「菜单高亮换了」被当成内容换了
  function contentSig(){const box=navBox();const keep=el=>!(box&&box.contains(el));
    const heads=[...document.querySelectorAll('h1,h2,h3,h4,[class*=title],[class*=head]')].filter(el=>vis(el)&&keep(el)&&!layers().some(l=>l.contains(el))).slice(0,10).map(el=>ownText(el).split(' ')[0].slice(0,24));
    return location.hash+'|'+heads.join('/');}
  async function navTo(route){
    const parts=String(route).replace(/^nav:/,'').split('›').map(s=>s.trim()).filter(Boolean);
    for(const part of parts){const box=navBox();if(!box)return false;const el=navItems(box).find(x=>ownText(x)===part);if(!el)return false;el.click();await sleep(260);}
    return true;
  }
  // 把导航里的每一项点一遍：内容换了 = 一个业务页面；只多出了几个菜单项 = 展开了一个分组，接着点里面的
  async function discoverNav(){
    const box0=navBox();if(!box0)return [];
    const pages=[],seenText=new Set(),seenPage=new Set(),parentOf={};const started=Date.now();
    for(let guard=0;guard<90&&Date.now()-started<40000;guard++){
      const box=navBox();if(!box)break;const items=navItems(box);
      const el=items.find(x=>!seenText.has(ownText(x)));if(!el)break;
      const text=ownText(el);seenText.add(text);
      if(/退出|登出|注销|登录|logout|sign ?out|切换账号|个人中心|消息|通知|帮助|设置$/i.test(text)&&!parentOf[text])continue;   // 账号、消息这类不是业务页面
      const before=contentSig(),hashBefore=location.hash,names=new Set(items.map(ownText));
      el.click();
      let changed=false,grew=false;const end=Date.now()+900;
      while(Date.now()<end){await sleep(70);if(contentSig()!==before){changed=true;await sleep(200);break;}
        const now=navItems(navBox()||box).map(ownText);if(now.some(t=>!names.has(t))){grew=true;now.filter(t=>!names.has(t)).forEach(t=>{parentOf[t]=text});await sleep(120);break;}}
      if(grew&&!changed)continue;
      if(!changed&&!(location.hash!==hashBefore))continue;
      const key=location.hash||contentSig();if(seenPage.has(key))continue;seenPage.add(key);
      pages.push({hash:location.hash,text,parent:parentOf[text]||'',title:text.replace(/^[^\p{L}\p{N}]+/u,'').trim()||text});   // 菜单前面的图标字符（▦ ◈）不进标题
      await closeAll(snapshot());
    }
    // 地址各不相同就用地址当路由；有的页面地址一样（纯脚本切页），这些用「分组›菜单项」
    const hashes=pages.map(p=>p.hash);
    return pages.map(p=>({hash:p.hash&&hashes.filter(h=>h===p.hash).length===1?p.hash:'nav:'+(p.parent?p.parent+'›':'')+p.text,title:p.title}));
  }
  // 内容区的几个标题（不含导航、弹窗、固定外壳）：用来判断「换了一页」还是「只是筛选 / 切了个状态」
  function mainHeads(){const box=navBox();return [...document.querySelectorAll('h1,h2,h3,h4,[class*=page-title],[class*=title],[class*=panel-head],[class*=card-head]')].filter(el=>vis(el)&&!(box&&box.contains(el))&&!inChrome(el)&&!layers().some(l=>l.contains(el))).slice(0,10).map(el=>ownText(el).split(' ')[0].slice(0,24)).filter(Boolean)}
  function headsMoved(a,b){if(!a.length||!b.length)return a.length!==b.length;if(a[0]!==b[0])return true;const s=new Set(a);return b.filter(x=>s.has(x)).length/Math.max(a.length,b.length)<0.5}
  // 内容区里的页签条（巡检计划 / 路线配置 / 巡检点）：每个页签是同一个业务页面的一个视图，里面的弹窗也要找
  const TAB_BAR=/(^|[\s_-])(tabs?|tab-?bar|tab-?nav|tab-?list|nav-tabs|tab-?header|tabs-nav)($|[\s_-])/i;
  function tabsIn(){
    const box=navBox(),out=[];
    const bars=[...document.querySelectorAll('[role=tablist],[class*=tab],[class*=Tab]')].filter(el=>vis(el)&&(el.matches('[role=tablist]')||TAB_BAR.test(String(el.className)))&&!(box&&box.contains(el))&&!inChrome(el)&&!layers().some(l=>l.contains(el)));
    for(const bar of bars.filter(b=>!bars.some(o=>o!==b&&o.contains(b)))){
      const items=navItems(bar).filter(el=>ownText(el).length<=12);if(items.length<2||items.length>8)continue;
      const act=items.find(el=>el.matches('[aria-selected=true]')||ACTIVE.test(String(el.className))||ACTIVE.test(String(el.parentElement?.className||'')))||items[0];
      for(const el of items)if(el!==act)out.push({...targetOf(el),text:ownText(el)});
      if(out.length>=12)break;
    }
    return out;
  }
  let knownRoutes=[];   // 宿主告诉副本：这个原型有哪些业务页面（跳到这些页面不算这一页的下一层）
  // 原型里有哪些页面：导航里指向 #路由 的链接。折叠起来的分组里的链接也算（不要求看得见）
  function routesOf(){
    const seen=new Set(),out=[];
    for(const a of document.querySelectorAll('a[href^="#"]')){
      const h=a.getAttribute('href')||'';if(h.length<2||seen.has(h))continue;
      if(!inSkipZone(a)&&!inChrome(a))continue;
      seen.add(h);out.push({hash:h,title:(a.textContent||'').replace(/\s+/g,' ').trim().slice(0,30)||h});
      if(out.length>=60)break;
    }
    return out;
  }
  let probeBase=null,probeSig='';
  async function probeInit(full){
    await sleep(50);probeBase=snapshot();probeSig=pageSig();
    if(!full)return {sig:probeSig};
    let page='';try{page=freeze(document.body).replace(/^<body[^>]*>|<\/body>$/g,'');}catch{}
    if(page.length>1500000)page='';
    return {sig:probeSig,title:pageTitle(),styles:stylesOf(),page,width:innerWidth,height:innerHeight,triggers:triggersIn(document,false),tabs:tabsIn()};
  }
  async function probeTry(path,step){
    if(!await closeAll(probeBase)||pageSig()!==probeSig)return {needReload:true};
    for(const s of path){
      if(s.nav){const was=pageSig();if(!await press(s,probeBase))return {ok:false,reason:'replay'};if(!await waitChange(was,1500))return {ok:false,reason:'replay'};continue;}
      const before=snapshot();if(!await press(s,probeBase))return {ok:false,reason:'replay'};if(!await waitOpen(before,1200))return {ok:false,reason:'replay'};
    }
    const before=snapshot(),sigBefore=pageSig(),hashBefore=location.hash,navBefore=activeNav(),headsBefore=mainHeads();
    if(!await press(step,probeBase))return {ok:false,reason:'missing'};
    const L=await waitOpen(before,step.select?900:520);
    let out={ok:true,opened:null};
    // 没弹窗、但页面整个换了：记成子页面，它上面的按钮接着往下找。
    // 换了路由也算（「配置单元/设备」跳到 #boundary-device），只要跳去的不是侧栏里另一张业务页面——那张自己会展开
    const known=[...knownRoutes,...routesOf().map(r=>r.hash)];
    if(!L&&!step.inLayer&&(pageSig()!==sigBefore||await waitChange(sigBefore,250))){
      const navNow=activeNav();
      // 跳去了别的业务页面：地址是清单里的另一页，或者左侧菜单的高亮换了。不挂进这一页的树，只记一条「能跳到哪」
      const jumped=(location.hash!==hashBefore&&known.includes(location.hash))||(navBefore&&navNow&&navNow!==navBefore);
      if(jumped)out.jump={hash:location.hash,nav:navNow,title:navNow||pageTitle()};
      // 页签：点了就是这一页的另一个视图
      else if(step.tab){out.subpage={...subpageOf(),title:step.target.text,tab:true};}
      // 真换了一页（地址变了，或内容区的标题换了一套）才算子页面；只是筛选、切个开关、表格换了几行，不算一层
      else if(location.hash!==hashBefore||headsMoved(headsBefore,mainHeads()))out.subpage=subpageOf();
    }
    if(L){
      const wizard=wizardOf(L);
      out.opened={layerSel:selectorFor(L),title:titleOf(L),sig:titleOf(L)+'|'+(L.innerText||'').replace(/\s+/g,' ').slice(0,160),html:freeze(L),box:boxOf(L),
        triggers:triggersIn(L,true,wizard.next?[wizard.next]:[]),branches:wizard.branches};
    }
    const closed=await closeAll(probeBase);
    out.pageChanged=!closed||pageSig()!==probeSig;
    return out;
  }
  async function replay(path){
    const prev=mode;mode='interact';const base=snapshot();let title='',at=-1;
    try{for(let i=0;i<path.length;i++){
      if(path[i].nav){const was=pageSig();if(!await press(path[i],base)||!await waitChange(was,2000)){at=i;break;}title=pageTitle();continue;}
      const before=snapshot();if(!await press(path[i],base)){at=i;break;}const L=await waitOpen(before,1600);if(!L){at=i;break;}title=titleOf(L);}}
    finally{mode=prev;paint();}
    return {ok:at<0,title,at};
  }

  window.addEventListener('message',e=>{
    if(e.source!==parent)return;const m=e.data||{};
    if(m.type==='PA_ROUTE'){if(typeof m.hash==='string'){if(m.hash.startsWith('nav:'))navTo(m.hash);else if(location.hash!==m.hash)location.hash=m.hash;}return;}
    if(m.type==='PA_PROBE_ROUTES'){send('PROBE_REPLY',{id:m.id,routes:routesOf(),current:location.hash});return;}
    if(m.type==='PA_PROBE_NAV'){discoverNav().then(routes=>send('PROBE_REPLY',{id:m.id,routes,current:location.hash}),()=>send('PROBE_REPLY',{id:m.id,routes:[]}));return;}
    if(m.type==='PA_PROBE_INIT'){if(Array.isArray(m.routes))knownRoutes=m.routes;probeInit(!!m.full).then(r=>send('PROBE_REPLY',{id:m.id,...r}),err=>send('PROBE_REPLY',{id:m.id,ok:false,error:String(err)}));return;}
    if(m.type==='PA_PROBE_TRY'){probeTry(m.path||[],m.step).then(r=>send('PROBE_REPLY',{id:m.id,...r}),err=>send('PROBE_REPLY',{id:m.id,ok:false,error:String(err),needReload:true}));return;}
    if(m.type==='PA_REPLAY'){replay(m.path||[]).then(r=>send('REPLAYED',r),()=>send('REPLAYED',{ok:false,at:0}));return;}
    if(m.type==='PA_SET_MODE'){mode=m.mode;hover=null;dragStart=null;if(m.mode==='interact')picked=[];if(dragBox)dragBox.style.display='none';paint();}
    if(m.type==='PA_SELECT'){
      if(!m.selector&&dragBox)dragBox.style.display='none';
      try{const one=m.selector?document.querySelector(m.selector):null;
        picked=one?[one]:[];
        if(one)send('SELECTED',{...describe(one),refresh:true});else if(m.selector)send('SELECTION_MISSING');
        paint();}catch{}
    }
    if(m.type==='PA_RENDER_MARKERS'){
      markers.forEach(m=>m.pin.remove());markers=[];
      (m.annotations||[]).forEach((a,i)=>{try{const el=document.querySelector(a.selector);if(!el)return;const pin=overlay('2px solid white');pin.textContent=i+1;Object.assign(pin.style,{width:'22px',height:'22px',borderRadius:'50%',background:'#b8532f',color:'white',font:'11px system-ui',placeItems:'center'});markers.push({el,pin});}catch{}});paint();
    }
    if(m.type==='PA_BOX_RECT')selectRegion(m.bounds);
    if(m.type==='PA_HIGHLIGHT')highlight(m.targets);
    if(m.type==='PA_SCROLL'){
      let el=document.elementFromPoint(m.x,m.y);
      while(el&&el!==document.body){const cs=getComputedStyle(el);if(/auto|scroll/.test(cs.overflowY)&&el.scrollHeight>el.clientHeight){el.scrollTop+=m.deltaY;el.scrollLeft+=m.deltaX;return;}el=el.parentElement;}
      window.scrollBy(m.deltaX,m.deltaY);paint();
    }
    if(m.type==='PA_PREVIEW'){
      try{
        if(m.prop.startsWith('--'))document.documentElement.style.setProperty(m.prop,m.value);
        else {const target=document.querySelector(m.selector);if(!target)return;if(m.prop==='text')target.textContent=m.value;else target.style.setProperty(m.prop,m.value,'important');}
        paint();
      }catch{}
    }
  });
  window.addEventListener('DOMContentLoaded',()=>{
    box=overlay('1px solid #b8532f');caption=overlay('0');
    Object.assign(caption.style,{background:'#b8532f',color:'#fff',font:'11px/20px system-ui',padding:'1px 6px',borderRadius:'3px'});
    restoreScroll();send('READY');send('WIDTH',{width:innerWidth});
  });
  window.addEventListener('load',async()=>{
    // 菜单不改地址的原型（纯脚本切页）：路由记成「nav:分组›菜单项」，载入后照着点过去再报已载入
    const r=String(window.__paRoute||'');if(r.startsWith('nav:')){await sleep(250);try{await navTo(r);}catch{}}
    restoreScroll();send('LOADED');});
})();
</script>
'''


def build_bridge(project_id, page_id):
    return _TEMPLATE.replace('__CFG__', json.dumps({'projectId':project_id,'pageId':page_id}))
