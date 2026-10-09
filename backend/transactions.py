"""Two-phase edits and a source-preserving, unified undo timeline."""
import hashlib
import threading
import time
import uuid

from . import storage
from .atomicio import write_atomic
from .patcher import PatchError, verify_source
from .experience import diff_source

LOCK = storage.META_LOCK   # 和改 project.json 的其他操作共用一把，免得互相覆盖
PENDING = {}


def invalidate(project_id, page_id=""):
    with LOCK:
        for token, item in list(PENDING.items()):
            if item['project_id']==project_id and (not page_id or item['page_id']==page_id):
                del PENDING[token]


def digest(source):
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def undo_entries(page):
    if 'undo_stack' in page:
        return list(page['undo_stack'])
    # Adapt old records lazily; no old source, snapshots or metadata are discarded.
    versions = sorted(page.get('versions',[]), key=lambda v:v['version'])
    entries = [{'id':f"legacy-v{v['version']}",'kind':'agent','before_file':versions[i-1]['file'],
                'reason':v.get('reason','旧版修改'),'created_at':v.get('created_at','')}
               for i,v in enumerate(versions) if i>0]
    entries += [{**item,'kind':'manual','before_file':item['file']} for item in page.get('manual_edits',[])]
    return entries


def stage(project_id, page_id, before, after, reason, kind="manual", **extra):
    check = verify_source(after)
    if not check["ok"]:
        raise PatchError("修改检查未通过，已保留上一版："+"；".join(check["issues"]))
    if after==before:
        return {"changed":False,"validation":check}
    with LOCK:
        # Also prevent a long-running model from staging work for a deleted page.
        storage.get_page(storage.load_meta(project_id),page_id)
        for key in list(PENDING):
            if PENDING[key]["expires"]<time.time(): del PENDING[key]
        token = uuid.uuid4().hex
        diff = diff_source(before,after)
        PENDING[token] = dict(project_id=project_id,page_id=page_id,before=before,after=after,
                             reason=reason[:120],kind=kind,expires=time.time()+900,diff=diff,**extra)
    return {"changed":True,"pending_id":token,"validation":check,"diff":diff,
            "targets":extra.get('targets',[]),"change_count":extra.get('operation_count',len(diff['hunks'])),
            "preview_url":f"/api/candidates/{token}/preview","hash":digest(after)}


def get(token):
    entry = PENDING.get(token)
    if not entry or entry["expires"]<time.time():
        raise PatchError("待确认的修改已过期，请重新修改")
    return entry


def commit(token, runtime_errors, runtime_checked):
    with LOCK:
        item = get(token)
        if not runtime_checked: raise PatchError("尚未完成检查")
        if runtime_errors:
            del PENDING[token]
            raise PatchError("运行检查失败，已保留上一版："+"；".join(runtime_errors)[:1500])
        pid,page_id = item["project_id"],item["page_id"]
        current = storage.read_page(pid,page_id)
        if digest(current)!=digest(item["before"]):
            del PENDING[token]
            raise PatchError("页面已被其他操作更新，请刷新后重试")
        meta = storage.load_meta(pid); page = storage.get_page(meta,page_id)
        stack = undo_entries(page)
        history = list(page.get('edit_history',[]))
        if item['kind']=='undo':
            if not stack or stack[-1]['id']!=item['undo_id']:
                raise PatchError("撤销记录已变化，请重试")
            stack.pop()
        edit_id = uuid.uuid4().hex
        path = storage.project_dir(pid)/"changes"/page_id/f"{edit_id}-before.html"
        path.parent.mkdir(parents=True,exist_ok=True)
        write_atomic(path, current)
        record = {'id':edit_id,'kind':item['kind'],'before_file':str(path.relative_to(storage.project_dir(pid))),
                  'reason':item['reason'],'created_at':storage.now_iso()}
        if item['kind']=='manual':
            write_atomic(storage.page_file(pid,page_id), item['after'])   # 原地覆写半路断电会留下半截页面
            page.setdefault('manual_edits',[]).append({**record,'file':record['before_file']})
            page['manual_edits'] = page['manual_edits'][-60:]
            page['updated_at'] = meta['updated_at'] = storage.now_iso()
            storage.save_meta(meta)
        else:
            if page.get('manual_edits') and item['kind']!='undo':
                storage.write_page(pid,page_id,current,"微调记录")
            storage.write_page(pid,page_id,item['after'],item['reason'])
        meta = storage.load_meta(pid); page = storage.get_page(meta,page_id)
        if item['kind']!='undo':
            stack.append(record)
        else:
            record['undo_of'] = item['undo_id']
        page['undo_stack'] = stack[-100:]
        page['edit_history'] = (history+[record])[-300:]
        # Only explicitly completed annotations are consumed.
        for ann in meta.get('annotations',[]):
            if ann['id'] in item.get('annotation_ids',[]):
                ann.update(status='applied',applied_at=storage.now_iso())
        storage.save_meta(meta)
        if item.get('message'):
            storage.append_chat(pid,"assistant",item['message'],{
                "page_id":page_id,"changed":True,"usage":item.get("usage",{}),"report":item.get('report'),
                "change_id":edit_id,"diff":item['diff'],"targets":item.get('targets',[]),
                "change_count":item.get('operation_count',len(item['diff']['hunks']))})
        del PENDING[token]
        return {"ok":True,"version":page['version'],"hash":digest(item['after']),"change_id":edit_id,
                "undo_count":len(stack),"last_undo_id":stack[-1]['id'] if stack else ''}



def undo(project_id, page_id, expected_id=""):
    page = storage.get_page(storage.load_meta(project_id),page_id)
    entries = undo_entries(page)
    if not entries: raise PatchError("没有可撤销的修改")
    last = entries[-1]
    if expected_id and expected_id!=last['id']:
        raise PatchError("只能撤销最近一步，请先撤销后续修改")
    before = storage.read_page(project_id,page_id)
    after = (storage.project_dir(project_id)/last['before_file']).read_bytes().decode('utf-8',errors='replace')
    return stage(project_id,page_id,before,after,"撤销上一步","undo",undo_id=last['id'])
