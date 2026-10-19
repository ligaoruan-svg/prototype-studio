---
name: 温暖柔和
description: 米色底、陶土色主色、大圆角、标题用衬线字，温和有质感。适合内容、阅读、生活方式、预约类的手机页面。
tagline: 米色衬线 · 内容生活
category: 手机
order: 8
layout: mobile
primary: "#c2603d"
background: "#f6f2ec"
side: "#14213d"
---
# 温暖柔和

## 用途
手机上的内容、阅读、生活方式、预约、社区类页面：要让人觉得舒服、有温度，而不是工具感。

## 视觉基调
米色纸张底 + 奶白卡片 + 陶土色点缀；标题用衬线字（外壳已经设好），正文无衬线。圆角大、间距松，像一本杂志。

## 配色怎么用
- 陶土色只用在主按钮、选中的 Tab、少量强调文字；大面积是米色和奶白。
- 不要纯黑纯白：文字是深棕灰，背景是米色（外壳变量已经是这样）。

## 布局（外壳已经做好）
- 底部 Tab 和「移动端App」一样：NAV 写一个分组，页面放 items 里，前 5 个是 Tab。
- 首页常用：一句问候或标题 → 一张大的推荐卡片 → 一列内容卡片（图片占位 + 标题 + 一行摘要）。图片用带圆角的色块占位，不要外链图片。
- 一屏一个重点；主操作放在底部，用 `kind:'primary block'` 撑满宽。

## 要做 / 不要做
- 要：文案口语、亲切（「今天想读点什么？」）；卡片之间留足间距。
- 不要：密集表格、小字号、硬朗的直角；不要冷色调的蓝色按钮。

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
