"""Stable user-facing error categories; diagnostics remain in local logs."""
import re


class WorkError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def error_payload(exc):
    detail = str(exc)[:1800]
    code = getattr(exc, 'code', '')
    if not code:
        if re.search(r'余额|密钥|401|403|402|quota|balance|insufficient|api.?key|authentication', detail, re.I):
            code = 'model_account'
        elif re.search(r'网络|timeout|timed out|connect|resolve host|network', detail, re.I):
            code = 'network'
        elif re.search(r'运行检查|脚本|校验', detail):
            code = 'validation'
        elif re.search(r'已.*更新|撤销记录|最近一步', detail):
            code = 'conflict'
        else:
            code = 'patch_target'
    messages = {
        'model_account': '模型账户或配置有问题，检查密钥、模型名称和余额后重试',
        'network': '没连上模型服务，检查网络后重试',
        'output_limit': '改动太大，一次没写完。请缩小范围或提高输出上限',
        'invalid_arguments': '模型返回的修改指令不完整，请缩小范围后重试',
        'internal': '工具内部出现错误，当前文件未改动。可查看本地服务日志后重试',
        'patch_target': '没找到可安全修改的位置，请重新点选后重试',
        'validation': '改完页面报错了，已保留上一版。可以让 AI 修复',
        'conflict': '页面已发生变化，请刷新后再修改',
        'iterations': '这次改动未能完成，请缩小到一个位置后重试',
        'stalled': '一直没定位到该改的地方，已停下。点选或框选目标后再说一次会准得多',
        'tool_rejected': '同一步反复没通过，已停下。换个说法或缩小到一个位置重试',
        'stopped': '已停止，当前文件没有改动',
        'busy': '模型服务暂时繁忙，已自动重试 3 次仍未成功，稍后再试；当前文件没有改动',
        'timeout': '模型 10 分钟都没写完，已放弃这一次（不再重试，免得重复计费）。请把需求拆小，或打开流式输出',
    }
    headline = messages.get(code)
    # 没登记的错误码以前直接回退成 detail，卡片标题和「查看详情」就是同一句话，
    # 看着像坏了。宁可只给一句，也不要重复一遍。
    return {'code': code, 'message': headline or detail,
            'detail': '' if headline is None else detail}
