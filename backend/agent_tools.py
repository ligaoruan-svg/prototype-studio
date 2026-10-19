"""给模型的工具清单：每个工具的名字、什么时候用、参数怎么写。

改工具的说明就改这里；工具的执行在 agent.py 的主循环里。
"""
from __future__ import annotations

from . import memory

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "inspect_page",
            "description": "读取当前页面摘要、标注目标和相关 DOM 片段。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_source",
            "description": "在当前 HTML 源码中搜索关键词并返回附近上下文。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_source_slice",
            "description": "按行读取当前 HTML 的一段源码。",
            "parameters": {
                "type": "object",
                "properties": {"start": {"type": "integer"}, "end": {"type": "integer"}},
                "required": ["start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_operations",
            "description": "对当前页面执行局部 DOM/CSS/JS 修改。一次可以提交多条操作。插入现成组件用 insert_component（只写 name 和 selector，原文由系统插入，不要自己抄一遍）。从页面外壳起步的页面，加新页面用 shell_add 一次写完 nav/pages/bind/script，不用先读源码找位置。",
            "parameters": {
                "type": "object",
                "properties": {
                    "operations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": [
                                        "set_text", "set_html", "set_attr", "remove_attr", "add_class",
                                        "remove_class", "insert_before", "insert_after", "replace_outer_html",
                                        "remove", "append_style", "append_script", "replace_source_text",
                                        "replace_region", "set_token", "set_style", "insert_component", "shell_add"
                                    ],
                                },
                                "selector": {"type": "string"},
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                                "old": {"type": "string"},
                                "new": {"type": "string"},
                                "region": {"type": "string"},
                                "position": {"type": "string", "enum": ["before", "after", "inside", "replace"],
                                             "description": "仅 insert_component 使用：相对 selector 的位置，默认 after"},
                                "nav": {"type": "string", "description": "仅 shell_add：要加的一级菜单分组（页面一定放在分组的 items 里，手机风格也一样），如 {key:'order',label:'订单管理',items:[{key:'refund',label:'退款审核'}]}；多个分组用逗号隔开，不要外面再包 []"},
                                "pages": {"type": "string", "description": "仅 shell_add：Pages 里的页面方法，如 refund(){return pageShell('退款审核','说明',内容HTML,右上按钮)}"},
                                "bind": {"type": "string", "description": "仅 shell_add：放进 bindPage(page) 的代码，如 if(page==='quota'){...}"},
                                "script": {"type": "string", "description": "仅 shell_add：数据、状态对象、辅助函数、PageEvents.on(...)，放在页面方法前面"},
                            },
                            "required": ["action"],
                        },
                    }
                },
                "required": ["operations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_page",
            "description": "校验当前 HTML 结构和指定元素/文本是否存在。",
            "parameters": {
                "type": "object",
                "properties": {
                    "assertions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"selector": {"type": "string"}, "contains": {"type": "string"}, "exists": {"type": "boolean"}},
                            "required": ["selector"],
                        },
                    }
                },
            },
        },
    },
]

TOOL_SPECS.extend([
    {"type":"function","function":{"name":"read_skill",
     "description":"这轮任务符合某个 skill 的适用说明时，取它的正文来照着做。",
     "parameters":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}}},
    {"type":"function","function":{"name":"read_skill_file",
     "description":("按行取 skill 正文里引用的文件，path 用正文里写的相对路径。组件库这类文件很大，"
                    "一次只给一段；返回里有 truncated 就按它给的行号往后接着读。"
                    "不要整份通读——读完就没额度写页面了。知道要找什么就用 search_skill_file。"),
     "parameters":{"type":"object","properties":{"name":{"type":"string"},"path":{"type":"string"},
                   "start":{"type":"integer","description":"起始行，默认 1"},
                   "end":{"type":"integer","description":"结束行，默认 start+200"}},
                   "required":["name","path"]}}},
    {"type":"function","function":{"name":"start_from_shell",
     "description":("页面还是空白骨架、要从零做一整页时，先调它：程序把 skill 里的「页面外壳」整份放进页面——"
                    "样式、顶栏、左侧菜单、hash 路由、弹窗 / 抽屉 / Toast 等组件函数都现成，不花你的输出额度。"
                    "之后你只写三处：/*PA:NAV*/ 菜单配置、/*PA:PAGES*/ 每页内容、/*PA:BIND*/ 交互绑定。"
                    "页面已经有内容时不能用。"),
     "parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"search_skill_file",
     "description":("在 skill 的附带文件里搜关键词，只拿回命中处附近的内容。要用组件库里的某个组件"
                    "（表格、Modal、分页…）时用这个，比整份读快得多，也不会把额度耗光。"),
     "parameters":{"type":"object","properties":{"name":{"type":"string"},"path":{"type":"string"},
                   "query":{"type":"string","description":"组件名或类名，如「Form Modal」「data-table」"}},
                   "required":["name","path","query"]}}},
])

TOOL_SPECS.extend([
    {"type":"function","function":{"name":"remember",
     "description":"用户说了以后还算数的约定时记下来，一次一条。一次性指令、你的推测、页面内容都不要记。",
     "parameters":{"type":"object","properties":{"note":{"type":"string","description":"用你自己的话写成一句"},
       "category":{"type":"string","enum":list(memory.CATEGORIES)},
       "scope":{"type":"string","enum":["project","global"],"description":"project 只对这个项目；global 是他在所有项目里的个人习惯"}},"required":["note"]}}},
    {"type":"function","function":{"name":"search_chats",
     "description":"在这个项目以前的全部对话里按关键词查（对话记录只带了最近几条）。用户说「上次那个」「之前说过的」时用。",
     "parameters":{"type":"object","properties":{"query":{"type":"string","description":"一到三个关键词，空格隔开"}},"required":["query"]}}},
    {"type":"function","function":{"name":"forget",
     "description":"用户说不用再守某条约定时，传它的 id 删掉。",
     "parameters":{"type":"object","properties":{"id":{"type":"string"}},"required":["id"]}}},
])

TOOL_SPECS.append({"type": "function", "function": {
    "name": "read_component", "description": "取一个可复用组件的原文，照它的结构写，不要另起炉灶。",
    "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}})

TOOL_SPECS.append({"type": "function", "function": {
    "name": "read_region", "description": "读取一个 region 的原始代码，作为精确补丁的依据。",
    "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
}})


TOOL_SPECS.extend([
    {"type":"function","function":{"name":"answer_user","description":"回答设计问题并给出可选的局部修改建议；不执行修改。",
     "parameters":{"type":"object","properties":{"answer":{"type":"string"},"suggestions":{"type":"array","maxItems":3,"items":{"type":"object","properties":{"label":{"type":"string","description":"10 个字以内的短标题"},"summary":{"type":"string","description":"给用户看的一句话说明，20 个字以内，说清改完是什么样"},"instruction":{"type":"string","description":"交给修改执行的完整指令，用户默认看不到"},"recommended":{"type":"boolean","description":"最推荐的那一条标 true，只标一条"}},"required":["label","summary","instruction"]}}},"required":["answer"]}}},
    {"type":"function","function":{"name":"report_result","description":"结束本轮修改前汇报结论和每条意见的真实处理结果。",
     "parameters":{"type":"object","properties":{"summary":{"type":"string"},"assumptions":{"type":"array","items":{"type":"string"},"maxItems":2},
     "annotations":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"status":{"type":"string","enum":["completed","partial","unprocessed"]},"reason":{"type":"string"}},"required":["id","status"]}},
     "retry_hint":{"type":"string","description":"没能改成时，写一句用户可以直接发送的换种说法；改成了就留空。"}},
     "required":["summary","annotations"]}}},
    {"type":"function","function":{"name":"update_plan","description":("改动需要三步以上时，先列出计划，只列一次——之后程序按你每轮的修改自动推进状态，不要再调它更新。"
                                                                    "步骤用页面上的叫法，不写选择器。从零做页面时同时写 brief（业务梳理）。"),
     "parameters":{"type":"object","properties":{"steps":{"type":"array","minItems":2,"maxItems":6,"items":{"type":"object","properties":{
     "title":{"type":"string"},"status":{"type":"string","enum":["pending","active","done"]}},"required":["title","status"]}},
     "brief":{"type":"string","description":"从零做页面时的业务梳理，3–5 行：谁用、管什么、有哪些状态和规则、哪些操作合理哪些不该有、页面要先回答用户哪几个问题"}},"required":["steps"]}}},
    {"type":"function","function":{"name":"ask_user","description":"改动方向存在重大歧义、删除数据或大范围重排时，先问一个问题，不做修改。",
     "parameters":{"type":"object","properties":{"question":{"type":"string"},"options":{"type":"array","minItems":2,"maxItems":3,"items":{"type":"string"}}},"required":["question","options"]}}}
])


OPERATION_ACTIONS = set(next(t for t in TOOL_SPECS if t["function"]["name"] == "apply_operations")
                        ["function"]["parameters"]["properties"]["operations"]["items"]["properties"]["action"]["enum"])
