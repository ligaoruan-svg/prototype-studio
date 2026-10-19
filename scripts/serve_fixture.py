"""隔离验收用的模拟服务：不联网、不用真实密钥、不写用户项目。

启动：python3 scripts/serve_fixture.py  然后打开 http://127.0.0.1:5175

在对话框里输入下面的词，可以分别走到对应路径：
  含「计划」    → 任务清单：三步逐条推进、逐字输出结论
  含「改不了」  → 失败路径：给出可一键填入的换种说法
  含「检查失败」→ 运行检查不通过，自动退回上一版
  含「网络失败」/「超长输出」/「卡片」→ 网络错误 / 截断提示 / 先提问再改
"""
import json
import re
import tempfile
import time
from pathlib import Path
import uvicorn
from backend import storage, config, agent
from backend.errors import WorkError

fixture_dir = tempfile.TemporaryDirectory(prefix='prototype-acceptance-')
storage.DATA_ROOT = Path(fixture_dir.name)/'projects'
storage.DATA_ROOT.mkdir()
config.CONFIG_FILE = Path(fixture_dir.name)/'config.json'
config.save({'api_key':'isolated-fixture-key','base_url':'https://example.invalid','model':'模拟模型 · 不联网','supports_vision':True,'stream':True})
project = storage.create_project('隔离验收 · 模拟模型')
source = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
/* #region tokens */
:root{--color-primary:#0f766e;}
/* #endregion tokens */
body{font:16px/1.7 system-ui;margin:0;color:#20302b;background:#f7faf8}header{padding:30px;background:white;border-bottom:1px solid #dde5df}main{padding:30px}button{background:var(--color-primary);border:0;color:white;border-radius:6px;padding:12px 20px;margin-right:14px;cursor:pointer}.spacer{height:1500px;padding-top:60px;color:#74867b}.nested{height:200px;overflow:auto;background:white;border:1px solid #dce5df;padding:16px}.nested>div{height:650px}
</style></head><body><header><h1>交互验收页面</h1><p>当前使用模拟模型，不会调用任何外部接口。</p></header><main>
<!-- #region markup-main -->
<button id="top-action" data-pid="top-action">顶部按钮</button><div class="nested" id="nested"><div>可滚动容器</div><button id="nested-action">容器内按钮</button></div><div class="spacer">滚动到页面底部，测试修改后位置保持。</div><h2>底部操作区</h2><button id="action" data-pid="bottom-action">导出</button><button id="filter">查询</button>
<!-- #endregion markup-main -->
</main><script>const example="/* #region example-only */";</script></body></html>'''
(storage.project_dir(project['id'])/'source'/'index.html').write_text(source,'utf-8')
storage.add_page(project['id'],'index.html','交互验收页面')


def answer(name,args,on_delta=None):
    # 把结论按小段喂回去，模拟真实接口的分片节奏，用来验流式渲染。
    if on_delta:
        text = str(args.get('summary') or args.get('answer') or '')
        for i in range(0,len(text),4):
            on_delta(text[i:i+4]); time.sleep(0.04)
    return {'choices':[{'finish_reason':'tool_calls','message':{'tool_calls':[{'id':'fixture-call','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}}], 'usage':{'total_tokens':128}}


PLAN = ['把三个筛选项改成一行排列','查询和重置按钮移到右端','收紧筛选栏的上下留白']


def plan_steps(done):
    return [{'title':t,'status':'done' if i<done else 'active' if i==done else 'pending'} for i,t in enumerate(PLAN)]


def fake_chat(key,model,messages,*args,**kwargs):
    on_delta = kwargs.get('on_delta')
    time.sleep(1.2)
    kickoff=next(m['content'] for m in messages if m['role']=='user')
    if isinstance(kickoff,list): kickoff=kickoff[0]['text']
    request=kickoff.split('用户这轮说的是：')[-1]   # agent 背景资料后面接的就是用户这轮的原话
    if '网络失败' in request: raise WorkError('network','模拟网络连接失败')
    if '超长输出' in request: return {'choices':[{'finish_reason':'length','message':{'content':'未完成的输出'}}]}
    if '卡片' in request: return answer('ask_user',{'question':'整块区域改成卡片，还是每一行分别改成卡片？','options':['整块改成卡片','每行一张卡片']})
    calls=[c['function']['name'] for m in messages for c in m.get('tool_calls',[])]
    if '改不了' in request:
        return answer('report_result',{'summary':'没找到“提交按钮”：页面上有两个文字相同的按钮，不敢替你猜是哪一个。',
            'annotations':[],'retry_hint':'先点选表单底部那个提交按钮，再把它改成主色实心'},on_delta)
    if '计划' in request:
        planned=calls.count('update_plan')
        if planned==0: return answer('update_plan',{'steps':plan_steps(0)})
        if 'inspect_page' not in calls: return answer('inspect_page',{})
        if planned==1: return answer('update_plan',{'steps':plan_steps(2)})
        if 'apply_operations' not in calls:
            return answer('apply_operations',{'operations':[{'action':'set_text','selector':'#action','value':'导出清单'}]})
        if planned==2: return answer('update_plan',{'steps':[{'title':t,'status':'done'} for t in PLAN]})
        return answer('report_result',{'summary':'筛选栏已改成一行：三个下拉并排，查询和重置移到右端，上下留白收紧到 16。',
            'annotations':[],'retry_hint':''},on_delta)
    if not calls: return answer('inspect_page',{})
    if 'apply_operations' not in calls:
        ops=[{'action':'set_text','selector':'#action','value':'导出清单'}]
        if '检查失败' in request: ops.append({'action':'append_script','value':'throw new Error("模拟检查失败");'})
        return answer('apply_operations',{'operations':ops})
    if 'verify_page' not in calls: return answer('verify_page',{'assertions':[{'selector':'#action','contains':'导出清单'}]})
    ids=re.findall(r'意见 \d+ id=(ann_[a-f0-9]+)',kickoff)
    results=[{'id':ident,'status':'completed' if i==0 else 'unprocessed','reason':'' if i==0 else '模拟待确认意见'} for i,ident in enumerate(ids)]
    return answer('report_result',{'summary':'导出按钮的文字已改为“导出清单”。','annotations':results,'assumptions':[]},on_delta)


agent.chat=fake_chat
from backend.server import app
if __name__=='__main__':
    try: uvicorn.run(app,host='127.0.0.1',port=5175,log_level='warning')
    finally: fixture_dir.cleanup()
