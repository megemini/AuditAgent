#!/usr/bin/env python3
"""
测试流式输出功能的脚本
"""

import asyncio
import json
import time
from app import answer_question_with_session

class MockClient:
    """模拟OpenAI客户端，模拟流式响应"""
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
        
        # 模拟网络延迟
        time.sleep(0.5)
        
        print(f"\n🤖 AI调用 #{self.parent.call_count}")
        
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
        print(f"🔧 执行工具: {tool_name}")
        
        # 模拟工具执行时间
        await asyncio.sleep(1)
        
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

def test_streaming():
    """测试流式输出功能"""
    print("🧪 开始测试流式输出功能...")
    
    # 模拟会话存储
    from app import session_store, global_mcp_client
    
    session_id = "test_streaming"
    session_store[session_id] = {
        "client": MockClient(),
        "model": "test-model",
        "reimbursement_rules": [
            {
                "rule_name": "餐饮费报销时间限制",
                "rule_description": "餐饮费必须在发生后7天内报销",
                "rule_category": "时间限制"
            },
            {
                "rule_name": "一线城市餐饮费标准",
                "rule_description": "一线城市餐饮费每餐不超过100元",
                "rule_category": "金额标准"
            }
        ]
    }
    
    # 替换全局MCP客户端
    original_mcp_client = global_mcp_client
    global_mcp_client.__dict__.update(MockMCPClient().__dict__)
    
    try:
        # 测试参数
        question = "请审核这张发票是否符合报销规定"
        history = []
        file_upload = None
        
        print(f"📝 开始处理问题: {question}")
        print("=" * 50)
        
        # 调用流式处理函数
        step = 0
        for empty_input, updated_history in answer_question_with_session(question, history, session_id, file_upload):
            step += 1
            print(f"\n📊 流式输出步骤 #{step}")
            print(f"📝 历史记录长度: {len(updated_history)}")
            
            if updated_history:
                last_msg = updated_history[-1]
                content = last_msg.get('content', '')
                role = last_msg.get('role', '')
                metadata = last_msg.get('metadata', {})
                
                print(f"👤 角色: {role}")
                print(f"💬 内容: {content[:100]}...")
                if metadata:
                    print(f"📋 元数据: {metadata}")
                print("-" * 30)
        
        print(f"\n✅ 流式输出测试完成！")
        print(f"📊 总共输出了 {step} 个步骤")
        
        # 检查最终结果
        if updated_history:
            final_messages = [msg for msg in updated_history if '审核' in msg.get('content', '')]
            if final_messages:
                print(f"\n📄 最终审核结果:")
                print(final_messages[-1].get('content', '')[:200] + "...")
            
            # 统计工具调用
            tool_messages = [msg for msg in updated_history if '使用工具:' in msg.get('content', '')]
            print(f"\n🔧 工具调用次数: {len(tool_messages)}")
            for msg in tool_messages:
                print(f"  - {msg.get('content', '')}")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 恢复原始MCP客户端
        global_mcp_client.__dict__.update(original_mcp_client.__dict__)

if __name__ == "__main__":
    test_streaming()
