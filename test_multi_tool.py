#!/usr/bin/env python3
"""
测试多工具调用功能的简单脚本
"""

import asyncio
import json
from app import _process_query_with_tools, FastMCPStdioClientWrapper

class MockClient:
    """模拟OpenAI客户端用于测试"""
    def __init__(self):
        self.call_count = 0
        self.chat = MockChat(self)

class MockChat:
    """模拟chat对象"""
    def __init__(self, parent):
        self.parent = parent
        self.completions = MockCompletions(parent)

class MockCompletions:
    """模拟completions对象"""
    def __init__(self, parent):
        self.parent = parent

    def create(self, **kwargs):
        self.parent.call_count += 1

        # 模拟第一次调用返回工具调用
        if self.parent.call_count == 1:
            return MockResponse(
                content="我需要使用工具来帮助您。",
                tool_calls=[
                    MockToolCall("query_city_tier", {"city": "北京"}),
                    MockToolCall("get_current_time", {})
                ]
            )
        # 模拟第二次调用返回最终结果
        else:
            return MockResponse(
                content="基于工具调用的结果，我可以为您提供详细的分析。",
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
        self.id = f"call_{name}"
        self.function = MockFunction(name, args)

class MockFunction:
    def __init__(self, name, args):
        self.name = name
        self.arguments = json.dumps(args)

class MockMCPClient:
    """模拟MCP客户端"""
    def __init__(self):
        self.connected_servers = ["test_server"]
        self.sessions = {"test_server": MockSession()}
    
    def get_all_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "query_city_tier",
                    "description": "查询城市分级",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "get_current_time",
                    "description": "获取当前时间",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
    
    def get_server_for_tool(self, tool_name):
        return "test_server"

class MockSession:
    """模拟MCP会话"""
    async def call_tool(self, tool_name, tool_args):
        if tool_name == "query_city_tier":
            return {"city": tool_args.get("city", "未知"), "tier": "一线城市"}
        elif tool_name == "get_current_time":
            return {"time": "2024-01-01 12:00:00", "timezone": "UTC+8"}
        else:
            return f"Unknown tool: {tool_name}"

async def test_multi_tool_calling():
    """测试多工具调用功能"""
    print("🧪 开始测试多工具调用功能...")
    
    # 创建模拟对象
    mock_client = MockClient()
    mock_mcp_client = MockMCPClient()
    
    # 测试参数
    question = "请查询北京的城市分级，并告诉我当前时间"
    history = []
    session_id = "test_session"
    file_upload = None
    model = "test-model"
    reimbursement_rules = [
        {"rule_name": "差旅费规则", "rule_description": "差旅费报销标准", "rule_category": "差旅费"}
    ]
    
    try:
        # 调用新的多工具处理函数
        result_messages = await _process_query_with_tools(
            question, history, session_id, file_upload, 
            mock_client, model, reimbursement_rules, mock_mcp_client
        )
        
        print(f"✅ 测试成功！")
        print(f"📊 AI调用次数: {mock_client.call_count}")
        print(f"📝 返回消息数量: {len(result_messages)}")
        
        print("\n📋 返回的消息:")
        for i, msg in enumerate(result_messages):
            print(f"  {i+1}. [{msg['role']}] {msg['content'][:100]}...")
            if 'metadata' in msg:
                print(f"     元数据: {msg['metadata']}")
        
        # 验证是否正确处理了多次工具调用
        tool_messages = [msg for msg in result_messages if "工具" in msg.get('content', '')]
        print(f"\n🔧 工具相关消息数量: {len(tool_messages)}")
        
        if mock_client.call_count >= 2:
            print("✅ 成功实现了多次AI调用")
        else:
            print("⚠️  只进行了一次AI调用")
            
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_multi_tool_calling())
