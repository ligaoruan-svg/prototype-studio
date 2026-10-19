---
name: 极简黑白
description: 黑白灰极简：浅灰侧栏、细边框、黑色主按钮，参考 Linear、Vercel 这类工具的克制感。适合 SaaS 控制台、开发者工具、设置页。
category: 后台
order: 3
layout: sidebar
primary: "#171717"
background: "#fafafa"
side: "#fafafa"
---
# 极简黑白

## 用途
SaaS 控制台、开发者工具、团队设置、账单页。用户是熟练用户，要的是安静、快、信息清楚。

## 视觉基调
几乎只有黑白灰，靠字重、间距和 1px 细线分层次，不靠颜色。留白大，标题偏大、正文偏小，对比鲜明。

## 配色怎么用
- 黑色是主色：主按钮、选中态、重点数字。彩色只出现在状态（绿成功、红错误、黄提醒），而且只用在小标签和小圆点上。
- 不要蓝色链接：链接用黑字 + 悬停底色（外壳的 .lnk 已经是这样）。

## 布局
- 页面头标题 22px，下面一句灰色说明；内容区宽，表格用细线分隔、不加斑马纹。
- 设置类页面用一列卡片：每张卡片左边标题和说明、右边控件（`.grid.two` 左窄右宽）。
- 数字、编号、时间用 `code` 类（等宽），对齐整齐。

## 要做 / 不要做
- 要：大量留白、少而准的文字；空状态一句话 + 一个按钮。
- 不要：阴影、渐变、彩色图标、圆角大于 12px；不要用颜色区分本来用文字就能区分的东西。

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
