---
name: 移动端App
description: 手机 App / H5：430px 宽居中、顶部标题、底部 Tab 栏、圆角卡片和列表。适合用户端的下单、订单、个人中心这类页面。
category: 手机
order: 7
layout: mobile
primary: "#1f7a5c"
background: "#f2f4f7"
side: "#14213d"
---
# 移动端App

## 用途
做手机 App 或 H5 页面：首页、列表、详情、下单、个人中心。外壳把页面限制在 430px 宽、居中，顶部是页面标题，底部是 Tab 栏。

## 这套风格的规矩
- 底部 Tab = NAV 里按顺序排的前 5 个页面（分组名不显示）；页面可以加 `icon:'home'|'grid'|'list'|'bell'|'user'` 指定图标。超过 5 个的页面（详情、设置）用链接 `#页面key` 进入。
- NAV 和别的风格一样写成分组，页面放在 items 里，不要直接写页面数组：shell_add 的 nav 写 `{key:'app',label:'App',items:[{key:'home',label:'首页',icon:'home'},{key:'orders',label:'订单',icon:'list'},{key:'me',label:'我的',icon:'user'}]}`。
- 页面标题显示在顶部栏里（pageShell 的第一个参数），页面里不用再写大标题。
- 列表用 `.list` + ZeroUI.ListItem({title,desc,extra,id}) 或一张张卡片；不要横向很宽的表格。
- 点击区域至少 44px 高；一屏底部的主操作用 `ZeroUI.Button({label:'提交',kind:'primary block'})` 撑满宽度。
- 表单字段一列排；选项多、或要选择的内容用 Drawer（外壳里是从底部弹出的面板）。
- 确认、提示用 ConfirmModal / Toast，不要 alert。
- 指标卡一排 2 张；一屏不要塞太多卡片，留白比 PC 多。

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
