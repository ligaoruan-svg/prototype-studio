---
name: 活力电商
description: 橙红主色、价格醒目、商品卡片两列排，热闹有购买欲。适合商城、外卖、团购、会员这类用户端手机页面。
tagline: 橙红 · 商城外卖
category: 手机
order: 9
layout: mobile
primary: "#ff5a1f"
background: "#f5f5f7"
side: "#14213d"
---
# 活力电商

## 用途
用户端的商城、外卖、团购、会员页面：首页、商品列表、商品详情、购物车、订单、我的。

## 视觉基调
浅灰底 + 白卡片 + 橙红主色，价格和促销醒目，信息排得紧凑但不乱，有逛街的热闹感。

## 配色怎么用
- 橙红 = 价格、主按钮（加入购物车、立即购买）、促销标签；同一屏橙红元素不要超过 3 处，否则什么都不突出。
- 价格写法：`<b style="color:var(--primary)">¥<span style="font-size:20px">99</span>.00</b>`，原价用灰色删除线。

## 布局（外壳已经做好）
- 底部 Tab 一般是：首页、分类、购物车、订单、我的（icon 用 home / grid / list / bell / user）。
- 商品列表两列卡片 `.grid.two`：图片色块占位（1:1）+ 两行标题 + 价格 + 销量；详情页底部固定一条「加入购物车 / 立即购买」。
- 搜索框放在首页顶部第一屏；分类页左边一列分类、右边商品。

## 要做 / 不要做
- 要：数字真实可信（¥ 129.00、已售 2.3 万）；按钮写清动作。
- 不要：满屏渐变和闪烁动效；不要把重要信息只用颜色表达（促销要有文字「限时」「满减」）。

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
