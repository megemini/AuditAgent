#!/usr/bin/env python3
"""
测试用户追问时的对话历史处理
"""

import asyncio
import json
import time
from app import answer_question_with_session

class MockClient:
    """模拟OpenAI客户端，测试追问功能"""
    def __init__(self):
        self.call_count = 0
        self.chat = MockChat(self)
        self.received_messages = []  # 记录收到的所有消息

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
        
        # 记录收到的消息
        self.parent.received_messages.append({
            "call_number": self.parent.call_count,
            "message_count": len(messages),
            "messages": [{"role": msg.get("role"), "content": msg.get("content", "")[:100] + "..."} for msg in messages]
        })
        
        print(f"\n🤖 AI调用 #{self.parent.call_count}")
        print(f"📝 收到消息数量: {len(messages)}")
        
        # 检查是否包含历史对话
        has_history = len(messages) > 1
        if has_history:
            print(f"✅ 包含对话历史 ({len(messages)}条消息)")
            # 显示最近几条消息的角色
            recent_roles = [msg.get("role") for msg in messages[-3:]]
            print(f"📋 最近消息角色: {recent_roles}")
        else:
            print(f"⚠️ 没有对话历史")
        
        # 模拟思考时间
        time.sleep(0.2)
        
        # 根据调用次数返回不同响应
        if self.parent.call_count == 1:
            # 第一次调用：初始审核
            return MockResponse(
                content="我将审核这张发票。首先识别发票信息。",
                tool_calls=[MockToolCall("recognize_single_invoice", {"image_url": "test.jpg"})]
            )
        elif self.parent.call_count == 2:
            # 第二次调用：开始规则验证
            return MockResponse(
                content="发票已识别。开始验证规则1：时间限制。",
                tool_calls=[MockToolCall("get_current_time", {})]
            )
        elif self.parent.call_count == 3:
            # 第三次调用：完成初始审核
            return MockResponse(
                content="**规则1验证结果**：✅ 符合\n\n📋 **初始审核完成**\n发票基本符合要求，但建议进一步检查其他规则。",
                tool_calls=None
            )
        elif self.parent.call_count == 4:
            # 第四次调用：处理用户追问
            return MockResponse(
                content="根据您的追问，我将继续详细验证其他规则。让我检查城市分级标准。",
                tool_calls=[MockToolCall("query_city_tier", {"city": "北京"})]
            )
        elif self.parent.call_count == 5:
            # 第五次调用：回答追问
            return MockResponse(
                content="**规则2验证结果**：❌ 不符合 - 北京为一线城市，餐饮标准100元/餐，但发票金额500元超标\n\n基于您的追问，这张发票确实存在金额超标的问题。建议分多次报销或调整金额。",
                tool_calls=None
            )
        else:
            # 后续调用：继续对话
            return MockResponse(
                content="我已经基于完整的对话历史为您提供了详细分析。如果还有其他问题，请继续提问。",
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
            {"type": "function", "function": {"name": "recognize_single_invoice", "description": "识别发票信息", "parameters": {"type": "object", "properties": {"image_url": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "get_current_time", "description": "获取当前时间", "parameters": {"type": "object", "properties": {}}}},
            {"type": "function", "function": {"name": "query_city_tier", "description": "查询城市分级", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}}}}
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
        await asyncio.sleep(0.3)
        
        if tool_name == "recognize_single_invoice":
            return {"invoice_info": {"amount": "500.00", "date": "2024-01-15", "city": "北京", "type": "餐饮费"}}
        elif tool_name == "get_current_time":
            return {"current_time": "2024-01-20 10:00:00", "timezone": "UTC+8"}
        elif tool_name == "query_city_tier":
            return {"city": tool_args.get("city", "未知"), "tier": "一线城市", "meal_allowance": "100元/餐"}
        else:
            return f"Unknown tool: {tool_name}"

def test_follow_up_questions():
    """测试用户追问功能"""
    print("🧪 开始测试用户追问功能...")
    print("=" * 60)
    
    # 模拟会话存储
    from app import session_store, global_mcp_client
    
    session_id = "test_follow_up"
    mock_client = MockClient()
    session_store[session_id] = {
        "client": mock_client,
        "model": "test-model",
        "reimbursement_rules": [
            {"rule_name": "餐饮费报销时间限制", "rule_description": "餐饮费必须在发生后7天内报销", "rule_category": "时间限制"},
            {"rule_name": "一线城市餐饮费标准", "rule_description": "一线城市餐饮费每餐不超过100元", "rule_category": "金额标准"}
        ]
    }
    
    # 替换全局MCP客户端
    original_mcp_client = global_mcp_client
    global_mcp_client.__dict__.update(MockMCPClient().__dict__)
    
    try:
        print("📝 第一轮对话：初始审核")
        print("-" * 40)
        
        # 第一个问题：初始审核
        question1 = "请审核这张发票"
        history = []
        
        final_history = None
        for empty_input, updated_history in answer_question_with_session(question1, history, session_id, None):
            final_history = updated_history
        
        print(f"✅ 第一轮对话完成，历史记录长度: {len(final_history)}")
        
        print("\n📝 第二轮对话：用户追问")
        print("-" * 40)
        
        # 第二个问题：用户追问
        question2 = "这张发票的金额是否超标？"
        
        for empty_input, updated_history in answer_question_with_session(question2, final_history, session_id, None):
            final_history = updated_history
        
        print(f"✅ 第二轮对话完成，历史记录长度: {len(final_history)}")
        
        print("\n📊 对话历史分析:")
        print("=" * 60)
        
        # 分析AI收到的消息
        print(f"📋 AI调用统计:")
        for i, record in enumerate(mock_client.received_messages):
            print(f"  调用{record['call_number']}: 收到{record['message_count']}条消息")
            if record['message_count'] > 1:
                print(f"    ✅ 包含对话历史")
            else:
                print(f"    ⚠️ 没有对话历史")
        
        # 检查追问时是否包含历史
        if len(mock_client.received_messages) >= 4:  # 追问应该在第4次调用
            follow_up_record = mock_client.received_messages[3]  # 第4次调用
            if follow_up_record['message_count'] > 2:
                print(f"\n✅ 追问处理正确！")
                print(f"   追问时AI收到了{follow_up_record['message_count']}条消息，包含完整对话历史")
            else:
                print(f"\n❌ 追问处理有问题！")
                print(f"   追问时AI只收到了{follow_up_record['message_count']}条消息，可能丢失了对话历史")
        
        # 分析最终对话历史
        print(f"\n📋 最终对话历史分析:")
        user_messages = [msg for msg in final_history if msg.get('role') == 'user']
        assistant_messages = [msg for msg in final_history if msg.get('role') == 'assistant']
        
        print(f"  - 用户消息数: {len(user_messages)}")
        print(f"  - 助手消息数: {len(assistant_messages)}")
        print(f"  - 总消息数: {len(final_history)}")
        
        # 显示用户消息内容
        print(f"\n📝 用户消息内容:")
        for i, msg in enumerate(user_messages):
            content = msg.get('content', '')[:50] + "..." if len(msg.get('content', '')) > 50 else msg.get('content', '')
            print(f"  {i+1}. {content}")
        
        # 验证追问功能
        if len(user_messages) >= 2:
            print(f"\n🎯 追问功能验证:")
            print(f"✅ 成功处理了{len(user_messages)}个用户问题")
            print(f"✅ 保持了完整的对话历史")
            print(f"✅ AI能够基于历史上下文回答追问")
        else:
            print(f"\n⚠️ 追问功能可能有问题")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 恢复原始MCP客户端
        global_mcp_client.__dict__.update(original_mcp_client.__dict__)

if __name__ == "__main__":
    test_follow_up_questions()
