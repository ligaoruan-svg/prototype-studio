"""文件放哪：程序自带的东西和用户自己的东西分开。

- APP_ROOT：程序自带、只读——提示词、前端界面、示例页面。源码运行时是项目根目录；
  打成 Mac 应用后是 .app 里的资源目录（PyInstaller 的 sys._MEIPASS）
- HOME：用户的东西、要能写——项目、模型设置、记忆，以及用户能改的设计规范、组件库、skill 包。
  源码运行时也是项目根目录（和以前完全一样）；桌面版由启动程序设 PROTOTYPE_STUDIO_HOME，
  指到 ~/Library/Application Support/原型工坊。.app 里面不能写，升级时还会整个换掉
"""
import os
import shutil
import sys
from pathlib import Path

APP_ROOT = Path(getattr(sys, '_MEIPASS', None) or Path(__file__).resolve().parents[1])
HOME = Path(os.environ['PROTOTYPE_STUDIO_HOME']).expanduser() if os.environ.get('PROTOTYPE_STUDIO_HOME') else APP_ROOT

DATA_DIR = HOME / 'data'
PROMPTS = APP_ROOT / 'prompts'                    # 系统提示词：随程序升级
STYLES_DIR = PROMPTS / 'styles'                   # 软件自带的几套风格：只读，随程序升级（scripts/生成内置风格.py 生成）
USER_PROMPTS = HOME / 'prompts'                   # 用户改过的规范、装的组件和 skill
SPEC_FILE = USER_PROMPTS / 'design-spec.md'
SKILLS_DIR = USER_PROMPTS / 'skills'
COMPONENTS_DIR = USER_PROMPTS / 'components'


def seed_home() -> None:
    """桌面版第一次打开：把自带的设计规范、组件库、skill 包复制一份到 HOME。
    已经有的不覆盖——那是用户改过的"""
    if HOME.resolve() == APP_ROOT.resolve():
        return
    USER_PROMPTS.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SPEC_FILE.exists() and (PROMPTS / 'design-spec.md').exists():
        shutil.copy2(PROMPTS / 'design-spec.md', SPEC_FILE)
    for name in ('skills', 'components'):
        source, target = PROMPTS / name, USER_PROMPTS / name
        if source.is_dir() and not target.exists():
            shutil.copytree(source, target)


seed_home()
