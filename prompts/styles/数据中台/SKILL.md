---
name: 数据中台
description: 浅色顶栏 + 左侧二级菜单，指标卡和图表卡为主：数据看板、经营分析、报表中心。比大屏更适合日常在电脑上看和筛选。
tagline: 指标图表 · 分析看板
category: 中台
order: 5
layout: topbar
primary: "#5b5bd6"
background: "#f6f7fb"
side: "#ffffff"
---
# 数据中台

## 用途
数据看板、经营分析、报表中心、指标管理：在电脑上天天看、要能筛选和下钻。要投屏就用「数据大屏」。

## 视觉基调
浅色、干净、偏冷的靛蓝。数字是主角：指标卡数字大、用主题色；图表卡标题带竖条。

## 布局（外壳已经做好）
- NAV 分组 = 顶部一级（如「经营看板」「用户分析」「报表中心」），items = 左侧具体看板。
- 一个看板从上到下：页面头右上放时间范围（今天 / 近 7 天 / 近 30 天，用一组按钮，选中的是 primary）→ 一排 4 个指标卡 → 2~3 列图表卡 → 明细表格。
- 图表用 ZeroUI.Bars、ZeroUI.Meter，或内联 SVG 画折线；每张图表卡标题写清单位和时间（「近 7 日成交额（万元）」）。

## 配色怎么用
- 一张图只用一个主色，最多再加一个灰色做对比；涨用 `.up` 绿、跌用 `.down` 红。
- 不要彩虹色的饼图和柱子。

## 要做 / 不要做
- 要：每个指标写清口径（metric-foot 里写「较昨日」「近 30 天」）；点指标卡或图表能下钻到明细（跳页或 Drawer）。
- 不要：一屏超过 12 个指标；不要只有图没有数字。

## 通用写法（所有内置风格都一样）
- 新页面从外壳起步：页面还是空的就 start_from_shell，已经是外壳就直接 apply_operations 一条 shell_add 写 nav / pages / bind / script。
- 样式只用外壳里的类和 CSS 变量（var(--primary) 等），不要另写一套颜色、字号、圆角；确实要加样式，也引用这些变量。
- 不要僵尸交互：分页、筛选、开关、按钮、行操作都要有真实效果，至少 ZeroUI.Toast 一句。提交时按钮进 loading 防止重复点。
- 示例数据用中性的名字和编号（张三、李四、王五；SO-20261018-0012），不用真实人名。

## 体验底线
- 每页先想清楚「用户来这页干什么」：最重要的数字或操作放在最显眼的位置，其余往后放。
- 列表要有空状态（ZeroUI.Empty）；表单必填标星、错误写在字段下面、提交后有结果反馈。
- 危险操作二次确认，并写清后果（「删除后不能恢复」）；按钮写具体动作（「提交审核」「加入购物车」），少用「确定」「OK」。
- 状态不能只靠颜色：标签里要有文字。正文不要用浅灰字，放在彩色底上的字要够清楚。

## 不要做（一眼就像 AI 做的）
- 紫蓝渐变、霓虹发光、到处加阴影；用 emoji 当图标。
- 什么都包一张卡片、卡片里再套卡片；一排三张一模一样的「图标 + 标题 + 一段话」卡片。
- 所有内容居中；每个区块都加一个大标题和一句空洞的介绍。
- 弹跳、抖动的动画；随手发明新的颜色、字号、圆角（用外壳的变量）。

## 外壳里现成的组件
- ZeroUI.Button({label,kind:'primary'|'danger'|'danger-solid',icon:SVG.plus,id}) · ZeroUI.Tag({text,kind:'info'|'success'|'warning'|'danger'|'neutral'}) · ZeroUI.Field({label,type:'text'|'select'|'textarea',options,required,full,id})
- ZeroUI.Pager({total,page,pageSize}) · ZeroUI.Empty({title,text,action}) · ZeroUI.ListItem({title,desc,extra,id,href}) · ZeroUI.Toast('已保存')
- ZeroUI.Bars({items:[{label,value}],unit,current}) 柱状图 · ZeroUI.Meter({items:[{label,value}],max,unit}) 占比条
- ZeroUI.openModal(ZeroUI.Modal({title,body,wide}), (close,btn)=>{…}) · ZeroUI.openModal(ZeroUI.ConfirmModal({title,message,danger:true}), close=>{…}) · ZeroUI.openDrawer(ZeroUI.Drawer({title,body}), close=>{…})
- Card({title,desc,body,extra}) · 指标卡 `<div class="metric-grid"><div class="metric"><div class="metric-label">今日订单</div><div class="metric-value">1,284</div><div class="metric-foot"><span class="up">+8.2%</span> 较昨日</div></div></div>`
- 栅格 `.grid.two/.three/.four`，键值详情 `<dl class="kv"><dt>…</dt><dd>…</dd></dl>`，开关 `<button class="switch on">`
