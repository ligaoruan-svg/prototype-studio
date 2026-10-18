# PyInstaller 打包配置：生成 build/dist/PrototypeStudio.app（打包脚本再改名成「原型工坊.app」）
# 用法见项目根目录的「打包Mac应用.command」，不用手动跑
import os
import re

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
VERSION = re.search(r'VERSION = "([^"]+)"', open(os.path.join(ROOT, 'backend', 'config.py'), encoding='utf-8').read()).group(1)

# 只打程序自带的：系统提示词、默认设计规范、界面、新建模板。
# prompts/skills、prompts/components 是你自己装的（公司的 skill 包、组件库），不打进去——
# 应用要能发给别人，别人打开看到的必须是空的，他们自己导入自己的
datas = [
    (os.path.join(ROOT, 'frontend', 'dist'), 'frontend/dist'),
    (os.path.join(ROOT, 'sample', 'starter.html'), 'sample'),
] + [(os.path.join(ROOT, 'prompts', name), 'prompts')
     for name in ('agent-system.md', 'discussion-system.md', 'design-spec.md')]
hidden = (collect_submodules('uvicorn')
          + collect_submodules('backend', filter=lambda name: not name.startswith('backend.tests'))
          + ['multipart', 'python_multipart'])

a = Analysis([os.path.join(ROOT, 'desktop', 'app.py')], pathex=[ROOT], datas=datas, hiddenimports=hidden,
             excludes=['tkinter', 'backend.tests'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PrototypeStudio', console=False)
coll = COLLECT(exe, a.binaries, a.datas, name='PrototypeStudio')
app = BUNDLE(
    coll,
    name='PrototypeStudio.app',
    icon=os.path.join(ROOT, 'build', 'icon.icns'),
    bundle_identifier='app.prototype-studio',
    version=VERSION,
    info_plist={
        'CFBundleName': '原型工坊',
        'CFBundleDisplayName': '原型工坊',
        'CFBundleShortVersionString': VERSION,
        'CFBundleVersion': VERSION,
        'LSMinimumSystemVersion': '11.0',
        'NSHighResolutionCapable': True,
        'LSApplicationCategoryType': 'public.app-category.developer-tools',
        # 界面从本机服务载入；原型里引用的外部图片、字体也要能显示
        'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True, 'NSAllowsArbitraryLoadsInWebContent': True},
    },
)
