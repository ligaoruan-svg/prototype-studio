# PyInstaller 打包配置（Windows）：生成 build/dist/PrototypeStudio/ 文件夹，里面的 PrototypeStudio.exe 双击即用。
# 用法见项目根目录的「打包Windows应用.bat」，不用手动跑
import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

# 和 Mac 版一样只打程序自带的：你的项目、模型、skill、组件都不打进去
datas = [
    (os.path.join(ROOT, 'frontend', 'dist'), 'frontend/dist'),
    (os.path.join(ROOT, 'sample', 'starter.html'), 'sample'),
    (os.path.join(ROOT, 'prompts', 'styles'), 'prompts/styles'),   # 软件自带的几套风格（只读，人人都有）
] + [(os.path.join(ROOT, 'prompts', name), 'prompts')
     for name in ('agent-system.md', 'discussion-system.md', 'design-spec.md')]
hidden = (collect_submodules('uvicorn')
          + collect_submodules('backend', filter=lambda name: not name.startswith('backend.tests'))
          + ['multipart', 'python_multipart'])

a = Analysis([os.path.join(ROOT, 'desktop', 'app.py')], pathex=[ROOT], datas=datas, hiddenimports=hidden,
             excludes=['tkinter', 'backend.tests'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PrototypeStudio', console=False,
          icon=os.path.join(ROOT, 'build', 'icon.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='PrototypeStudio')
