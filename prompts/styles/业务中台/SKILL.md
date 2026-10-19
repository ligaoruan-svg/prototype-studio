---
name: 业务中台
description: 顶部深色一级导航 + 左侧二级菜单：多个业务模块并列、每个模块下若干页面。适合运营中台、订单中台、供应链这类模块多的系统。
tagline: 顶部模块 + 左侧菜单
category: 中台
order: 4
layout: topbar
primary: "#1f6feb"
background: "#f2f4f7"
side: "#0f1b2d"
---
# 业务中台

## 用途
模块多的业务中台：订单、商品、库存、结算、会员……每个模块下面若干页面，用户经常在模块之间跳。

## 视觉基调
顶部深色导航条压住整页，下面是浅灰工作区 + 白卡片。信息密，层级靠「顶部模块 → 左侧页面 → 卡片」三层清楚分开。

## 布局（外壳已经做好）
- NAV 的每个分组 = 顶部一个模块；分组里的 items = 左侧二级菜单。模块 4~8 个最合适，每个模块 2~8 页；只有一页的模块不显示左侧菜单。
- 中台首页常用「工作台」：上面一排待办数字（指标卡，点了跳到对应列表），下面左宽右窄 `.grid.two`：左边待办列表、右边快捷入口和公告。
- 列表页、详情页的写法和后台一样：筛选卡片 + 表格卡片 + 分页；详情用 Drawer。

## 配色怎么用
- 主色蓝只给主按钮、链接和选中态；顶栏深色不要再放彩色按钮。
- 跨模块的状态颜色保持一致：同一个「待处理」在所有模块都是 warning。

## 要做 / 不要做
- 要：每个模块名短（2~4 字）；指标卡带「去处理」链接。
- 不要：在页面里再做一排 Tabs 当模块导航（顶部已经有了）；不要一页塞两张以上的大表格。

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
