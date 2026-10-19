---
name: 企业蓝
description: 国内最常见的企业后台：白色侧边菜单、标准蓝、紧凑表格，接近 Ant Design 的观感。适合审批、CRM、ERP 这类信息量大的系统。
category: 后台
order: 2
layout: sidebar
primary: "#1677ff"
background: "#f5f5f5"
side: "#ffffff"
---
# 企业蓝

## 用途
国内企业后台：审批流、CRM、ERP、工单、配置中心。信息量大，讲究规整、密度适中、一眼找到操作。

## 视觉基调
白色侧边菜单 + 浅灰底 + 白卡片，标准蓝只用在主按钮、链接、选中态。整体克制、规整，像成熟的企业软件。

## 配色怎么用
- 主色蓝 = 能点的东西（主按钮、链接、选中菜单），别拿来做大面积背景。
- 状态四色：success 绿通过、warning 橙待处理、danger 红驳回或异常、info 蓝进行中；neutral 灰是草稿、停用。

## 布局
- 菜单分组 ≤ 6 个、每组 ≤ 8 页；页面头 → 筛选卡片 → 表格卡片，和 Ant Design Pro 的列表页一个结构。
- 筛选项多于 4 个时，只露常用的 3 个，其余收进「展开」。
- 表格行高 50、表头 44；金额右对齐加 `num`；操作列固定在最右，最多 3 个文字链接。

## 要做 / 不要做
- 要：表单两列 `.form-grid`，标签在上；详情用 Drawer（560 宽）分组展示。
- 不要：彩色大卡片、渐变、插画；不要一页放两个主按钮。

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
