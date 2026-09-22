"""Build a source + prebuilt UI ZIP without local data, secrets or dependencies."""
import argparse
import re
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r'VERSION = "([\d.]+)"', (ROOT/'backend'/'config.py').read_text('utf-8'))[1]
# 'Claude outputs' 是桌面端自动存放截图的目录，会凭空出现在项目里，别让它进发布包。
EXCLUDE = {'.git','.venv','.idea','node_modules','__pycache__','data','qa-artifacts','release',
           '.DS_Store','.env','.codex','Claude outputs','screenshots'}


def check_versions(root=ROOT):
    """打包前核对版本号。测试删掉后没人守着这件事，放在发布的必经之路上最省心。"""
    import json
    problems = []
    package = json.loads((root / 'frontend' / 'package.json').read_text('utf-8'))['version']
    if not package.startswith(VERSION + '.'):
        problems.append(f"frontend/package.json 是 {package}，与 backend/config.py 的 {VERSION} 对不上")
    first = (root / 'README.md').read_text('utf-8').splitlines()[0]
    if f'v{VERSION}' not in first:
        problems.append(f"README 首行「{first}」里没有 v{VERSION}")
    if problems:
        raise SystemExit('版本号不一致，先改一致再打包：\n  ' + '\n  '.join(problems))
    return VERSION


def build(output, root=ROOT):
    check_versions(root)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob('*'):
            relative = path.relative_to(root)
            if any(part in EXCLUDE for part in relative.parts) or path.suffix in {'.pyc','.zip'}:
                continue
            if path.is_file() and not path.is_symlink() and path.resolve()!=output:
                archive.write(path, str(Path('prototype-agent')/relative))
    return output


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT/'release'/f'prototype-agent-v{VERSION}.zip'))
    print(build(parser.parse_args().output))
