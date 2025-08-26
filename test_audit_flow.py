#!/usr/bin/env python3
"""
测试发票审核多步骤流程的脚本
"""

import asyncio
import json
from app import _process_query_with_tools

class MockClient:
    """模拟OpenAI客户端，模拟多步骤审核流程"""
    def __init__(self):
        self.call_count = 0
        self.chat = MockChat(self)

class MockChat:
    def __init__(self, parent):
        self.parent = parent
        self.completions = MockCompletions(parent)

class MockCompletions:
    def __init__(self, parent):
        self.parent = parent
        
    def create(self, **kwargs):
        self.parent.call_count += 1
        messages = kwargs.get('messages', [])
        
        print(f"\n🤖 AI调用 #{self.parent.call_count}")
        print(f"📝 消息数量: {len(messages)}")
        if messages:
            last_msg = messages[-1]
            content = last_msg.get('content', '')
            if isinstance(content, list):
                content = str(content)
            print(f"📄 最后消息内容: {content[:200]}...")
        
        # 第一次调用：识别发票
        if self.parent.call_count == 1:
            return MockResponse(
                content="我将开始审核这张发票。首先需要识别发票信息。",
                tool_calls=[
                    MockToolCall("recognize_single_invoice", {"image_url": "test.jpg"})
                ]
            )
        
        # 第二次调用：检查时间
        elif self.parent.call_count == 2:
            return MockResponse(
                content="发票信息已识别。现在需要检查报销时间是否超时。",
                tool_calls=[
                    MockToolCall("get_current_time", {})
                ]
            )
        
        # 第三次调用：检查城市分级
        elif self.parent.call_count == 3:
            return MockResponse(
                content="时间检查完成。现在需要查询发票城市的分级标准。",
                tool_calls=[
                    MockToolCall("query_city_tier", {"city": "北京"})
                ]
            )
        
        # 第四次调用：最终分析
        else:
            return MockResponse(
                content="基于所有工具调用的结果，我现在可以给出完整的审核报告：\n\n**审核结论**：通过\n**详细分析**：\n1. 发票信息完整\n2. 报销时间未超时\n3. 城市分级标准符合要求\n4. 金额在允许范围内",
                tool_calls=None
            )

class MockResponse:
    def __init__(self, content, tool_calls=None):
        self.choices = [MockChoice(content, tool_calls)]

class MockChoice:
    def __init__(self, content, tool_calls=None):
        self.message = MockMessage(content, tool_calls)

class MockMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

class MockToolCall:
    def __init__(self, name, args):
        self.id = f"call_{name}_{len(args)}"
        self.function = MockFunction(name, args)

class MockFunction:
    def __init__(self, name, args):
        self.name = name
        self.arguments = json.dumps(args)

class MockMCPClient:
    def __init__(self):
        self.connected_servers = ["invoice_server", "datetime_server", "citytier_server"]
        self.sessions = {
            "invoice_server": MockSession(),
            "datetime_server": MockSession(),
            "citytier_server": MockSession()
        }
    
    def get_all_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "recognize_single_invoice",
                    "description": "识别发票信息",
                    "parameters": {"type": "object", "properties": {"image_url": {"type": "string"}}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "获取当前时间",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "query_city_tier",
                    "description": "查询城市分级",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}
                }
            }
        ]
    
    def get_server_for_tool(self, tool_name):
        if tool_name == "recognize_single_invoice":
            return "invoice_server"
        elif tool_name == "get_current_time":
            return "datetime_server"
        elif tool_name == "query_city_tier":
            return "citytier_server"
        return None

class MockSession:
    async def call_tool(self, tool_name, tool_args):
        print(f"🔧 执行工具: {tool_name}, 参数: {tool_args}")
        
        if tool_name == "recognize_single_invoice":
            return {
                "invoice_info": {
                    "amount": "500.00",
                    "date": "2024-01-15",
                    "city": "北京",
                    "type": "餐饮费",
                    "vendor": "某餐厅"
                }
            }
        elif tool_name == "get_current_time":
            return {
                "current_time": "2024-01-20 10:00:00",
                "timezone": "UTC+8"
            }
        elif tool_name == "query_city_tier":
            return {
                "city": tool_args.get("city", "未知"),
                "tier": "一线城市",
                "meal_allowance": "100元/餐"
            }
        else:
            return f"Unknown tool: {tool_name}"

async def test_audit_flow():
    """测试完整的发票审核流程"""
    print("🧪 开始测试发票审核多步骤流程...")
    
    # 创建模拟对象
    mock_client = MockClient()
    mock_mcp_client = MockMCPClient()
    
    # 测试参数
    question = "请审核这张发票是否符合报销规定"
    history = []
    session_id = "test_session"
    file_upload = None  # 模拟有文件上传
    model = "test-model"
    reimbursement_rules = [
        {
            "rule_name": "餐饮费报销时间限制",
            "rule_description": "餐饮费必须在发生后7天内报销",
            "rule_category": "时间限制"
        },
        {
            "rule_name": "一线城市餐饮费标准",
            "rule_description": "一线城市餐饮费每餐不超过100元",
            "rule_category": "金额标准"
        },
        {
            "rule_name": "发票完整性要求",
            "rule_description": "发票必须包含完整的商户信息、金额、日期",
            "rule_category": "发票要求"
        }
    ]
    
    try:
        # 调用审核流程
        result_messages = await _process_query_with_tools(
            question, history, session_id, file_upload, 
            mock_client, model, reimbursement_rules, mock_mcp_client
        )
        
        print(f"\n✅ 测试完成！")
        print(f"📊 总AI调用次数: {mock_client.call_count}")
        print(f"📝 返回消息数量: {len(result_messages)}")
        
        # 统计工具调用
        tool_calls = {}
        for msg in result_messages:
            content = msg.get('content', '')
            if '使用工具:' in content:
                tool_name = content.split('使用工具:')[1].strip()
                tool_calls[tool_name] = tool_calls.get(tool_name, 0) + 1
        
        print(f"\n🔧 工具调用统计:")
        for tool, count in tool_calls.items():
            print(f"  - {tool}: {count}次")
        
        # 检查是否实现了多步骤流程
        expected_tools = ["recognize_single_invoice", "get_current_time", "query_city_tier"]
        found_tools = list(tool_calls.keys())
        
        print(f"\n📋 流程检查:")
        print(f"期望的工具: {expected_tools}")
        print(f"实际调用的工具: {found_tools}")
        
        if all(tool in found_tools for tool in expected_tools):
            print("✅ 成功实现多步骤审核流程！")
        else:
            print("⚠️ 未完成所有预期的审核步骤")
            
        # 显示最终结果
        print(f"\n📄 最终审核结果:")
        final_messages = [msg for msg in result_messages if msg.get('role') == 'assistant' and '审核' in msg.get('content', '')]
        for msg in final_messages[-1:]:  # 显示最后一条审核消息
            print(f"  {msg.get('content', '')[:300]}...")
            
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_audit_flow())
