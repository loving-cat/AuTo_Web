"""
MCP Server for Playwright Automation Tools

提供基于视觉语言模型的智能页面元素分析工具，以及自动化测试执行工具

使用方法:
    python mcp_server.py

工具列表:
    页面分析工具:
    - check_web_element: 分析页面元素并返回结构化信息
    - find_missing_elements: 查缺补漏，重新定位缺失元素
    - get_element_locator: 获取元素定位器
    - list_all_elements: 列出所有元素
    
    测试执行工具:
    - run_debug_test: 执行单网站调试测试
    - run_concurrent_test: 执行并发压力测试
    - generate_test_questions: 基于知识库生成测试问题
"""

import asyncio
import json
import os
import sys
from typing import Any, Optional, List

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 导入统一配置（使用绝对导入避免冲突）
from MCP_Server.config import get_vision_api_config

# 导入核心工具
from MCP_Server.lib.PlayWright.checkWeb.check_web_element import (
    CheckWebElementResult,
    check_web_element_tool,
    find_missing_elements
)

# 导入统一工具接口
from MCP_Server.tools_api import (
    run_debug_test as _run_debug_test,
    run_concurrent_test as _run_concurrent_test,
    generate_questions_concurrent as _generate_questions,
    get_test_report
)


# ============== 配置 ==============

def get_config() -> dict:
    """获取配置（使用统一配置模块）"""
    return get_vision_api_config()


# ============== 全局状态 ==============

# 存储当前的 Playwright Page 对象引用
# 注意：MCP Server 需要与 Playwright 实例运行在同一进程中
_current_page = None
_last_result: Optional[CheckWebElementResult] = None


def set_current_page(page):
    """设置当前 Page 对象（供外部调用）"""
    global _current_page
    _current_page = page


def get_current_page():
    """获取当前 Page 对象"""
    return _current_page


# ============== MCP Server 定义 ==============

# 创建 MCP Server 实例
server = Server("playwright-vision-tools")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用工具"""
    return [
        Tool(
            name="check_web_element",
            description="""分析当前页面的所有可交互元素。

使用视觉语言模型 (qwen3-vl-plus) 对当前页面进行深度语义分析，
识别按钮、输入框、链接等交互元素，并返回：
- 元素的文本内容
- 业务含义（如"提交按钮"、"搜索框"）
- 元素类型和位置坐标
- 推荐的 Playwright 选择器

适用于：
- 页面元素探索和分析
- 自动化测试前的元素定位
- 页面结构理解""",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_dom": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否包含 DOM 结构作为辅助上下文"
                    },
                    "custom_prompt": {
                        "type": "string",
                        "default": "",
                        "description": "自定义分析提示词（可选）"
                    }
                }
            }
        ),
        Tool(
            name="find_missing_elements",
            description="""查缺补漏：检查目标元素是否被识别。

当某些关键元素未被识别时，使用此工具进行针对性搜索。
会根据目标描述重新分析页面，尝试定位缺失的元素。""",
            inputSchema={
                "type": "object",
                "properties": {
                    "target_elements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "目标元素描述列表，如 ['登录按钮', '搜索框', '提交']"
                    }
                },
                "required": ["target_elements"]
            }
        ),
        Tool(
            name="get_element_locator",
            description="""根据元素描述获取推荐的 Playwright 定位器。

在已分析的元素中搜索匹配的元素，返回最佳定位器。""",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_description": {
                        "type": "string",
                        "description": "元素描述，如 '登录按钮'、'搜索输入框'、'提交'"
                    }
                },
                "required": ["element_description"]
            }
        ),
        Tool(
            name="list_all_elements",
            description="""列出所有已识别的页面元素。

返回上次分析结果中的所有元素摘要信息。""",
            inputSchema={
                "type": "object",
                "properties": {
                    "element_type": {
                        "type": "string",
                        "default": "",
                        "description": "筛选元素类型：button/input/link/text/image/other"
                    }
                }
            }
        ),
        # ============== 测试执行工具 ==============
        Tool(
            name="run_debug_test",
            description="""执行单网站调试测试。

对单个网站进行自动化测试，使用预设的测试问题。
支持裁判模型评估回答精确率。

适用于：
- 单个网站的功能测试
- AI对话质量验证
- 问题回答准确性评估""",
            inputSchema={
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "测试问题列表"
                    },
                    "knowledge_content": {
                        "type": "string",
                        "default": "",
                        "description": "知识库内容（用于裁判评估）"
                    },
                    "session_id": {
                        "type": "string",
                        "default": "",
                        "description": "会话ID（用于多用户隔离）"
                    },
                    "bot_persona": {
                        "type": "string",
                        "default": "",
                        "description": "BOT人设风格（如\"二次元\"、\"专业客服\"等）"
                    }
                },
                "required": ["questions"]
            }
        ),
        Tool(
            name="run_concurrent_test",
            description="""执行并发压力测试。

同时对多个网站渠道进行并发测试，支持多Worker压力测试。
每个网站可启动多个Worker实例进行并发测试。

适用于：
- 多渠道并发测试
- 压力测试和性能评估
- 多网站对比测试""",
            inputSchema={
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "测试问题列表"
                    },
                    "target_sites": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "目标网站ID列表（可选，不填则测试所有网站）"
                    },
                    "workers_per_site": {
                        "type": "integer",
                        "default": 1,
                        "description": "每个网站的并发Worker数"
                    },
                    "knowledge_content": {
                        "type": "string",
                        "default": "",
                        "description": "知识库内容（用于裁判评估）"
                    },
                    "session_id": {
                        "type": "string",
                        "default": "",
                        "description": "会话ID（用于多用户隔离）"
                    },
                    "bot_persona": {
                        "type": "string",
                        "default": "",
                        "description": "BOT人设风格（如\"二次元\"、\"专业客服\"等）"
                    }
                },
                "required": ["questions"]
            }
        ),
        Tool(
            name="generate_test_questions",
            description="""基于知识库文档生成测试问题。

使用LLM根据文档内容智能生成测试问题。
支持单轮问题和多轮对话问题。
使用10个并发请求加速生成。

【重要】worker_type参数说明：
- "solo": 调试测试专用，问题保存到solo_worker目录
- "max": 渠道测试专用，问题保存到max_worker目录
- 不指定: 只返回问题列表，不保存文件""",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "知识库文档内容"
                    },
                    "count": {
                        "type": "integer",
                        "default": 10,
                        "description": "生成问题数量"
                    },
                    "multi_turn": {
                        "type": "integer",
                        "default": 1,
                        "description": "多轮对话轮数（1=单轮，2=两轮连续对话，3=三轮连续对话）"
                    },
                    "session_id": {
                        "type": "string",
                        "default": "",
                        "description": "会话ID（用于多用户隔离）"
                    },
                    "worker_type": {
                        "type": "string",
                        "default": "",
                        "description": "Worker类型：solo=调试测试专用，max=渠道测试专用"
                    }
                },
                "required": ["content"]
            }
        ),
        # ============== 报告工具 ==============
        Tool(
            name="get_test_report",
            description="""获取测试报告。

根据session_id获取对应的测试报告摘要。
支持获取solo_worker和max_worker的报告。""",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "default": "",
                        "description": "会话ID（用于多用户隔离）"
                    },
                    "report_type": {
                        "type": "string",
                        "default": "all",
                        "description": "报告类型：solo/max/all"
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """执行工具调用"""
    global _last_result
    
    page = get_current_page()
    
    if name == "check_web_element":
        if page is None:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "未设置当前 Page 对象。请先调用 set_current_page(page) 设置页面。"
                }, ensure_ascii=False)
            )]
        
        include_dom = arguments.get("include_dom", True)
        custom_prompt = arguments.get("custom_prompt", "") or None
        
        result = check_web_element_tool(
            page=page,
            include_dom=include_dom,
            custom_prompt=custom_prompt,
            config=get_config()
        )
        
        _last_result = CheckWebElementResult(**result)
        
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    elif name == "find_missing_elements":
        if page is None:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "未设置当前 Page 对象"
                }, ensure_ascii=False)
            )]
        
        if _last_result is None:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "没有之前的分析结果，请先调用 check_web_element"
                }, ensure_ascii=False)
            )]
        
        target_elements = arguments.get("target_elements", [])
        
        result = find_missing_elements(page, target_elements, _last_result)
        _last_result = result
        
        return [TextContent(
            type="text",
            text=json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
        )]
    
    elif name == "get_element_locator":
        if _last_result is None or not _last_result.success:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "没有可用的分析结果，请先调用 check_web_element"
                }, ensure_ascii=False)
            )]
        
        description = arguments.get("element_description", "").lower()
        
        # 搜索匹配的元素
        matches = []
        for elem in _last_result.elements:
            text_match = description in elem.text_content.lower()
            meaning_match = description in elem.semantic_meaning.lower()
            
            if text_match or meaning_match:
                matches.append({
                    "id": elem.id,
                    "text_content": elem.text_content,
                    "semantic_meaning": elem.semantic_meaning,
                    "element_type": elem.element_type,
                    "confidence": elem.confidence,
                    "suggested_playwright_locator": elem.suggested_playwright_locator,
                    "alternative_selector": elem.alternative_selector,
                    "match_score": 1.0 if text_match and meaning_match else 0.7
                })
        
        if matches:
            # 按匹配分数排序
            matches.sort(key=lambda x: x["match_score"], reverse=True)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": True,
                    "message": f"找到 {len(matches)} 个匹配元素",
                    "best_match": matches[0],
                    "all_matches": matches
                }, ensure_ascii=False, indent=2)
            )]
        else:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": f"未找到匹配 '{description}' 的元素",
                    "available_elements": [
                        {"id": e.id, "text": e.text_content, "meaning": e.semantic_meaning}
                        for e in _last_result.elements[:10]
                    ]
                }, ensure_ascii=False, indent=2)
            )]
    
    elif name == "list_all_elements":
        if _last_result is None or not _last_result.success:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "没有可用的分析结果，请先调用 check_web_element"
                }, ensure_ascii=False)
            )]
        
        element_type = arguments.get("element_type", "").lower()
        
        elements = _last_result.elements
        if element_type:
            elements = [e for e in elements if e.element_type.lower() == element_type]
        
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": True,
                "total_count": len(_last_result.elements),
                "filtered_count": len(elements),
                "elements": [
                    {
                        "id": e.id,
                        "text_content": e.text_content,
                        "semantic_meaning": e.semantic_meaning,
                        "element_type": e.element_type,
                        "locator": e.suggested_playwright_locator
                    }
                    for e in elements
                ]
            }, ensure_ascii=False, indent=2)
        )]
    
    # ============== 测试执行工具 ==============
    elif name == "run_debug_test":
        questions = arguments.get("questions", [])
        knowledge_content = arguments.get("knowledge_content", "")
        session_id = arguments.get("session_id", "")
        bot_persona = arguments.get("bot_persona", "")
        
        if not questions:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "请提供测试问题列表"
                }, ensure_ascii=False)
            )]
        
        # 执行调试测试
        result = _run_debug_test(
            questions=questions,
            knowledge_content=knowledge_content,
            session_id=session_id,
            bot_persona=bot_persona
        )
        
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    elif name == "run_concurrent_test":
        questions = arguments.get("questions", [])
        target_sites_raw = arguments.get("target_sites")
        workers_per_site = arguments.get("workers_per_site", 1)
        knowledge_content = arguments.get("knowledge_content", "")
        session_id = arguments.get("session_id", "")
        bot_persona = arguments.get("bot_persona", "")
        
        # 处理 target_sites 类型
        target_sites: Optional[List[int]] = None
        if target_sites_raw and isinstance(target_sites_raw, list):
            target_sites = [int(s) for s in target_sites_raw if isinstance(s, (int, float))]
        
        if not questions:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "请提供测试问题列表"
                }, ensure_ascii=False)
            )]
        
        # 执行并发测试
        result = _run_concurrent_test(
            questions=questions,
            target_sites=target_sites,
            workers_per_site=workers_per_site,
            knowledge_content=knowledge_content,
            session_id=session_id,
            bot_persona=bot_persona
        )
        
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    elif name == "generate_test_questions":
        content = arguments.get("content", "")
        count = arguments.get("count", 10)
        multi_turn = arguments.get("multi_turn", 1)
        session_id = arguments.get("session_id", "")
        worker_type = arguments.get("worker_type", "")
        
        if not content:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": "请提供知识库文档内容"
                }, ensure_ascii=False)
            )]
        
        # 并发生成问题
        questions, error = _generate_questions(
            content=content,
            count=count,
            multi_turn=multi_turn,
            session_id=session_id,
            worker_type=worker_type
        )
        
        if error:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": error
                }, ensure_ascii=False)
            )]
        
        result = {
            "success": True,
            "count": len(questions) if questions else 0,
            "multi_turn": multi_turn,
            "session_id": session_id,
            "questions": questions
        }
        if worker_type:
            result["worker_type"] = worker_type
        
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    elif name == "get_test_report":
        session_id = arguments.get("session_id", "")
        report_type = arguments.get("report_type", "all")
        
        result = get_test_report(
            session_id=session_id,
            report_type=report_type
        )
        
        return [TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2)
        )]
    
    else:
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": f"未知工具: {name}"
            }, ensure_ascii=False)
        )]


# ============== 启动入口 ==============

async def run_server():
    """运行 MCP Server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """主入口"""
    print("Starting Playwright Vision Tools MCP Server...", file=sys.stderr)
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
