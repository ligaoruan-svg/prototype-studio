"""原型工坊的本机服务：建应用、安全检查（只收本机、同源的请求）、统一的错误处理，把各领域的接口挂上来，最后托管界面文件。
接口本身在 routes/ 下按领域分文件"""
from __future__ import annotations

from urllib.parse import urlsplit as _urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse as _JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .errors import WorkError, error_payload
from .patcher import PatchError
from .paths import APP_ROOT as ROOT
from .routes import agent_runs, memory, pages, projects, settings
from .safety import host_name

FRONTEND_DIST = ROOT / "frontend" / "dist"
app = FastAPI(title="原型工坊", version=config.VERSION)


# 本机工具也会被别的网站"顺手"调用：浏览器里任何网页都能往 127.0.0.1 发表单。
# 改东西的请求必须来自原型工坊自己的页面（Origin 和 Host 一致）；原型预览跑在沙箱里，Origin 是 null，也拦掉。
# DNS rebinding：恶意网站把自己的域名临时解析到 127.0.0.1，浏览器就把它当成同源，
# Origin 和 Host 都是 evil.com:5173，上面的比较拦不住。所以 Host 本身必须是本机地址。
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}


@app.middleware("http")
async def same_origin_only(request, call_next):
    if host_name(request.headers.get("host", "")) not in LOCAL_HOSTS:
        return _JSONResponse({"detail": "原型工坊只接受本机地址（127.0.0.1 / localhost）的访问"}, status_code=400)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin is not None and _urlsplit(origin).netloc != request.headers.get("host", ""):
            return _JSONResponse({"detail": "只接受原型工坊自己页面发来的修改请求"}, status_code=403)
        # 没带 Origin 的浏览器请求（老式表单之类），看 Sec-Fetch-Site：不是同源发来的一律不收
        site = request.headers.get("sec-fetch-site")
        if origin is None and site and site not in ("same-origin", "none"):
            return _JSONResponse({"detail": "只接受原型工坊自己页面发来的修改请求"}, status_code=403)
    return await call_next(request)


# 各接口里漏掉的错误统一兜住：项目或页面不存在 → 404，参数不对 → 400，模型出错 → 按错误分类说人话。
# 以前这些会变成一句「Internal Server Error」，界面上什么都看不出来
@app.exception_handler(FileNotFoundError)
async def _not_found(request, exc):
    return _JSONResponse({"detail": "项目或页面不存在，可能已经移到回收站"}, status_code=404)


@app.exception_handler(KeyError)
async def _missing(request, exc):
    return _JSONResponse({"detail": "没找到要操作的对象，可能已经被删除或移到回收站"}, status_code=404)


@app.exception_handler(ValueError)
async def _bad_value(request, exc):
    return _JSONResponse({"detail": str(exc)[:300] or "参数不对"}, status_code=400)


@app.exception_handler(PatchError)
async def _patch(request, exc):
    return _JSONResponse({"detail": str(exc)[:600]}, status_code=400)


@app.exception_handler(WorkError)
async def _work(request, exc):
    payload = error_payload(exc)
    return _JSONResponse({"detail": payload["message"], "error": payload}, status_code=502 if payload["code"] in {"network", "busy", "timeout", "model_account"} else 400)


# 各领域的接口。界面文件的兜底路由（/{path}）要放在最后，所以先挂这些
for _module in (settings, memory, projects, pages, agent_runs):
    app.include_router(_module.router)


# 界面文件名里没有版本号（app.css、App.js 一直是这个名字）。
# Starlette 只发 etag 和 last-modified，不发 Cache-Control，浏览器就按启发式规则
# 自己判定「这个文件还新鲜」，连问都不问服务器——改了代码、重启了服务，页面还是老样子，
# 只能靠人记得按 Cmd+Shift+R。这里要求每次都回来核对；没变就是 304，本地几乎不花时间。
NO_CACHE = {"Cache-Control": "no-cache"}


class FreshFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", FreshFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path in {'api','preview','preview-assets'} or path.startswith(("api/", "preview/", "preview-assets/")):
            raise HTTPException(404)
        candidate = (FRONTEND_DIST / path).resolve()
        if FRONTEND_DIST.resolve() not in candidate.parents and candidate != FRONTEND_DIST.resolve():
            raise HTTPException(404)
        if path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate, headers=NO_CACHE)
        return FileResponse(FRONTEND_DIST / "index.html", headers=NO_CACHE)
