#!/bin/bash
# 双击：把 prototype-studio 开源出去。
#   1. 补上许可证（AGPL-3.0）、把最新代码和 README 传上去
#   2. 把仓库改成公开（会先问你）
#   3. 打 v版本号 标签：GitHub 自动打 Mac / Windows 安装包并发布到 Releases
#   4. 把你账号下其他仓库归档（会先列出来问你；归档后仍然公开、只读）
cd "$(dirname "$0")/.." || exit 1   # 脚本放在 scripts/ 里，干活要在项目根目录
fail() { echo ""; echo "没成功：$1"; read -r -p "按回车关闭"; exit 1; }
ask() { read -r -p "$1 [y/N] " a; case "$a" in [yY]*) return 0 ;; *) return 1 ;; esac; }

echo "== 开源发布 原型工坊 =="
rm -f .git/stale-* .git/index.lock .git/HEAD.lock .git/objects/maintenance.lock 2>/dev/null
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null
source desktop/ci/connect_github.sh
git remote get-url origin >/dev/null 2>&1 || fail "还没传过 GitHub：先双击 scripts 里的「上传GitHub打包.command」"
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner) || fail "读不到仓库信息"
OWNER=${REPO%%/*}
VERSION=$(python3 -c 'import re;print(re.search(r"VERSION = \"([^\"]+)\"", open("backend/config.py", encoding="utf-8").read()).group(1))')
BRANCH=$(git branch --show-current)

# 1. 许可证 + 最新代码
if [ ! -f LICENSE ]; then
  echo "加许可证 AGPL-3.0…"
  gh api licenses/agpl-3.0 --jq .body > LICENSE && grep -q "GNU AFFERO GENERAL PUBLIC LICENSE" LICENSE || fail "许可证下载失败"
  git add LICENSE && git commit -q -m "许可证：AGPL-3.0" || fail "提交许可证失败"
fi
mkdir -p .github/workflows
if ! cmp -s desktop/ci/package.yml .github/workflows/package.yml; then
  cp desktop/ci/package.yml .github/workflows/package.yml
  git add .github/workflows/package.yml && git commit -q -m "GitHub Actions：打包并发布到 Releases" || fail "提交失败"
fi
git ls-files | grep -qE '^data/' && fail "data 文件夹被 git 记录了，里面是你的项目和密钥，已停止"
echo "上传最新代码…"
git push -q origin "$BRANCH" || fail "上传失败"

# 2. 改成公开
VIS=$(gh repo view "$REPO" --json visibility -q .visibility)
gh repo edit "$REPO" --description "用说话的方式做可点击的 HTML 原型：点一下告诉 AI 改哪里，改完自己检查，随时退回。本地运行，模型用你自己的。" \
  --add-topic prototype --add-topic html --add-topic ai-agent --add-topic llm --add-topic vue --add-topic fastapi --add-topic desktop-app >/dev/null 2>&1
if [ "$VIS" != "PUBLIC" ]; then
  echo ""
  echo "要把 $REPO 改成公开：所有人都能看到代码和全部提交历史（包括提交里的邮箱、prompts/skills 里的 skill 包和 docs 里的文档）。"
  if ask "确定改成公开？"; then
    gh repo edit "$REPO" --visibility public --accept-visibility-change-consequences || fail "改公开失败"
    echo "✓ 已公开：https://github.com/$REPO"
  else
    echo "先不公开。"
  fi
fi

# 3. 发版本
TAG="v$VERSION"
if git ls-remote --tags origin "refs/tags/$TAG" | grep -q .; then
  echo "标签 $TAG 已经发过。"
  if ask "重新打包这个版本的安装包，替换 Releases 上的附件？"; then
    for _ in $(seq 1 12); do gh workflow run package.yml --ref "$TAG" >/dev/null 2>&1 && { echo "✓ 已开始重新打包（大约 15 分钟），打完自动替换"; break; }; sleep 5; done
  fi
else
  echo "打标签 $TAG：GitHub 会打 Mac / Windows 安装包并发到 Releases（大约 15 分钟）…"
  git tag -a "$TAG" -m "原型工坊 $VERSION" 2>/dev/null
  git push -q origin "$TAG" || fail "标签上传失败"
fi

# 4. 归档其他仓库
OTHERS=$(gh repo list "$OWNER" --limit 100 --json name,isArchived,isFork -q '.[] | select(.isArchived | not) | .name' | grep -vx "${REPO#*/}")
if [ -n "$OTHERS" ]; then
  echo ""
  echo "你账号下还有这些没归档的仓库（归档 = 只读、标记为不再维护，仍然公开可见，以后可以取消归档）："
  echo "$OTHERS" | sed 's/^/  - /'
  if ask "全部归档？"; then
    for name in $OTHERS; do gh repo archive "$OWNER/$name" --yes && echo "  ✓ 已归档 $name"; done
  fi
fi

echo ""
echo "完成。仓库：https://github.com/$REPO"
echo "安装包打好后在：https://github.com/$REPO/releases"
echo "最后一步：在个人主页点「Customize your pins」，只勾 prototype-studio，让它显示在主页最上面。"
open "https://github.com/$OWNER"
read -r -p "按回车关闭"
