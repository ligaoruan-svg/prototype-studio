---
name: 数据大屏
description: 深色数据大屏：顶部标题和时间、大号指标、柱状图和占比条。适合投屏、监控、经营看板，一屏看全。
layout: screen
primary: "#3ad1ff"
background: "#070f1f"
---
# 数据大屏

## 用途
做投屏用的数据大屏、监控看板、经营驾驶舱：以「看」为主，一屏看全，不做复杂表单。

## 这套风格的规矩
- 按 1920×1080 设计，1440 宽也不能乱；内容尽量一屏放下、不出纵向滚动：一排 4~6 个指标，下面 2 行图表卡（`.grid.three` 或 `.grid.two`）。
- 一屏最多 8 张卡。卡片标题带主题色竖条（外壳已经做好），标题短，4~8 个字。
- 指标数字用 `.metric-value`（大号、主题色），涨跌写在 `.metric-foot` 里，用 `.up` / `.down`。
- 图表用 ZeroUI.Bars（柱状图）、ZeroUI.Meter（占比 / 进度条），或者纯 CSS / 内联 SVG 自己画；不要引外部图表库（离线也要能看）。
- 颜色：深色底，主题色只用在数字、图表和选中态上；不要出现大块白底、浅色卡片。
- 多个看板写成 NAV 里的多个页面，外壳会显示成标题下方的切换按钮；只有一页时不显示。
- 少按钮：交互只做切换时间范围、点卡片或条目看详情（Drawer）。页面头的标题用一句话说明这屏看什么。
- 明细用 `.list` + ZeroUI.ListItem 做「最新 N 条」滚动条目，不要带分页的大表格。

## 通用写法（三套内置风格都一样）
- 新页面从外壳起步：页面还是空的就 start_from_shell，已经是外壳就直接 apply_operations 一条 shell_add 写 nav / pages / bind / script。
- 样式只用外壳里的类和 CSS 变量（var(--primary) 等），不要另写一套颜色、字号、圆角；确实要加样式，也引用这些变量。
- 不要僵尸交互：分页、筛选、开关、按钮、行操作都要有真实效果，至少 ZeroUI.Toast 一句。提交时按钮进 loading 防止重复点。
- 示例数据用中性的名字和编号（张三、李四、王五；SO-20261018-0012），不用真实人名。

## 外壳里现成的组件
- ZeroUI.Button({label,kind:'primary'|'danger'|'danger-solid',icon:SVG.plus,id}) · ZeroUI.Tag({text,kind:'info'|'success'|'warning'|'danger'|'neutral'}) · ZeroUI.Field({label,type:'text'|'select'|'textarea',options,required,full,id})
- ZeroUI.Pager({total,page,pageSize}) · ZeroUI.Empty({title,text,action}) · ZeroUI.ListItem({title,desc,extra,id,href}) · ZeroUI.Toast('已保存')
- ZeroUI.Bars({items:[{label,value}],unit,current}) 柱状图 · ZeroUI.Meter({items:[{label,value}],max,unit}) 占比条
- ZeroUI.openModal(ZeroUI.Modal({title,body,wide}), (close,btn)=>{…}) · ZeroUI.openModal(ZeroUI.ConfirmModal({title,message,danger:true}), close=>{…}) · ZeroUI.openDrawer(ZeroUI.Drawer({title,body}), close=>{…})
- Card({title,desc,body,extra}) · 指标卡 `<div class="metric-grid"><div class="metric"><div class="metric-label">今日订单</div><div class="metric-value">1,284</div><div class="metric-foot"><span class="up">+8.2%</span> 较昨日</div></div></div>`
- 栅格 `.grid.two/.three/.four`，键值详情 `<dl class="kv"><dt>…</dt><dd>…</dd></dl>`，开关 `<button class="switch on">`
