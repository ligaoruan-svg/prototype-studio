"""Conservative intent routing. Unclear requests are conversations, not writes."""
import re


# 求评价、求解释的问法：一律当讨论，句子里同时出现动词也不改。
ASK_HARD = re.compile(
    r'怎么样|怎样|如何|好不好|好吗|为什么|怎么|哪里|哪些|哪个|什么|是否|是不是'
    r'|行不行|合不合适|对不对|值得|要不要|更好|更合适'
    r'|[？?]|(?:吗|么)[啊呀呢吧。！!\s]*$')
# 只是提到了「讨论」「建议」「分析」这些话题词，不等于这句话在提问。
# 「按已讨论的建议修改」里两个词都有——按旧写法它会被判成只讨论，一个字都不会改。
# 所以这类词降级：单独出现算讨论，跟明确的改动指令同时出现时听指令。
ASK_SOFT = re.compile(r'建议|能不能|可不可以|讨论|聊聊|分析|评价|解释|觉得')
NO_WRITE = re.compile(r'先别|暂不|不要(?:直接)?(?:改|修改)|不(?:用|需要)(?:先|直接)?(?:改|修改)')
EDIT_WORDS = re.compile(
    r'修改|改成|改为|改一下|改改|改掉|再改|重新改|帮.{0,3}改|给.{0,3}改|调整|替换|删除|移除'
    r'|新增|增加|添加|优化|修复|修正|统一|重排|重做|制作|搭建|生成|创建|处理.*(?:意见|标注)'
    r'|加粗|加大|变大|变小|放大|缩小|对齐|居中|靠左|靠右|换成|挪到|移到|设成|设为|去掉|隐藏'
    r'|展开|收起|插入|插到|加个|加一个|加上|做个|做一个|补个|补一个|换个|换一个|排成|拆成|合并'
    # 追问式微调：「再小一点点」「稍微宽一点」——上一轮改过的东西接着调
    r'|(?:再|稍微|略)[^，。；\s]{0,4}(?:小|大|宽|窄|高|矮|粗|细|紧|松|深|浅|多|少)一?点'
    # 以光秃秃的动词收尾：「按刚才讨论的改」「这几处都调整」
    r'|(?:改|调整|删掉|去掉|对齐|统一)\s*[。！!~]?$')
# 词表穷举不完。祈使句还可以按句子结构认：「把/将/给 …」开头，或者直接以动词开头（「加千分位」）。
EDIT_HEAD = re.compile(
    r'^\s*(?:请|帮我|帮忙|麻烦)*\s*(?:把|将)\s*\S'
    r'|^\s*(?:请|帮我|帮忙|麻烦)*\s*(?:加(?!载)|添|删|换|改(?!天)|调|移|设|做|补)\S')
ASK_EN = re.compile(r'\b(review|discuss|explain|why|how|suggest|feedback|what|should|could)\b', re.I)
EDIT_EN = re.compile(r'\b(change|replace|remove|delete|add|fix|create|implement|update)\b', re.I)


# 一次丢过来一大段、还分了好几行的，通常是需求清单而不是一条指令。
# 这种东西直接开干最亏：跑十分钟做出来的东西方向就不对。先对齐再动手。
# 用户明确选了「直接改」时 intent 已经是 edit，根本走不到这里，所以不会挡他的路。
BRIEF_MIN_CHARS = 100   # 中文一个字顶英文三四个，按中文定
BRIEF_MIN_LINES = 3


def looks_like_brief(text: str) -> bool:
    lines = [l for l in text.splitlines() if l.strip()]
    return len(text) >= BRIEF_MIN_CHARS and len(lines) >= BRIEF_MIN_LINES


def resolve_intent(message: str, intent: str = 'auto') -> str:
    if intent in {'discuss', 'edit'}:
        return intent
    text = message.strip()
    if looks_like_brief(text):
        return 'discuss'
    # 明说了别改、或者本身就是个问句，一律讨论。
    if NO_WRITE.search(text) or ASK_HARD.search(text) or ASK_EN.search(text):
        return 'discuss'
    # 再看有没有明确的改动指令。放在软问法之前——「按你的建议改一下」听后半句。
    if EDIT_WORDS.search(text) or EDIT_HEAD.search(text) or EDIT_EN.search(text):
        return 'edit'
    if ASK_SOFT.search(text):
        return 'discuss'
    return 'discuss'


# 「这个」「这里」这类指代词，指的是用户此刻在屏幕上看着的东西。
# 没有点选就没有指代——模型再聪明也只能在几十万字符里瞎猜。
# 实测过一次：用户说「这个我想要点击有介绍内容」，模型搜了八轮才说出
# 「你这个没有指代，我无法确定改哪个元素」。这句话该在第一秒说，不该烧八轮。
PLACE_WORDS = re.compile(r'这里|这儿|这块|这边|那里|那儿')
# 「这个」后面跟名词就是有指代的（这个按钮、那个表格）；跟动词、代词、标点或结尾就是空指。
BARE_THIS = re.compile(
    r'(?:这个|那个|这一个|它)\s*(?=[我你他她想要能可以怎太就还也是有加改换删弄做搞给，。！？!?、…]|$)')


def needs_target(message: str) -> bool:
    """这句话在指某个东西，但没告诉我们是哪个。"""
    text = (message or "").strip()
    if not text:
        return False
    return bool(PLACE_WORDS.search(text) or BARE_THIS.search(text))


def discussion_result(answer: str, suggestions=None) -> dict:
    answer = str(answer or '').strip()[:6000]
    if not answer:
        raise ValueError('请给出对用户问题的具体回答')
    choices = []
    for suggestion in (suggestions or [])[:3]:
        if not isinstance(suggestion, dict):
            continue
        label = str(suggestion.get('label') or '').strip()[:80]
        instruction = str(suggestion.get('instruction') or '').strip()[:1500]
        if label and instruction:
            choices.append({'label': label, 'instruction': instruction})
    return {'answer': answer, 'suggestions': choices}


def history_context(messages: list, page_id: str) -> list:
    history = []
    for message in messages:
        if message.get('page_id') != page_id or message.get('role') not in {'user', 'assistant'} or not message.get('content'):
            continue
        content = message['content'][:3000]
        for i, suggestion in enumerate((message.get('discussion') or {}).get('suggestions', [])):
            content += f"\n建议 {i+1}（尚未执行）：{suggestion['label']}；{suggestion['instruction']}"
        question = message.get('clarification')
        if question:
            content += '\n待确认选项：' + ' / '.join(question.get('options', []))
        history.append({'role': message['role'], 'content': content})
    return history[-10:]
