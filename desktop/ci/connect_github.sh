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
if ! ok_github 8; then
  unset https_proxy http_proxy all_proxy
  for port in 7890 7897 7891 1087 1080 8889 10809 10808 33210 6152; do
    if curl -s --max-time 4 -x "http://127.0.0.1:$port" -o /dev/null https://api.github.com; then
      export https_proxy="http://127.0.0.1:$port" http_proxy="http://127.0.0.1:$port"; break
    fi
  done
fi
ok_github 10 || fail "终端连不上 GitHub（浏览器能上是因为走了代理，终端没走）。
  - 用 Clash / ClashX / Surge 这类工具的：打开「系统代理」或「增强模式 / TUN 模式」，再双击一次这个脚本
  - 或者把代理软件里「复制终端代理命令」复制出来，告诉 Claude 端口号"
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

