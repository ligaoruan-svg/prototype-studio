#!/bin/bash
# 双击这个文件，打出一个能放进「应用程序」的 原型工坊.app。
# 第一次要下载打包工具，需要联网，大概三五分钟；以后改了代码再双击一次就是新版本。
cd "$(dirname "$0")/.." || exit 1   # 脚本放在 scripts/ 里，干活要在项目根目录
# 在 GitHub Actions 这类自动打包的机器上（环境变量 CI 有值）不问问题、不装到本机
fail() { echo ""; echo "打包没成功：$1"; [ -z "$CI" ] && read -r -p "按回车关闭"; exit 1; }
ask() { if [ -n "$CI" ]; then REPLY="n"; else read -r -p "$1" REPLY; fi; }

echo "== 打包 原型工坊.app =="
command -v python3 >/dev/null || fail "没找到 python3，先装 Python 3.10 以上版本"

# 打包工具单独放一个环境，不影响平时用的 .venv
if [ ! -d .venv-build ]; then
  echo "第一次打包：准备打包工具…"
  python3 -m venv .venv-build || fail "创建打包环境失败"
fi
# shellcheck disable=SC1091
source .venv-build/bin/activate || fail "打包环境损坏，删掉 .venv-build 文件夹后重试"
echo "检查依赖…"
python -m pip install -q --upgrade pip >/dev/null 2>&1
python -m pip install -q -e . "pywebview>=5.3" "pyinstaller>=6.11" || fail "依赖安装失败，检查网络后重试"

echo "构建界面…"
if [ -d frontend/node_modules ] && command -v node >/dev/null; then
  (cd frontend && node scripts/build-esm.mjs .) || fail "界面构建失败"
fi
[ -f frontend/dist/index.html ] || fail "缺少 frontend/dist（需要 Node.js 构建界面）"

echo "生成图标…"
rm -rf build/icon.iconset && mkdir -p build/icon.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s desktop/icon.png --out "build/icon.iconset/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2)); sips -z $d $d desktop/icon.png --out "build/icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns build/icon.iconset -o build/icon.icns || fail "图标生成失败"

echo "打包（一两分钟）…"
pyinstaller desktop/prototype_studio.spec --noconfirm --clean --log-level WARN \
  --distpath build/dist --workpath build/work || fail "PyInstaller 出错，看上面的报错"

mkdir -p release
APP="release/原型工坊.app"
rm -rf "$APP"
ditto build/dist/PrototypeStudio.app "$APP" || fail "复制应用失败"

# 应用里不能带你的东西：没有项目、没有模型设置。拿你本机的密钥去整个 .app 里找一遍，找到就不发
echo "检查应用里有没有带上你的密钥…"
[ -d "$APP/Contents/Resources/data" ] && fail "应用里混进了 data 文件夹（项目和模型设置），已停止"
for x in skills components; do
  [ -d "$APP/Contents/Resources/prompts/$x" ] && fail "应用里混进了你装的 $x，已停止"
done
python3 desktop/release_check.py "$APP" || fail "应用里发现了你的项目、skill 或 API 密钥，已停止。不要把这个 .app 发给别人"

# 安装包：发给别人的就是这个 .dmg。对方双击打开，把「原型工坊」拖到「应用程序」就装好了
VERSION=$(python3 -c 'import re;print(re.search(r"VERSION = \"([^\"]+)\"", open("backend/config.py", encoding="utf-8").read()).group(1))')
DMG="release/原型工坊-$VERSION.dmg"
echo "做安装包…"
rm -rf build/dmg "$DMG" && mkdir -p build/dmg
ditto "$APP" "build/dmg/原型工坊.app" && ln -s /Applications "build/dmg/应用程序"
hdiutil create -volname "原型工坊 $VERSION" -srcfolder build/dmg -ov -format UDZO "$DMG" >/dev/null || fail "安装包生成失败"
rm -rf build/dmg

# 你自己这台电脑第一次装：把现有的项目、设计规范、组件和 skill 复制过去（只复制，不动原来的）。
# 模型设置和密钥不复制——应用第一次打开会请你绑定，和别人拿到这个应用时一样
SUPPORT="$HOME/Library/Application Support/原型工坊"
if [ ! -e "$SUPPORT/data" ] && [ -d data/projects ]; then
  ask "把现在的项目复制到应用里？（模型要在应用里重新绑定）[Y/n] "
  case "$REPLY" in [nN]*) ;; *)
  mkdir -p "$SUPPORT/prompts" "$SUPPORT/data"
  ditto data/projects "$SUPPORT/data/projects"
  [ -f prompts/design-spec.md ] && cp prompts/design-spec.md "$SUPPORT/prompts/"
  for x in skills components; do [ -d "prompts/$x" ] && ditto "prompts/$x" "$SUPPORT/prompts/$x"; done
  ;; esac
fi

echo ""
echo "打好了："
echo "  安装包（发给别人用这个）：$DMG"
echo "  应用本体：$APP"
echo "安装包是空的：没有你的项目、模型、组件和 skill。对方打开 .dmg，把「原型工坊」拖进「应用程序」，"
echo "第一次打开如果提示「无法验证开发者」：右键点 原型工坊 →「打开」，或在「系统设置 → 隐私与安全性」里点「仍要打开」。"
ask "装到「应用程序」文件夹？[Y/n] "
case "$REPLY" in
  [nN]*) ;;
  *)
    # 先把旧的停掉、删掉，不然新版装不进去：
    # 正在开着的原型工坊.app、终端里跑着的浏览器版服务（5173 端口），以及「应用程序」里的旧版本
    echo "停掉旧版本…"
    osascript -e 'quit app "原型工坊"' >/dev/null 2>&1
    sleep 1
    pkill -f "原型工坊.app/Contents/MacOS/PrototypeStudio" >/dev/null 2>&1
    lsof -ti tcp:5173 2>/dev/null | xargs kill 2>/dev/null
    if [ -e "/Applications/原型工坊.app" ]; then
      echo "删掉旧的 原型工坊.app…"
      rm -rf "/Applications/原型工坊.app" 2>/dev/null || \
        osascript -e 'do shell script "rm -rf /Applications/原型工坊.app" with administrator privileges' >/dev/null 2>&1
      [ -e "/Applications/原型工坊.app" ] && fail "旧版本删不掉：在「应用程序」里把 原型工坊 拖进废纸篓，再双击一次这个脚本"
    fi
    if ditto "$APP" "/Applications/原型工坊.app"; then
      echo "已装好，可以在「启动台」或「应用程序」里打开 原型工坊。"
      open "/Applications/原型工坊.app"
    else
      echo "没有写入「应用程序」的权限，已在访达里选中，拖进去就行。"; open -R "$APP"
    fi ;;
esac
if [ -z "$CI" ]; then
  open -R "$DMG"   # 在访达里选中安装包，发给别人就拖这个文件
  read -r -p "按回车关闭"
fi
