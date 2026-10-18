"""发出去之前查一遍：打好的应用里不能带你的东西。Mac 和 Windows 打包脚本都调它。

查三样：项目和模型设置（data 文件夹）、你自己装的 skill 和组件、你绑定的 API 密钥（逐个文件搜）。
用法：python desktop/release_check.py <打好的应用目录>   查到问题退出码 1
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def own_keys() -> set[bytes]:
    try:
        data = json.loads((ROOT / 'data' / 'config.json').read_text('utf-8'))
    except (OSError, ValueError):
        return set()
    keys = {data.get('api_key') or ''} | {p.get('api_key') or '' for p in data.get('profiles', [])}
    return {k.encode() for k in keys if len(k) >= 8}


def check(app: Path) -> list[str]:
    problems = []
    for folder in app.rglob('*'):
        if folder.is_dir() and folder.parent.name == 'prompts' and folder.name in ('skills', 'components'):
            problems.append(f'混进了你装的 {folder.name}：{folder}')
        if folder.is_dir() and folder.name == 'data' and (folder / 'projects').exists():
            problems.append(f'混进了 data 文件夹（项目和模型设置）：{folder}')
    keys = own_keys()
    for root, _, files in os.walk(app):
        for name in files:
            path = Path(root) / name
            try:
                blob = path.read_bytes()
            except OSError:
                continue
            if any(k in blob for k in keys):
                problems.append(f'这个文件里有你的 API 密钥：{path}')
    return problems


if __name__ == '__main__':
    found = check(Path(sys.argv[1]))
    for line in found:
        print('  ' + line)
    sys.exit(1 if found else 0)
