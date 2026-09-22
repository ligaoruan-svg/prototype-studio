"""Early, sandbox-compatible inspector. All editor visuals are separate overlays."""
import json

_TEMPLATE = r'''
<script data-prototype-agent-bridge>
(() => {
  const CFG = __CFG__;
  const send = (type, payload={}) => parent.postMessage({source:'prototype-agent', ...CFG, type, ...payload}, '*');
  let mode='interact', selected=null, hover=null, box, selectedBox, caption, dragStart=null, dragBox=null, markers=[];
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
  if(window.__paRoute) location.hash=window.__paRoute;
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
      text:(el.innerText||el.textContent||'').trim().slice(0,500),outer_html:el.outerHTML.slice(0,5000),
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
  function place(out,el){
    if(!out)return;
    if(!el?.isConnected || mode==='interact'){out.style.display='none';return;}
    const r=el.getBoundingClientRect();
    Object.assign(out.style,{display:'block',left:r.left+'px',top:r.top+'px',width:r.width+'px',height:r.height+'px'});
  }
  function paint(){place(box,hover);place(selectedBox,selected);for(const {el,pin} of markers){const r=el.getBoundingClientRect();pin.style.display=el.isConnected&&r.width?'grid':'none';pin.style.left=(r.right-10)+'px';pin.style.top=(r.top-10)+'px';}if(caption){caption.style.display=(mode==='select'&&hover?.isConnected)?'block':'none';if(hover?.isConnected){const r=hover.getBoundingClientRect();caption.textContent=hover.dataset.pid||hover.tagName.toLowerCase();caption.style.left=Math.max(4,r.left)+'px';caption.style.top=Math.max(4,r.top-26)+'px';}}}
  window.addEventListener('mousemove',e=>{if(mode!=='select')return;hover=e.target instanceof Element&&!e.target.closest('[data-pa-overlay]')?e.target:null;paint();},true);
  window.addEventListener('click',e=>{
    const el=e.target instanceof Element?e.target:null;if(!el)return;
    if(mode==='box'){e.preventDefault();e.stopImmediatePropagation();return;}
    if(mode==='select'){
      e.preventDefault();e.stopImmediatePropagation();selected=el;hover=null;paint();send('SELECTED',describe(el));return;
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
  window.addEventListener('keydown',e=>{if(e.target?.closest?.('input,textarea,select,[contenteditable=true]'))return;const key=e.key.toLowerCase(),command=e.metaKey||e.ctrlKey;if((!command&&!e.altKey&&['h','v','b','escape'].includes(key))||(command&&['z','/','enter'].includes(key))){e.preventDefault();send('SHORTCUT',{key:e.key,metaKey:e.metaKey,ctrlKey:e.ctrlKey,altKey:e.altKey,shiftKey:e.shiftKey});}},true);
  window.addEventListener('message',e=>{
    if(e.source!==parent)return;const m=e.data||{};
    if(m.type==='PA_SET_MODE'){mode=m.mode;hover=null;dragStart=null;if(dragBox)dragBox.style.display='none';paint();}
    if(m.type==='PA_SELECT'){
      if(!m.selector&&dragBox)dragBox.style.display='none';
      try{selected=m.selector?document.querySelector(m.selector):null;if(selected)send('SELECTED',{...describe(selected),refresh:true});else if(m.selector)send('SELECTION_MISSING');paint();}catch{}
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
    box=overlay('1px solid #b8532f');selectedBox=overlay('2px solid #b8532f');caption=overlay('0');
    Object.assign(caption.style,{background:'#b8532f',color:'#fff',font:'11px/20px system-ui',padding:'1px 6px',borderRadius:'3px'});
    restoreScroll();send('READY');send('WIDTH',{width:innerWidth});
  });
  window.addEventListener('load',()=>{restoreScroll();send('LOADED');});
})();
</script>
'''


def build_bridge(project_id, page_id):
    return _TEMPLATE.replace('__CFG__', json.dumps({'projectId':project_id,'pageId':page_id}))
