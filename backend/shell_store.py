"""页面外壳里的统一数据层 Store：业务数据只放一份，所有页面都从它读，按钮改的也是它，改完当前页自动重画。

以前每页各写各的演示数据，「退租后铺位变空置、招商看板跟着刷新」这种跨页联动每次都要 AI 现场搭，
切页还会把改过的状态重置掉。现在：
- 内置风格的外壳生成时就带着（scripts/生成内置风格.py 把 STORE_JS 放进骨架）
- 别的外壳（自己装的 skill、以前做的原型）在 shell_add 时补进去（ensure）
"""
from __future__ import annotations

from .shell_list import LIST_JS, MARK as LIST_MARK

MARK = "const Store="

STORE_JS = r"""// ===== 业务数据：所有页面共用一份（Store）=====
// 演示数据在 script 里用 Store.define('工单',[…]) 写一次（切页不会重置）；页面从 Store 读，按钮改也改 Store，
// 改完当前页自动重画：列表、统计数字、别的页面都跟着变，跨页联动不用自己写。
// 状态流转：Store.flow('工单',{派单:['待派单','处理中'],完工:['处理中','待评价']})；按钮出不出现用 Store.can，点了用 Store.move。
const Store=(()=>{
  const data={},seq={},flows={};let timer=0;
  const list=n=>data[n]||(data[n]=[]);
  const same=(a,b)=>String(a)===String(b);
  const redraw=()=>{clearTimeout(timer);timer=setTimeout(()=>{if(typeof Router!=='undefined'&&document.getElementById('content'))Router.render()},0)};
  return{
    // 先被 Store.all 读过（还是空的）也照样定义
    define(n,rows=[]){if(!data[n]||!data[n].length){data[n]=rows.map((r,i)=>({id:r.id??`${n}-${i+1}`,...r}));seq[n]=data[n].length}
      else if(rows.length)console.error(`Store.define('${n}') 已经定义过了，这次的数据没用上：要加字段用 Store.all('${n}').forEach(r=>…)，要换数据改原来那段`);
      return data[n]},
    all(n){return list(n)},
    get(n,id){return list(n).find(r=>same(r.id,id))},
    where(n,fn){return list(n).filter(fn)},
    count(n,fn){return fn?list(n).filter(fn).length:list(n).length},
    sum(n,field,fn){return (fn?list(n).filter(fn):list(n)).reduce((s,r)=>s+(+r[field]||0),0)},
    add(n,row){seq[n]=(seq[n]??list(n).length)+1;const r={id:row.id??`${n}-${seq[n]}`,...row};list(n).unshift(r);redraw();return r},
    update(n,id,patch){const r=this.get(n,id);if(!r)return null;Object.assign(r,typeof patch==='function'?patch(r):patch);redraw();return r},
    remove(n,id){const l=list(n),i=l.findIndex(r=>same(r.id,id));if(i>=0)l.splice(i,1);redraw()},
    names(){return Object.keys(data)},
    flow(n,map){if(map===undefined)return flows[n];flows[n]=map},
    can(n,id,action){const r=this.get(n,id),f=(flows[n]||{})[action];return !!(r&&f&&[].concat(f[0]).includes(r.status))},
    move(n,id,action,patch={}){
      const r=this.get(n,id),f=(flows[n]||{})[action];
      if(!r||!f){UI.Toast(`没有「${action}」这个操作`,'error');return false}
      if(![].concat(f[0]).includes(r.status)){UI.Toast(`现在是「${r.status}」，不能${action}`,'error');return false}
      const from=r.status;Object.assign(r,typeof patch==='function'?patch(r):patch,{status:f[1]});
      (r.logs||(r.logs=[])).push({action,from,to:f[1],at:new Date().toLocaleString('zh-CN',{hour12:false})});
      redraw();return true}
  }
})();
"""

ANCHORS = ("// ===== 业务菜单", "const NAV=[/*PA:NAV*/")


def ensure(source: str) -> str:
    """外壳里还没有 Store、列表页模板就补进去，放在菜单配置前面；不是外壳的页面不动"""
    if "const NAV=[/*PA:NAV*/" not in source:
        return source
    add = (STORE_JS + "\n" if MARK not in source else "") + (LIST_JS + "\n" if LIST_MARK not in source else "")
    if not add:
        return source
    at = next((source.find(a) for a in ANCHORS if a in source), -1)
    return source[:at] + add + source[at:]
