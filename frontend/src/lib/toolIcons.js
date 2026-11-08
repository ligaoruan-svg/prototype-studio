// 工具一步一行（参照 Claude 显示工具调用）：图标说明干的是哪类事，后面一小截灰字是它拿到了什么
import { Search, FileText, PencilLine, MousePointerClick, ListChecks, Bookmark, BookOpen, MessageSquare, Wrench, Eye, LayoutTemplate } from 'lucide-vue-next'

const ICONS = { search_source: Search, search_skill_file: Search, search_chats: Search, read_source_slice: FileText, read_region: FileText, read_component: FileText,
  read_skill: BookOpen, read_skill_file: BookOpen, inspect_page: LayoutTemplate, start_from_shell: LayoutTemplate, arch_gen: LayoutTemplate, apply_operations: PencilLine,
  verify_page: Eye, check_page: MousePointerClick, measure_page: Eye, update_plan: ListChecks, finish_step: ListChecks, remember: Bookmark, forget: Bookmark,
  ask_user: MessageSquare, answer_user: MessageSquare, report_result: MessageSquare }

export const iconOf = step => ICONS[step.tool] || Wrench
// 结果的第一句（「找到 3 处」「打开了 4 页：都正常」）
export const brief = step => /^\s*[{[]/.test(step.detail || '') ? '' : String(step.detail || '').split(/[\n：:；;，,]/)[0].slice(0, 24)
