# 连上 GitHub 并登录 gh。上传GitHub打包.command、开源发布.command 都 source 它（调用方要先定义 fail）
# 0. 连 GitHub：浏览器能上 GitHub 多半是开了代理（Clash 之类），但终端默认不走代理。
#    这里先读系统代理设置，不行再试常见的本机代理端口，都通了才往下走
ok_github() { curl -s --max-time "${1:-8}" -o /dev/null https://api.github.com; }
if [ -z "$https_proxy$HTTPS_PROXY$all_proxy$ALL_PROXY" ]; then
  eval "$(scutil --proxy 2>/dev/null | awk '
    /HTTPSEnable : 1/ {he=1} /HTTPSProxy :/ {hh=$3} /HTTPSPort :/ {hp=$3}
    /SOCKSEnable : 1/ {se=1} /SOCKSProxy :/ {sh=$3} /SOCKSPort :/ {sp=$3}
    END { if (he && hh) printf "export https_proxy=http://%s:%s http_proxy=http://%s:%s\n", hh, hp, hh, hp;
          else if (se && sh) printf "export all_proxy=socks5h://%s:%s\n", sh, sp }')"
fi
echo "检查能不能连上 GitHub…"
SAVED_PROXY_FILE="build/.github-proxy"   # 上次连通用的代理，先试它（build/ 不上传）
try_proxy() { curl -s --max-time "${2:-10}" -x "$1" -o /dev/null https://api.github.com; }
use_proxy() { export https_proxy="$1" http_proxy="$1"; mkdir -p build; echo "$1" > "$SAVED_PROXY_FILE"; }
connected=""
ok_github 10 && connected=1
if [ -z "$connected" ]; then
  unset https_proxy http_proxy all_proxy
  candidates="$(cat "$SAVED_PROXY_FILE" 2>/dev/null)"
  for port in 7897 7890 7891 1087 1080 8889 10809 10808 33210 6152; do candidates="$candidates http://127.0.0.1:$port"; done
  for round in 1 2; do   # 代理有时第一下慢，多给一轮、多等一会
    for proxy in $candidates; do
      if try_proxy "$proxy" $((round * 8)); then use_proxy "$proxy"; connected=1; break 2; fi
    done
    [ "$round" = 1 ] && echo "（还没连上，再试一轮…）"
  done
fi
[ -n "$connected" ] || fail "终端连不上 GitHub（浏览器能上是因为走了代理，终端没走）。
  - 先确认代理软件（Clash Verge 之类）开着、节点能用，再双击一次这个脚本
  - 还不行：打开代理软件的「系统代理」或「TUN 模式」，或者把它显示的端口号告诉 Claude"
[ -n "$https_proxy$all_proxy" ] && echo "（通过本机代理 ${https_proxy:-$all_proxy} 连 GitHub）"

# 1. GitHub 命令行工具：登录走浏览器，不用自己弄令牌
if ! command -v gh >/dev/null; then
  command -v brew >/dev/null || fail "需要先装 Homebrew（brew.sh），或者到 cli.github.com 装 GitHub CLI"
  echo "安装 GitHub 命令行工具…"
  brew install gh || fail "GitHub 命令行工具装不上，检查网络后重试"
fi
if ! gh auth status >/dev/null 2>&1; then
  echo ""
  echo "接下来登录 GitHub：终端里会给你一串验证码，浏览器打开后把它填进去、点授权。"
  gh auth login --hostname github.com --git-protocol https --web || fail "没登录上 GitHub"
fi
gh auth setup-git >/dev/null 2>&1

