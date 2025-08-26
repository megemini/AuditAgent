#!/usr/bin/env python3
"""
测试AI思考提示功能的脚本
"""

import asyncio
import json
import time
from app import answer_question_with_session

class MockClient:
    """模拟OpenAI客户端，模拟思考时间"""
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
        
        # 模拟AI思考时间（更长的延迟）
        print(f"🤖 AI开始思考... (第{self.parent.call_count}次调用)")
        time.sleep(2)  # 模拟2秒的思考时间
        print(f"💡 AI思考完成!")
        
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
        print(f"🔧 开始执行工具: {tool_name}")
        
        # 模拟工具执行时间
        await asyncio.sleep(1.5)
        
        print(f"✅ 工具执行完成: {tool_name}")
        
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

def test_thinking_indicator():
    """测试AI思考提示功能"""
    print("🧪 开始测试AI思考提示功能...")
    print("=" * 60)
    
    # 模拟会话存储
    from app import session_store, global_mcp_client
    
    session_id = "test_thinking"
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
        
        print(f"📝 用户问题: {question}")
        print("🔄 开始流式处理...")
        print("=" * 60)
        
        # 调用流式处理函数
        step = 0
        thinking_steps = 0
        tool_steps = 0
        
        for empty_input, updated_history in answer_question_with_session(question, history, session_id, file_upload):
            step += 1
            
            if updated_history:
                last_msg = updated_history[-1]
                content = last_msg.get('content', '')
                role = last_msg.get('role', '')
                metadata = last_msg.get('metadata', {})
                
                print(f"\n📊 步骤 #{step}")
                print(f"👤 角色: {role}")
                print(f"💬 内容: {content}")
                
                if metadata:
                    status = metadata.get('status', '')
                    title = metadata.get('title', '')
                    print(f"📋 状态: {status}")
                    print(f"🏷️  标题: {title}")
                    
                    # 统计不同类型的步骤
                    if "思考" in title:
                        thinking_steps += 1
                        print("🤔 → 用户看到AI正在思考...")
                    elif "Tool:" in title:
                        tool_steps += 1
                        if status == "pending":
                            print("🔧 → 用户看到工具正在执行...")
                        elif status == "done":
                            print("✅ → 用户看到工具执行完成...")
                        elif status == "error":
                            print("❌ → 用户看到工具执行失败...")
                
                print("-" * 40)
        
        print(f"\n🎉 测试完成！")
        print(f"📊 总步骤数: {step}")
        print(f"🤔 思考提示次数: {thinking_steps}")
        print(f"🔧 工具调用次数: {tool_steps}")
        
        # 验证思考提示是否正常工作
        if thinking_steps > 0:
            print("✅ AI思考提示功能正常工作！")
            print("👍 用户现在可以看到AI何时在思考")
        else:
            print("⚠️ 未检测到思考提示")
        
        # 验证工具状态更新是否正常
        if tool_steps > 0:
            print("✅ 工具状态更新功能正常工作！")
            print("👍 用户可以看到工具从pending到done的状态变化")
        else:
            print("⚠️ 未检测到工具状态更新")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 恢复原始MCP客户端
        global_mcp_client.__dict__.update(original_mcp_client.__dict__)

if __name__ == "__main__":
    test_thinking_indicator()
