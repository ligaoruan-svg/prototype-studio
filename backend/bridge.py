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
  // 后台副本放在屏幕外，浏览器会把屏幕外 iframe 的动画冻住：淡入的弹窗永远停在第一帧（透明度 0），
  // 看起来就像「点了没反应」。副本里把动画、过渡都改成瞬间完成（只在副本里，预览不受影响）
  if(PROBE){const calm=()=>{if(document.querySelector('style[data-pa-calm]'))return;const s=document.createElement('style');s.setAttribute('data-pa-overlay','');s.setAttribute('data-pa-calm','');s.textContent='*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;transition-duration:0s!important;transition-delay:0s!important}';(document.head||document.documentElement).appendChild(s);};calm();document.addEventListener('DOMContentLoaded',calm);}
  const esc = value => CSS.escape(String(value));
  const scrollContainers = new Set(); let scrollTimer, restoringScroll=false;
  // Opaque sandbox origins cannot use native localStorage. Keep demo data scoped
  // to this project/page; only the trusted host persists it after receiving events.
  // localStorage 记到宿主那边（刷新还在）；sessionStorage 只在这一次打开里有效，不往外存。
  // 用 Proxy 包一层：原型里常写 localStorage.token = 'x' / localStorage.token，也要能存能取
  function makeStore(data,persist){
    const save=()=>{if(persist)send('STORAGE',{data});};
    const api={getItem:k=>Object.hasOwn(data,String(k))?data[String(k)]:null,
      setItem:(k,v)=>{data[String(k)]=String(v);save();},
      removeItem:k=>{delete data[String(k)];save();},
      clear:()=>{Object.keys(data).forEach(k=>delete data[k]);save();},
      key:i=>Object.keys(data)[i]??null, get length(){return Object.keys(data).length;}};
    return new Proxy(api,{
      get:(t,k)=>k in t||typeof k!=='string'?t[k]:(Object.hasOwn(data,k)?data[k]:undefined),
      set:(t,k,v)=>{if(typeof k==='string'&&!(k in t))api.setItem(k,v);return true;},
      deleteProperty:(t,k)=>{api.removeItem(k);return true;},
      has:(t,k)=>k in t||Object.hasOwn(data,k),
      ownKeys:()=>Object.keys(data),
      getOwnPropertyDescriptor:(t,k)=>Object.hasOwn(data,k)?{value:data[k],enumerable:true,configurable:true,writable:true}:undefined});
  }
  const store=makeStore({...(window.__paStorageSeed || {})},true);
  try { Object.defineProperty(window,'localStorage',{value:store}); Object.defineProperty(window,'sessionStorage',{value:makeStore({},false)}); } catch {}
  if(window.__paRoute&&String(window.__paRoute).startsWith('#')) location.hash=window.__paRoute;
  window.addEventListener('hashchange',()=>send('ROUTE',{hash:location.hash}));
  // 报错既发给宿主，也记在这里：用户点了某个按钮之后冒出来的报错，要跟着那次点击一起交给 AI
  const recentErrors=[];
  const noteError=message=>{recentErrors.push({at:Date.now(),message:String(message).slice(0,300)});if(recentErrors.length>20)recentErrors.shift();};
  window.addEventListener('error',e=>{if(e.message){noteError(e.message);send('RUNTIME_ERROR',{message:e.message,lineno:e.lineno});}});
  window.addEventListener('unhandledrejection',e=>{const m=String(e.reason?.message||e.reason||'Promise rejection');noteError(m);send('RUNTIME_ERROR',{message:m});});
  const originalError=console.error;
  // 包一层把报错交给宿主；这一层自己绝不能抛错（Object.create(null) 转字符串会抛），循环里狂打日志时也别刷屏
  let lastErrorSent=0;
  console.error=(...args)=>{
    try{const m=args.map(x=>{try{return String(x?.message||x);}catch{return Object.prototype.toString.call(x);}}).join(' ').slice(0,1200);
      noteError(m);const now=Date.now();if(now-lastErrorSent>200){lastErrorSent=now;send('RUNTIME_ERROR',{message:m});}}catch{}
    originalError.apply(console,args);};

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
  // 脚本生成的元素在源码里找不到对应的标签，没法按位置改；改样式就按「同类元素」写一条 CSS 规则：
  // 从它往上找到第一个带类名的祖先，拼成 .metric > div:nth-of-type(2) 这样的选择器，页面上同类的一起变
  const STATE_CLASS=/^(active|on|current|selected|show|open|hover|focus|disabled|checked|is-|has-|pa-)/i;
  function stableClasses(el){return [...(el.classList||[])].filter(c=>/^[a-zA-Z_][\w-]*$/.test(c)&&!STATE_CLASS.test(c)&&!/\d{3,}/.test(c)).slice(0,2);}
  function partOf(el){
    const tag=el.tagName.toLowerCase(),cls=stableClasses(el);
    if(cls.length)return tag+cls.map(c=>'.'+c).join('');
    const p=el.parentElement,same=p?[...p.children].filter(c=>c.tagName===el.tagName):[];
    return tag+(same.length>1?':nth-of-type('+(same.indexOf(el)+1)+')':'');
  }
  function styleSelectorFor(el){
    try{
      let sel=partOf(el),node=el;
      if(stableClasses(el).length){
        const anchor=el.parentElement?.closest('[class]');
        if(anchor&&anchor!==document.body&&stableClasses(anchor).length)sel=partOf(anchor)+' '+sel;
      }else{
        for(let i=0;i<4;i++){const p=node.parentElement;if(!p||p===document.body||p===document.documentElement)break;sel=partOf(p)+' > '+sel;node=p;if(stableClasses(p).length)break;}
      }
      const all=[...document.querySelectorAll(sel)].filter(n=>!n.closest('[data-pa-overlay]'));
      return all.includes(el)?{styleSel:sel,styleCount:all.length}:{};
    }catch{return {};}
  }
  function describe(el){
    const cs=getComputedStyle(el);
    return {selector:selectorFor(el),...styleSelectorFor(el),leaf:!el.children.length,pid:el.dataset.pid||'',tag:el.tagName.toLowerCase(),
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
    if(mode==='box'||swallowClick){e.preventDefault();e.stopImmediatePropagation();swallowClick=false;return;}   // 刚拖完框，这一下 click 不算点选
    if(mode==='select'){
      e.preventDefault();e.stopImmediatePropagation();hover=null;if(dragBox)dragBox.style.display='none';
      if(strokes.length){clearInk();send('DRAWING',{count:0});}   // 画了没发又去点别的：这次画的作废，改成点选
      if(e.shiftKey||e.metaKey||e.ctrlKey){
        const at=picked.indexOf(el);
        if(at>=0)picked.splice(at,1);else if(picked.length<16)picked.push(el);
      }else picked=[el];
      paint();reportPicks();return;
    }
    if(e.isTrusted)traceClick(el);
    const link=el.closest('a[href]');const href=link?.getAttribute('href')||'';
    if(href.startsWith('#')){
      // 预览里有 <base>，不拦的话 #xxx 会被当成跳到资源目录。但要等原型自己的处理先跑完再决定：
      // 原型自己 preventDefault 了（Bootstrap 页签、#xxx 打开弹窗）就不替它改地址；href="#" 本来就只是占位
      e.preventDefault();
      let pagePrevented=false;
      try{e.preventDefault=()=>{pagePrevented=true;};}catch{}
      setTimeout(()=>{if(!pagePrevented&&href.length>1&&href!=='#!'&&location.hash!==href)location.hash=href;},0);
      return;
    }
    if(/\.html?(?:[?#].*)?$/i.test(href) && !/^(?:https?:)?\/\//i.test(href)){e.preventDefault();send('NAVIGATE',{href});}
  },true);
  // 交互模式下用户真点的每一下：点了什么、点完地址变没变、内容变没变、有没有弹窗、有没有报错。
  // 用户说「点了没反应」时，AI 不用在几千行源码里猜是哪个按钮
  function quickSig(){const t=(document.body&&document.body.innerText)||'';let h=0;for(let i=0;i<t.length;i+=5)h=(h*31+t.charCodeAt(i))|0;return t.length+':'+h;}
  function traceClick(el){
    if(el.closest('[data-pa-overlay]'))return;
    const target=el.closest('button,a,[role=button],[role=tab],[role=menuitem],[onclick],[data-action],li,td,label,input,select,summary')||el;
    // 输入框只报它是哪个框（提示文字 / 名字），不报里面填了什么：用户可能在原型里随手填了真实信息
    const field=/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
    const label=((field?(target.getAttribute('aria-label')||target.placeholder||target.name||''):(target.innerText||target.getAttribute('aria-label')||target.title||'')).replace(/\s+/g,' ').trim()||target.tagName.toLowerCase()).slice(0,40);
    let selector='';try{selector=selectorFor(target);}catch{}
    const at=Date.now(),hashBefore=location.hash,sigBefore=quickSig(),layersBefore=layers().length;
    setTimeout(()=>{
      const errors=recentErrors.filter(x=>x.at>=at).map(x=>x.message).slice(0,3);
      send('CLICK_TRACE',{label,selector,tag:target.tagName.toLowerCase(),hashBefore,hashAfter:location.hash,
        changed:quickSig()!==sigBefore,opened:layers().length>layersBefore,errors,at});
    },700);
  }
  // 点选模式里：点一下选一个，拖一下框一片（拉框并进了点选，不再单独一个模式）。
  // 按下时先记起点，移动超过 6px 才算拖；没拖就照常当点击处理
  let dragging=false,swallowClick=false,dragEnabled=true;   // 拖框只在评论里有；编辑里拖一下什么都不做
  for(const type of ['pointerdown','mousedown'])window.addEventListener(type,e=>{if(mode==='select'){dragDown(e);e.preventDefault();e.stopImmediatePropagation();}},true);
  // ===== 评论里的画笔：在页面上直接画圈、划线（参照 Claude Design）=====
  // 笔迹按页面坐标存（滚动后还在原处），画在一层不挡点击的 SVG 上；每画完一笔，
  // 把笔迹圈到的元素报给宿主（AI 拿它定位源码），截图在发送时再拍
  let strokes=[],redoStrokes=[],current=null,inkLayer=null;
  function ink(){
    if(inkLayer)return inkLayer;
    inkLayer=document.createElementNS('http://www.w3.org/2000/svg','svg');inkLayer.dataset.paOverlay='1';
    Object.assign(inkLayer.style,{position:'fixed',left:'0',top:'0',width:'100vw',height:'100vh',pointerEvents:'none',zIndex:'2147483645',overflow:'visible'});
    document.documentElement.appendChild(inkLayer);return inkLayer;
  }
  function drawInk(){
    if(!strokes.length&&!current){if(inkLayer)inkLayer.innerHTML='';return;}
    const all=current?[...strokes,current]:strokes,dx=scrollX,dy=scrollY;
    ink().innerHTML=all.map(st=>'<polyline fill="none" stroke="#e5383b" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" points="'+st.map(p=>(p.x-dx).toFixed(1)+','+(p.y-dy).toFixed(1)).join(' ')+'"/>').join('');
  }
  window.addEventListener('scroll',()=>{if(strokes.length||current)drawInk();},true);
  function strokeRect(st){const xs=st.map(p=>p.x-scrollX),ys=st.map(p=>p.y-scrollY);return {left:Math.min(...xs),top:Math.min(...ys),right:Math.max(...xs),bottom:Math.max(...ys)};}
  function reportInk(){
    if(!strokes.length){send('DRAWING',{count:0});return;}
    // 每一笔：圈住的范围里露在最前面的元素，加上笔迹直接压过的元素
    const seen=new Set(),nodes=[];
    const add=el=>{if(el&&el!==document.body&&el!==document.documentElement&&!el.closest('[data-pa-overlay]')&&!seen.has(el)){seen.add(el);nodes.push(el);}};
    for(const st of strokes){
      const r=strokeRect(st);
      // 画的是一个圈：取圈里面的；画的是一道线（下划线、删除线）：取线压过的。圈的边线常常压到旁边的东西，不能算
      if(r.right-r.left>24&&r.bottom-r.top>24)findInRect(r).forEach(add);
      else for(let k=0;k<st.length;k+=3){const p=st[k];add(document.elementFromPoint(p.x-scrollX,p.y-scrollY));}
    }
    if(!nodes.length&&strokes.length){const r=strokeRect(strokes[strokes.length-1]);add(document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2));}
    const kept=nodes.filter((el,_,all)=>!all.some(n=>n!==el&&el.contains(n))).slice(0,16);
    const box=strokes.map(strokeRect).reduce((a,b)=>({left:Math.min(a.left,b.left),top:Math.min(a.top,b.top),right:Math.max(a.right,b.right),bottom:Math.max(a.bottom,b.bottom)}));
    let ancestor=kept[0];while(ancestor&&kept.some(n=>!ancestor.contains(n)))ancestor=ancestor.parentElement;
    const targets=kept.map(describe);
    send('DRAWING',{...describe(ancestor||document.body),kind:'region',drawing:true,count:strokes.length,redo:redoStrokes.length,
      text:targets.map(n=>n.text||n.tag).join(' · ').slice(0,500),targets,bounds:box});
  }
  // 截图：把当前页面（含打开的弹窗、填的值）连同样式放进 SVG foreignObject 画到 canvas，再叠上笔迹。
  // 不依赖外部库；外链图片画不出来（浏览器不让），原型里大多是 CSS 画的，够用来标位置
  async function shoot(pad=60,maxW=1100){
    const W=innerWidth,H=innerHeight;
    const box=strokes.length?strokes.map(strokeRect).reduce((a,b)=>({left:Math.min(a.left,b.left),top:Math.min(a.top,b.top),right:Math.max(a.right,b.right),bottom:Math.max(a.bottom,b.bottom)})):{left:0,top:0,right:W,bottom:H};
    const x0=Math.max(0,Math.floor(box.left-pad)),y0=Math.max(0,Math.floor(box.top-pad)),x1=Math.min(W,Math.ceil(box.right+pad)),y1=Math.min(H,Math.ceil(box.bottom+pad));
    const css=[...document.querySelectorAll('style')].filter(n=>!n.closest('[data-pa-overlay]')&&!n.hasAttribute('data-pa-calm')).map(n=>n.textContent).join('\n');
    const rootCs=getComputedStyle(document.documentElement),vars=[];for(const k of rootCs)if(k.startsWith('--'))vars.push(k+':'+rootCs.getPropertyValue(k));
    const clone=document.body.cloneNode(true);
    clone.querySelectorAll('script,[data-pa-overlay],iframe,video,canvas').forEach(n=>n.remove());
    // 输入框里填的、下拉选的值写回属性，克隆出来才看得见
    const src=[...document.body.querySelectorAll('input,select,textarea')],dst=[...clone.querySelectorAll('input,select,textarea')];
    src.forEach((el,k)=>{const c=dst[k];if(!c)return;if(el.tagName==='SELECT'){[...c.options].forEach((o,m)=>{if(m===el.selectedIndex)o.setAttribute('selected','');else o.removeAttribute('selected');});}else if(el.type==='checkbox'||el.type==='radio'){if(el.checked)c.setAttribute('checked','');else c.removeAttribute('checked');}else if(el.tagName==='TEXTAREA')c.textContent=el.value;else c.setAttribute('value',el.value);});
    const bodyCs=getComputedStyle(document.body);
    const xhtml='<div xmlns="http://www.w3.org/1999/xhtml" style="'+vars.join(';').replace(/"/g,"'")+';width:'+W+'px;height:'+H+'px;overflow:hidden;position:relative;background:'+bodyCs.backgroundColor+'"><style>'+css.replace(/:root\b/g,'.pa-shot-root').replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</style><div class="pa-shot-root '+(document.documentElement.className||'')+'" style="position:absolute;left:'+(-scrollX)+'px;top:'+(-scrollY)+'px;width:'+document.documentElement.scrollWidth+'px">'+new XMLSerializer().serializeToString(clone)+'</div></div>';
    const svg='<svg xmlns="http://www.w3.org/2000/svg" width="'+W+'" height="'+H+'"><foreignObject width="100%" height="100%">'+xhtml+'</foreignObject></svg>';
    const img=new Image();img.decoding='sync';
    await new Promise((ok,bad)=>{img.onload=ok;img.onerror=()=>bad(new Error('截图失败'));img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);});
    const scale=Math.min(1,maxW/(x1-x0));
    const cv=document.createElement('canvas');cv.width=Math.round((x1-x0)*scale);cv.height=Math.round((y1-y0)*scale);
    const ctx=cv.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,cv.width,cv.height);
    ctx.drawImage(img,x0,y0,x1-x0,y1-y0,0,0,cv.width,cv.height);
    ctx.strokeStyle='#e5383b';ctx.lineWidth=3.5*Math.max(scale,.6);ctx.lineCap='round';ctx.lineJoin='round';
    for(const st of strokes){ctx.beginPath();st.forEach((p,k)=>{const x=(p.x-scrollX-x0)*scale,y=(p.y-scrollY-y0)*scale;k?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();}
    const big=cv.toDataURL('image/jpeg',.85);
    const t=document.createElement('canvas'),ts=Math.min(1,320/cv.width);t.width=Math.round(cv.width*ts);t.height=Math.round(cv.height*ts);
    t.getContext('2d').drawImage(cv,0,0,t.width,t.height);
    return {data_url:big,thumb:t.toDataURL('image/jpeg',.7),width:cv.width,height:cv.height};
  }
  function clearInk(){strokes=[];redoStrokes=[];current=null;drawInk();}
  function dragDown(e){
    if((mode!=='box'&&mode!=='select')||(mode==='select'&&!dragEnabled)||e.button!==0||e.target?.closest?.('[data-pa-overlay]'))return;e.preventDefault();e.stopImmediatePropagation();
    if(dragStart)return;
    dragStart={x:e.clientX,y:e.clientY};dragging=false;current=null;
  }
  function dragMove(e){
    if(!dragStart)return;
    if(!dragging){if(Math.abs(e.clientX-dragStart.x)+Math.abs(e.clientY-dragStart.y)<6)return;dragging=true;hover=null;paint();current=[{x:dragStart.x+scrollX,y:dragStart.y+scrollY}];}
    e.preventDefault();e.stopImmediatePropagation();
    const last=current[current.length-1],x=e.clientX+scrollX,y=e.clientY+scrollY;
    if(Math.abs(last.x-x)+Math.abs(last.y-y)>=2){current.push({x,y});drawInk();}
  }
  function dragUp(e){
    if(!dragStart)return;dragStart=null;
    if(!dragging)return;   // 没拖动：交给 click 当点选
    dragging=false;e.preventDefault();e.stopImmediatePropagation();swallowClick=true;setTimeout(()=>{swallowClick=false;},0);
    if(current&&current.length>2){strokes.push(current);redoStrokes=[];}
    current=null;drawInk();reportInk();
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
  // 候选：常见的可见元素，加上自己直接带字的（AI 生成的页面里文字多半直接写在 div 里）
  const hasOwnText=el=>[...el.childNodes].some(n=>n.nodeType===3&&n.textContent.trim());
  function inRect(r){
    return [...document.body.querySelectorAll('*')].filter(el=>!el.closest('[data-pa-overlay]')&&(el.matches('button,a,input,select,textarea,h1,h2,h3,h4,p,label,th,td,span,li,img,svg')||hasOwnText(el))).filter(el=>{
      const b=el.getBoundingClientRect(),x=b.left+b.width/2,y=b.top+b.height/2;
      return b.width>0&&b.height>0&&x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom;
    });
  }
  function findInRect(r){
    return inRect(r).filter(el=>{const b=el.getBoundingClientRect();return visibleAt(el,b.left+b.width/2,b.top+b.height/2);})
      .filter((el,_,all)=>!all.some(n=>n!==el&&el.contains(n))).slice(0,16);
  }
  function selectRegion(r){
    const inBox=inRect(r);
    const nodes=findInRect(r);
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
  window.addEventListener('keydown',e=>{if(!e.isTrusted||e.target?.isContentEditable||e.target?.closest?.('input,textarea,select'))return;const key=e.key.toLowerCase(),command=e.metaKey||e.ctrlKey;if((!command&&!e.altKey&&['h','c','v','b','p','e','escape'].includes(key))||(command&&['z','/','enter'].includes(key))){e.preventDefault();send('SHORTCUT',{key:e.key,metaKey:e.metaKey,ctrlKey:e.ctrlKey,altKey:e.altKey,shiftKey:e.shiftKey});}},true);
  // ===== 展开：找出这一页能打开的所有弹窗 =====
  // 原型里的弹窗大多是 JS 现拼的，源码里搜不到、预览里要点好几层才看得见。
  // 这里在一个后台副本里把按钮挨个点一遍：点完多出来一层遮罩，就是它打开的弹窗；
  // 再顺着弹窗里的按钮（下一步、新排放源……）往下点，整条链就出来了。
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const LAYER_SEL='[role=dialog],[aria-modal=true],dialog,[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog],[class*=drawer],[class*=popup],[class*=mask],[class*=overlay]';
  const LAYER_NAME=/modal|dialog|drawer|popup|mask|overlay|layer/i;
  const CLICKABLE='button,a[href],[data-action],[data-cx],[onclick],[role=button],.btn,[class*=btn]';
  const REAL_CONTROL='button,a[href],[role=button],input[type=button],input[type=submit]';
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
  const COMMIT_TEXT=/^(保存|确定|确认|提交|完成|删除|移除|确认删除|启用|停用|发布|撤回|通过|驳回|发起|派发|下发|生成)$/;
  const NOISE_TEXT=/^(查询|搜索|重置|刷新|导出.*|下载.*|全屏|退出.*|打印|返回.*|收起|展开|更多|上一页|下一页)$/;
  const WIZARD_TEXT=/^(下一步|继续|下一页|next)/i;
  // vis：按钮、下拉这种小东西看得见就行；shown：够大才算得上一层弹窗
  function vis(el){
    if(!el?.isConnected)return false;const cs=getComputedStyle(el);
    if(cs.display==='none'||cs.visibility==='hidden')return false;
    // 透明度 0 但正在播淡入动画的，算看得见（动画被冻住时会一直停在 0）
    if(Number(cs.opacity)===0&&!(el.getAnimations?.()||[]).some(a=>a.playState==='running'||a.playState==='pending'))return false;
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
    // 表格里固定在右边的「操作」列也是 sticky，但它属于这一页的内容，不是外壳
    for(let n=el.parentElement;n&&n!==document.body;n=n.parentElement){if(n.closest('table'))continue;const p=getComputedStyle(n).position;if(p==='fixed'||p==='sticky')return true;}
    return false;
  }
  const bare=el=>(el.innerText||el.value||'').replace(/\s+/g,' ').trim().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu,'');
  // skips：没试的按钮按原因记一笔（只记页面这一层），展开完能看到「跳过了哪些、为什么」，漏了一眼就知道
  // 关闭按钮：「×」这种字会被 bare() 去掉，只看字认不出来；再看提示文字、id 和常见的 dismiss 标记
  function isCloser(el){
    const t=(el.innerText||el.value||'').trim(),a=(el.getAttribute('aria-label')||el.getAttribute('title')||'').trim();
    return /^[×✕✖╳xX]$/.test(t)||/^(关闭|取消|返回|close)$/i.test(a)||/(^|[-_])close([-_A-Z]|$)|Close([-_A-Z]|$)/.test(el.id||'')||el.matches('[data-dismiss],[data-bs-dismiss],[data-layer-close]');
  }
  function inTabBar(el){for(let p=el.parentElement;p&&p!==document.body;p=p.parentElement)if(TAB_BAR.test(String(p.className)))return true;return false;}
  function triggersIn(scope,inLayer,skip,skips){
    const seen=new Set(),groups={},out=[],open=inLayer?[]:layers();
    const note=(reason,el,name)=>{if(!skips)return;const r=skips[reason]||(skips[reason]={n:0,labels:[]});r.n++;const t=(name||bare(el)||labelOf(el)).slice(0,16);if(t&&r.labels.length<12&&!r.labels.includes(t))r.labels.push(t)};
    for(const el of scope.querySelectorAll(CLICKABLE)){
      if(!vis(el)||el.disabled||el.closest('[data-pa-overlay]'))continue;
      if(!inLayer&&open.some(l=>l.contains(el)))continue;
      // 菜单（业务页面另算）、页签（tabsIn 另算）不记；分页条算「查询 / 翻页这类」；别的（面包屑等）记成菜单
      if(!inLayer&&inSkipZone(el)){if(el.closest('[class*=pag],[class*=Pag]'))note('noise',el,'翻页');else if(!(navBox()&&navBox().contains(el))&&!el.closest('[role=tab],[role=tablist]')&&!inTabBar(el))note('nav',el);continue;}
      if(!inLayer&&inChrome(el)){note('chrome',el);continue;}
      // 外层是真按钮（button 里的 span）才把里面的让给它；外层只是 .btn-group、.op-btns 这种容器时，点里面的按钮。
      // 容器自己（没有自己的点击处理）也不当按钮点——以前点的是「编辑 删除」整排，什么都打不开
      const outer=el.parentElement?.closest(CLICKABLE);if(outer&&scope.contains(outer)&&outer.matches(REAL_CONTROL))continue;
      if(!el.matches(REAL_CONTROL)&&!el.matches('[onclick],[data-action],[data-cx]')&&el.querySelector(REAL_CONTROL))continue;
      const raw=bare(el);
      if(CLOSE_TEXT.test(raw)||isCloser(el))continue;
      if(COMMIT_TEXT.test(raw)){note('commit',el);continue;}
      if(NOISE_TEXT.test(raw)){note('noise',el);continue;}
      if(out.length>=40){note('limit',el);continue;}
      if(el.matches('[class*=close]')||(skip&&skip.includes(el)))continue;
      const href=el.getAttribute('href')||'';
      if(el.tagName==='A'&&!el.matches('[data-action],[data-cx],[onclick]')&&(href.startsWith('#')||/\.html?(?:[?#].*)?$/i.test(href)||/^(?:https?:)?\/\//i.test(href)))continue;
      const t=targetOf(el);if(!t.text)continue;
      const group=t.attr?t.attr+'='+t.value.replace(/\d+/g,'#'):t.tag+'|'+t.text,key=group+'|'+t.text;
      // 同一个动作挂在一排按钮上（行业列表、每一行的编辑）只试两个，试多了全是重复
      if(seen.has(key)||(groups[group]||0)>=2){note('repeat',el);continue;}
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
      const btn=[...L.querySelectorAll('[data-cx="m-x"],[data-action*="close"],[class*=close],[aria-label*="关闭"],[aria-label*="lose"],button,.btn')].find(b=>vis(b)&&(b.matches('[data-cx="m-x"],[data-action*="close"],[class*=close],[aria-label*="关闭"],[aria-label*="lose"]')||CLOSE_TEXT.test((b.innerText||'').trim())));
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
  let navMiss=0;
  function navBox(){
    if(navCache&&navCache.isConnected&&vis(navCache))return navCache;
    // 没有侧栏/顶栏的页面：每次都要把整页元素量一遍，一次试按钮里会调好几次。没找到就记一会儿，别反复量
    if(Date.now()-navMiss<1500)return null;
    const W=innerWidth,H=innerHeight;
    const cand=new Set([...document.querySelectorAll(NAV_SEL)].filter(vis));
    for(const el of document.body.querySelectorAll('*')){if(!vis(el)||el.closest('[data-pa-overlay]'))continue;const r=el.getBoundingClientRect();
      if((r.left<40&&r.width<W*0.35&&r.height>H*0.55)||(r.top<90&&r.height<130&&r.width>W*0.6))cand.add(el);}
    let best=null,score=2;const open=layers();
    for(const el of cand){if(open.some(l=>l.contains(el)))continue;const r=el.getBoundingClientRect();if(r.width>W*0.6&&r.height>H*0.6)continue;
      const n=navItems(el).length;if(n>score||(n===score&&best&&best.contains(el))){best=el;score=n;}}
    navCache=best;if(!best)navMiss=Date.now();return best;
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
  // 当前亮着的页签（每个页签条一个）：展示类操作常常是「切到另一个页签并定位到这条」，比如整改跟踪 → 异常跟踪
  function activeTabs(){
    const box=navBox();
    return [...document.querySelectorAll('[role=tablist],[class*=tab],[class*=Tab]')].filter(el=>vis(el)&&(el.matches('[role=tablist]')||TAB_BAR.test(String(el.className)))&&!(box&&box.contains(el))&&!inChrome(el)&&!layers().some(l=>l.contains(el)))
      .map(bar=>{const items=navItems(bar);const a=items.find(el=>el.matches('[aria-selected=true]')||ACTIVE.test(String(el.className))||ACTIVE.test(String(el.parentElement?.className||'')));return a?ownText(a):''}).filter(Boolean);
  }
  // 展示类操作：看这一行关联的信息。点了没有任何可见变化，就是「还没接上」，列进待补
  const DISPLAY_TEXT=/查看|明细|详情|跟踪|记录|日志|历史|路线|轨迹|预览|档案|履历|追溯|溯源/;
  const ACTION_HEAD=/^(确认|确定|取消|提交|保存|删除|新增|添加|导入|导出|批量|生成|发起|关联|解除)/;   // 「确认关联」「取消关联」这类是动作不是查看
  // 有提示也算有反应（toast、消息条），不算没接上
  function feedback(){return [...document.querySelectorAll('[class*=toast],[class*=Toast],[class*=message],[class*=notice],[class*=notify],[class*=snackbar],[role=alert],[role=status]')].filter(vis).map(el=>ownText(el).slice(0,40)).join('|')}
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
  function stateSig(){
    const t=(document.body&&document.body.innerText)||'';
    const v=[...document.querySelectorAll('input,select,textarea')].slice(0,300).map(e=>e.type==='checkbox'||e.type==='radio'?(e.checked?1:0):String(e.value).slice(0,20)).join('\u0001');
    return location.hash+'\u0002'+t+'\u0002'+v;
  }
  let probeBase=null,probeSig='';
  async function probeInit(full){
    await sleep(50);probeBase=snapshot();probeSig=pageSig();
    if(!full)return {sig:probeSig};
    let page='';try{page=freeze(document.body).replace(/^<body[^>]*>|<\/body>$/g,'');}catch{}
    if(page.length>1500000)page='';
    const skipped={};
    return {sig:probeSig,title:pageTitle(),styles:stylesOf(),page,width:innerWidth,height:innerHeight,triggers:triggersIn(document,false,null,skipped),tabs:tabsIn(),skipped};
  }
  async function probeTry(path,step){
    if(!await closeAll(probeBase)||pageSig()!==probeSig)return {needReload:true};
    const textBefore=stateSig();
    for(const s of path){
      if(s.nav){const was=pageSig();if(!await press(s,probeBase))return {ok:false,reason:'replay'};if(!await waitChange(was,1500))return {ok:false,reason:'replay'};continue;}
      const before=snapshot();if(!await press(s,probeBase))return {ok:false,reason:'replay'};if(!await waitOpen(before,1200))return {ok:false,reason:'replay'};
    }
    const before=snapshot(),sigBefore=pageSig(),hashBefore=location.hash,navBefore=activeNav(),headsBefore=mainHeads(),tabsBefore=activeTabs().join('|'),fbBefore=feedback();
    const pressed=findTarget(step.target,step.inLayer?topOpen(probeBase):document),raw=pressed?bare(pressed):'';
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
      // 用户纠正过：按用户说的来（这其实是别的业务页面 / 子页面 / 页签）
      if(step.force==='jump')out.jump={hash:location.hash,nav:navNow,title:(navNow&&navNow!==navBefore?navNow:'')||pageTitle(),forced:true};
      else if(step.force==='subpage'||step.force==='tab')out.subpage={...subpageOf(),...(step.force==='tab'?{title:step.target.text,tab:true}:{})};
      else if(jumped)out.jump={hash:location.hash,nav:navNow,title:navNow||pageTitle()};
      // 页签：点了就是这一页的另一个视图
      else if(step.tab){out.subpage={...subpageOf(),title:step.target.text,tab:true};}
      // 真换了一页（地址变了，或内容区的标题换了一套）才算子页面；只是筛选、切个开关、表格换了几行，不算一层
      else if(location.hash!==hashBefore||headsMoved(headsBefore,mainHeads()))out.subpage=subpageOf();
      // 切到了同一页的另一个页签：连到那张页签卡，不再单独建卡
      else{const now=activeTabs(),was=tabsBefore.split('|');const moved=now.find(t=>!was.includes(t));if(moved)out.tablink={tab:moved};}
    }
    // 什么都没发生：展示类的按钮记成「待补」（删除、查询这类本来就不试）
    if(!L&&!out.jump&&!out.subpage&&!out.tablink&&raw.length>=2&&DISPLAY_TEXT.test(raw)&&!ACTION_HEAD.test(raw)&&!CLOSE_TEXT.test(raw)&&!(pressed&&isCloser(pressed))){
      await sleep(150);
      if(pageSig()===sigBefore&&feedback()===fbBefore&&!topOpen(before))out.dead=true;
    }
    if(L){
      const wizard=wizardOf(L);
      out.opened={layerSel:selectorFor(L),title:titleOf(L),sig:titleOf(L)+'|'+(L.innerText||'').replace(/\s+/g,' ').slice(0,160),html:freeze(L),box:boxOf(L),
        triggers:triggersIn(L,true,wizard.next?[wizard.next]:[]),branches:wizard.branches};
    }
    const closed=await closeAll(probeBase);
    out.pageChanged=!closed||pageSig()!==probeSig;
    // 页面上的字、勾选、输入有没有被这一下改掉：没改就不用重载副本，省下一次加载（展开慢主要慢在这）
    out.dirty=!out.pageChanged&&stateSig()!==textBefore;
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
    if(m.type==='PA_PROBE_ROUTES'){send('PROBE_REPLY',{id:m.id,routes:routesOf(),current:location.hash,currentTitle:activeNav()||pageTitle()});return;}
    if(m.type==='PA_PROBE_NAV'){const home=location.hash,homeTitle=activeNav()||pageTitle();discoverNav().then(routes=>send('PROBE_REPLY',{id:m.id,routes,current:home,currentTitle:homeTitle}),()=>send('PROBE_REPLY',{id:m.id,routes:[]}));return;}
    if(m.type==='PA_PROBE_INIT'){if(Array.isArray(m.routes))knownRoutes=m.routes;probeInit(!!m.full).then(r=>send('PROBE_REPLY',{id:m.id,...r}),err=>send('PROBE_REPLY',{id:m.id,ok:false,error:String(err)}));return;}
    if(m.type==='PA_PROBE_TRY'){probeTry(m.path||[],m.step).then(r=>send('PROBE_REPLY',{id:m.id,...r}),err=>send('PROBE_REPLY',{id:m.id,ok:false,error:String(err),needReload:true}));return;}
    if(m.type==='PA_REPLAY'){replay(m.path||[]).then(r=>send('REPLAYED',r),()=>send('REPLAYED',{ok:false,at:0}));return;}
    if(m.type==='PA_SET_MODE'){if(m.mode!==mode)clearInk();mode=m.mode;hover=null;dragStart=null;dragging=false;if(m.mode==='interact')picked=[];if(dragBox)dragBox.style.display='none';paint();}
    if(m.type==='PA_SELECT'){
      if(!m.selector&&dragBox)dragBox.style.display='none';
      try{const one=m.selector?document.querySelector(m.selector):null;
        picked=one?[one]:[];
        if(one)send('SELECTED',{...describe(one),refresh:true});else if(m.selector)send('SELECTION_MISSING');
        paint();}catch{}
    }
    if(m.type==='PA_RENDER_MARKERS'){
      markers.forEach(m=>m.pin.remove());markers=[];
      (m.annotations||[]).forEach((a,i)=>{try{const el=document.querySelector(a.selector);if(!el)return;const pin=overlay('2px solid white');pin.textContent=i+1;pin.title=String(a.note||'').slice(0,120);Object.assign(pin.style,{width:'24px',height:'24px',borderRadius:'50% 50% 50% 4px',background:'#b8532f',color:'white',font:'600 11px system-ui',placeItems:'center',boxShadow:'0 2px 6px #0003'});markers.push({el,pin});}catch{}});paint();
    }
    if(m.type==='PA_BOX_RECT')selectRegion(m.bounds);
    if(m.type==='PA_SET_DRAG'){dragEnabled=!!m.enabled;dragStart=null;dragging=false;}
    if(m.type==='PA_DRAW_UNDO'&&strokes.length){redoStrokes.push(strokes.pop());drawInk();reportInk();}
    if(m.type==='PA_DRAW_REDO'&&redoStrokes.length){strokes.push(redoStrokes.pop());drawInk();reportInk();}
    if(m.type==='PA_DRAW_CLEAR'){clearInk();}
    if(m.type==='PA_DRAW_SHOT'){shoot().then(r=>send('DRAW_SHOT',{id:m.id,ok:true,...r}),err=>send('DRAW_SHOT',{id:m.id,ok:false,error:String(err&&err.message||err)}));}
    if(m.type==='PA_HIGHLIGHT')highlight(m.targets);
    if(m.type==='PA_SCROLL'){
      let el=document.elementFromPoint(m.x,m.y);
      while(el&&el!==document.body){const cs=getComputedStyle(el);if(/auto|scroll/.test(cs.overflowY)&&el.scrollHeight>el.clientHeight){el.scrollTop+=m.deltaY;el.scrollLeft+=m.deltaX;return;}el=el.parentElement;}
      window.scrollBy(m.deltaX,m.deltaY);paint();
    }
    if(m.type==='PA_PREVIEW'){
      try{
        if(m.prop.startsWith('--'))document.documentElement.style.setProperty(m.prop,m.value);
        else if(m.all&&m.prop!=='text'){document.querySelectorAll(m.selector).forEach(t=>{if(!t.closest('[data-pa-overlay]'))t.style.setProperty(m.prop,m.value,'important');});}
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
