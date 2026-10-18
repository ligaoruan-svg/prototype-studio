"""打包 Windows 版：生成便携版 zip 和安装程序。在 Windows 上双击「打包Windows应用.bat」会调这个。

步骤和 Mac 版一样：单独的打包环境 → 构建界面 → 图标 → PyInstaller → 查有没有带上你的东西 → 打成安装包。
--ci：在 GitHub Actions 这类干净机器上跑，不建虚拟环境、不问问题。
"""
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = '--ci' in sys.argv
os.chdir(ROOT)


def say(text):
    print(text, flush=True)


def fail(text):
    say('\n打包没成功：' + text)
    if not CI:
        input('按回车关闭')
    sys.exit(1)


def run(*cmd, **kw):
    if subprocess.run([str(c) for c in cmd], **kw).returncode != 0:
        fail('命令出错：' + ' '.join(str(c) for c in cmd[:4]))


def build_python() -> Path:
    if CI:
        return Path(sys.executable)
    venv = ROOT / '.venv-build-win'
    py = venv / 'Scripts' / 'python.exe'
    if not py.exists():
        say('第一次打包：准备打包工具…')
        run(sys.executable, '-m', 'venv', venv)
    return py


def main():
    if os.name != 'nt':
        fail('这个脚本要在 Windows 上跑；Mac 上用「打包Mac应用.command」')
    version = re.search(r'VERSION = "([^"]+)"', (ROOT / 'backend' / 'config.py').read_text('utf-8')).group(1)
    say(f'== 打包 原型工坊 {version}（Windows）==')
    py = build_python()
    say('检查依赖…')
    run(py, '-m', 'pip', 'install', '-q', '--upgrade', 'pip')
    run(py, '-m', 'pip', 'install', '-q', '-e', '.', 'pywebview>=5.3', 'pyinstaller>=6.11', 'pillow')

    say('构建界面…')
    if (ROOT / 'frontend' / 'node_modules').exists() and shutil.which('node'):
        run('node', 'scripts/build-esm.mjs', '.', cwd=ROOT / 'frontend')
    if not (ROOT / 'frontend' / 'dist' / 'index.html').exists():
        fail('缺少 frontend/dist（需要 Node.js 构建界面）')

    say('生成图标…')
    (ROOT / 'build').mkdir(exist_ok=True)
    run(py, '-c', "from PIL import Image; Image.open('desktop/icon.png').save('build/icon.ico', "
                  "sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])")

    say('打包（一两分钟）…')
    run(py, '-m', 'PyInstaller', 'desktop/prototype_studio_win.spec', '--noconfirm', '--clean', '--log-level', 'WARN',
        '--distpath', 'build/dist-win', '--workpath', 'build/work-win')
    app = ROOT / 'build' / 'dist-win' / 'PrototypeStudio'

    say('检查应用里有没有带上你的东西…')
    if subprocess.run([str(py), 'desktop/release_check.py', str(app)]).returncode != 0:
        fail('应用里发现了你的项目、skill 或密钥，已停止。不要把它发给别人')

    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    portable = release / f'原型工坊-{version}-Windows便携版.zip'
    say('做便携版 zip…')
    with zipfile.ZipFile(portable, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in app.rglob('*'):
            if path.is_file():
                zf.write(path, Path('原型工坊') / path.relative_to(app))

    iscc = shutil.which('ISCC') or next((str(p) for p in (
        Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Inno Setup 6' / 'ISCC.exe',
        Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Inno Setup 6' / 'ISCC.exe',
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs' / 'Inno Setup 6' / 'ISCC.exe') if p.exists()), None)
    installer = None
    if iscc:
        say('做安装程序…')
        run(iscc, '/Q', f'/DAppVersion={version}', f'/DSourceDir={app}', f'/DOutputDir={release}', 'desktop/installer.iss')
        installer = release / f'原型工坊-{version}-Windows安装程序.exe'
    say('\n打好了：')
    if installer:
        say(f'  安装程序（发给别人用这个）：{installer}')
    else:
        say('  （没装 Inno Setup，这次没做安装程序。想要的话到 jrsoftware.org 免费下载 Inno Setup 6，装好再打包一次）')
    say(f'  便携版（解压就能用，不用安装）：{portable}')
    say('两个都是空的：没有你的项目、模型、组件和 skill。对方打开后绑定他自己的模型。')
    say('第一次打开如果 Windows 提示「已保护你的电脑」：点「更多信息」→「仍要运行」。')
    if not CI:
        os.startfile(release)
        input('按回车关闭')


if __name__ == '__main__':
    main()
