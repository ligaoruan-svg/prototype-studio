#!/bin/bash
# 双击：把代码传到你 GitHub 上的私有仓库，让 GitHub 的电脑同时打出 Windows 安装程序和 Mac 安装包，
# 打完自动下载到 release/github。以后改了代码再双击一次，就是新版本。
# 上传的只有代码：data/（项目、模型设置、密钥）、打包缓存都不传，上传前还会再查一遍。
cd "$(dirname "$0")/.." || exit 1   # 脚本放在 scripts/ 里，干活要在项目根目录
REPO_NAME="prototype-studio"
fail() { echo ""; echo "没成功：$1"; read -r -p "按回车关闭"; exit 1; }

echo "== 上传到 GitHub，自动打 Windows 和 Mac 安装包 =="

# 清掉之前在这台电脑上留下的 git 临时文件（没有删除权限时改名留下的）
rm -f .git/stale-* .git/index.lock .git/HEAD.lock .git/objects/maintenance.lock 2>/dev/null
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null

# 0~1. 连 GitHub（自动用上代理）、装 gh、登录
source desktop/ci/connect_github.sh

# 2. 上传前检查：你的项目和密钥绝对不能上去
echo "检查要上传的内容…"
git ls-files | grep -qE '^data/' && fail "data 文件夹被 git 记录了，里面是你的项目和密钥，已停止"
python3 - <<'PY' || fail "代码历史里有你的 API 密钥，已停止上传"
import json, subprocess, sys
try:
    data = json.load(open("data/config.json", encoding="utf-8"))
except (OSError, ValueError):
    sys.exit(0)
keys = {data.get("api_key") or ""} | {p.get("api_key") or "" for p in data.get("profiles", [])}
revs = subprocess.run(["git", "rev-list", "--all"], capture_output=True, text=True).stdout.split()
for k in (k for k in keys if len(k) >= 8):
    if revs and subprocess.run(["git", "grep", "-q", "-F", k] + revs).returncode == 0:
        sys.exit(1)
PY

# 3. 打包流程放到 GitHub 认的位置
mkdir -p .github/workflows
if ! cmp -s desktop/ci/package.yml .github/workflows/package.yml; then
  cp desktop/ci/package.yml .github/workflows/package.yml
  git add .github/workflows/package.yml
  git commit -q -m "GitHub Actions：打 Windows 和 Mac 安装包" || fail "提交失败"
fi
git diff --quiet && git diff --cached --quiet || echo "（提醒：有没提交的改动，这次不会上传它们）"

# 4. 建私有仓库并上传；建过了就只推最新代码
BRANCH=$(git branch --show-current)
if git remote get-url origin >/dev/null 2>&1; then
  echo "上传最新代码…"
  git push -u origin "$BRANCH" || fail "上传失败"
else
  OWNER=$(gh api user -q .login) || fail "读不到你的 GitHub 用户名"
  if gh repo view "$OWNER/$REPO_NAME" >/dev/null 2>&1; then
    git remote add origin "https://github.com/$OWNER/$REPO_NAME.git"
    git push -u origin "$BRANCH" || fail "上传失败"
  else
    echo "在你的 GitHub 上建私有仓库 $REPO_NAME（只有你看得到）…"
    gh repo create "$REPO_NAME" --private --source . --remote origin --push || fail "建仓库失败"
  fi
fi

# 5. 让 GitHub 开始打包，等它打完下载回来
echo "让 GitHub 开始打包…"
last_run() { gh run list --workflow package.yml --limit 1 --json databaseId -q '.[0].databaseId' 2>/dev/null; }
BEFORE=$(last_run)
# 刚上传的打包配置，GitHub 要过一会儿才认得到（马上启动会报 404），多试几次
started=""
for _ in $(seq 1 12); do
  if why=$(gh workflow run package.yml --ref "$BRANCH" 2>&1); then started=1; break; fi
  sleep 5
done
if [ -z "$started" ]; then
  echo "GitHub 的原话：$why"
  echo "仓库里现在认到的打包流程："; gh workflow list --all 2>&1 | sed 's/^/  /'
  REPO_URL=$(gh repo view --json url -q .url 2>/dev/null)
  open "$REPO_URL/actions" 2>/dev/null
  fail "没能启动打包。已在浏览器打开仓库的 Actions 页面，截图发给 Claude"
fi
RUN=""
for _ in $(seq 1 30); do   # 新的一次运行要过几秒才查得到；别拿成上一次的
  sleep 3; RUN=$(last_run)
  [ -n "$RUN" ] && [ "$RUN" != "$BEFORE" ] && break
done
[ -n "$RUN" ] && [ "$RUN" != "$BEFORE" ] || fail "打包启动了但没查到，到仓库网页的 Actions 里看"
echo ""
echo "GitHub 正在打包，大约 10 分钟。窗口别关，打完会自动下载。"
gh run watch "$RUN" --exit-status >/dev/null || fail "GitHub 上打包出错了。看详情：gh run view $RUN --web（把网页截图发给 Claude）"
rm -rf release/github && mkdir -p release/github
gh run download "$RUN" -D release/github || fail "下载失败，可以在网页上下载：gh run view $RUN --web"
echo ""
echo "打好了，在 release/github 里："
find release/github -type f \( -name '*.exe' -o -name '*.zip' -o -name '*.dmg' \) | sed 's/^/  /'
echo "都是空的：没有你的项目、模型、组件和 skill，可以直接发给别人。"
open release/github
read -r -p "按回车关闭"
