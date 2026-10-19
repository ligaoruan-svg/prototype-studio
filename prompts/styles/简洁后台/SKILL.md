---
name: 简洁后台
description: PC 管理后台：左侧深色菜单、白底卡片、筛选 + 表格 + 分页。适合订单、用户、商品、配置这类增删改查页面。
layout: sidebar
primary: "#2f6fed"
background: "#f6f7f9"
---
# 简洁后台

## 用途
做 PC 端管理后台：列表、详情、表单、配置，以及简单的数据概览。

## 这套风格的规矩
- 菜单：NAV 里一级分组 + 二级页面，左侧深色菜单会把分组名显示成小标题。分组不超过 6 个，每组不超过 8 页；不要在页面里再加一层主 Tabs 当导航。
- 一页从上到下：页面头（标题 + 一句说明 + 右上按钮）→ 指标卡（可选，一排最多 4 张）→ 筛选栏 + 表格卡片。
- 页面头右上最多 1 个主按钮（新建、导出这类），其余用默认按钮。
- 列表页：卡片里先放 `<div class="card-bd"><div class="filter">字段…<div class="filter-actions">查询 / 重置</div></div></div>`，再放表格和 ZeroUI.Pager。
- 表格包在 `<div class="tw">` 里，`table.data-table` 用 `<colgroup>` 定列宽；第一列重要信息用 `td.t1`，金额、数量加 `num`；操作列在最右，最多 3 个 `.lnk` 文字链接。
- 状态用 ZeroUI.Tag：info 进行中 / success 已完成 / warning 待处理 / danger 异常 / neutral 草稿、停用。
- 新建、编辑用 Modal（字段 ≤ 6 个，两列 `.form-grid`）；字段多或长详情用 Drawer；删除、停用必须 ConfirmModal({danger:true})。

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
