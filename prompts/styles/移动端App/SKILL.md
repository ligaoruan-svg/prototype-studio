---
name: 移动端App
description: 手机 App / H5：430px 宽居中、顶部标题、底部 Tab 栏、圆角卡片和列表。适合用户端的下单、订单、个人中心这类页面。
layout: mobile
primary: "#1f7a5c"
background: "#f2f4f7"
---
# 移动端App

## 用途
做手机 App 或 H5 页面：首页、列表、详情、下单、个人中心。外壳把页面限制在 430px 宽、居中，顶部是页面标题，底部是 Tab 栏。

## 这套风格的规矩
- 底部 Tab = NAV 里按顺序排的前 5 个页面（分组名不显示）；页面可以加 `icon:'home'|'grid'|'list'|'bell'|'user'` 指定图标。超过 5 个的页面（详情、设置）用链接 `#页面key` 进入。
- 页面标题显示在顶部栏里（pageShell 的第一个参数），页面里不用再写大标题。
- 列表用 `.list` + ZeroUI.ListItem({title,desc,extra,id}) 或一张张卡片；不要横向很宽的表格。
- 点击区域至少 44px 高；一屏底部的主操作用 `ZeroUI.Button({label:'提交',kind:'primary block'})` 撑满宽度。
- 表单字段一列排；选项多、或要选择的内容用 Drawer（外壳里是从底部弹出的面板）。
- 确认、提示用 ConfirmModal / Toast，不要 alert。
- 指标卡一排 2 张；一屏不要塞太多卡片，留白比 PC 多。

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
