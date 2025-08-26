#!/usr/bin/env python3
"""
测试避免重复验证的脚本
"""

import asyncio
import json
import time
from app import answer_question_with_session

class MockClient:
    """模拟OpenAI客户端，检测重复验证"""
    def __init__(self):
        self.call_count = 0
        self.chat = MockChat(self)
        self.validation_prompts = []  # 记录所有验证提示

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
        
        # 检查是否有验证提示
        last_message = messages[-1] if messages else {}
        content = last_message.get('content', '')
        if isinstance(content, list):
            content = str(content)
        
        # 记录验证相关的提示
        validation_keywords = ["逐条验证", "开始验证", "继续验证", "验证规则"]
        if any(keyword in content for keyword in validation_keywords):
            self.parent.validation_prompts.append({
                "call_number": self.parent.call_count,
                "content": content[:200] + "..." if len(content) > 200 else content
            })
            print(f"📋 检测到验证提示 #{len(self.parent.validation_prompts)}")
        
        # 模拟思考时间
        time.sleep(0.2)
        
        # 第一次调用：识别发票
        if self.parent.call_count == 1:
            return MockResponse(
                content="我将开始审核这张发票。首先识别发票信息。",
                tool_calls=[
                    MockToolCall("recognize_single_invoice", {"image_url": "test.jpg"})
                ]
            )
        
        # 第二次调用：开始逐条验证（应该只有一次这样的提示）
        elif self.parent.call_count == 2:
            return MockResponse(
                content="发票信息已识别。现在开始逐条验证规则。\n\n**验证规则1：餐饮费报销时间限制**\n需要获取当前时间进行对比。",
                tool_calls=[
                    MockToolCall("get_current_time", {})
                ]
            )
        
        # 第三次调用：验证下一条规则
        elif self.parent.call_count == 3:
            return MockResponse(
                content="**规则1验证结果**：✅ 符合\n\n**验证规则2：一线城市餐饮费标准**\n需要查询城市分级。",
                tool_calls=[
                    MockToolCall("query_city_tier", {"city": "北京"})
                ]
            )
        
        # 第四次调用：继续验证其他规则
        elif self.parent.call_count == 4:
            return MockResponse(
                content="**规则2验证结果**：❌ 不符合\n\n**验证规则3：发票完整性要求**\n基于已有信息验证。",
                tool_calls=None
            )
        
        # 第五次调用：最后一条规则和汇总
        elif self.parent.call_count == 5:
            return MockResponse(
                content="**规则3验证结果**：✅ 符合\n\n**验证规则4：业务合理性验证**\n基于发票内容判断。",
                tool_calls=None
            )
        
        # 第六次调用：最终汇总报告
        else:
            return MockResponse(
                content="""**规则4验证结果**：⚠️ 需注意

📋 **最终审核报告汇总**
- 规则1：✅ 符合
- 规则2：❌ 不符合  
- 规则3：✅ 符合
- 规则4：⚠️ 需注意

🎯 **最终结论**：部分通过""",
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
        await asyncio.sleep(0.3)
        
        if tool_name == "recognize_single_invoice":
            return {"invoice_info": {"amount": "500.00", "date": "2024-01-15", "city": "北京", "type": "餐饮费"}}
        elif tool_name == "get_current_time":
            return {"current_time": "2024-01-20 10:00:00", "timezone": "UTC+8"}
        elif tool_name == "query_city_tier":
            return {"city": tool_args.get("city", "未知"), "tier": "一线城市", "meal_allowance": "100元/餐"}
        else:
            return f"Unknown tool: {tool_name}"

def test_no_duplicate_validation():
    """测试避免重复验证功能"""
    print("🧪 开始测试避免重复验证功能...")
    print("=" * 60)
    
    # 模拟会话存储
    from app import session_store, global_mcp_client
    
    session_id = "test_no_duplicate"
    mock_client = MockClient()
    session_store[session_id] = {
        "client": mock_client,
        "model": "test-model",
        "reimbursement_rules": [
            {"rule_name": "餐饮费报销时间限制", "rule_description": "餐饮费必须在发生后7天内报销", "rule_category": "时间限制"},
            {"rule_name": "一线城市餐饮费标准", "rule_description": "一线城市餐饮费每餐不超过100元", "rule_category": "金额标准"},
            {"rule_name": "发票完整性要求", "rule_description": "发票必须包含完整的商户信息、金额、日期", "rule_category": "发票要求"},
            {"rule_name": "业务合理性验证", "rule_description": "餐饮费用必须有合理的业务用途说明", "rule_category": "业务规则"}
        ]
    }
    
    # 替换全局MCP客户端
    original_mcp_client = global_mcp_client
    global_mcp_client.__dict__.update(MockMCPClient().__dict__)
    
    try:
        # 测试参数
        question = "请审核这张发票"
        history = []
        file_upload = None
        
        print(f"📝 用户问题: {question}")
        print(f"📋 规则总数: {len(session_store[session_id]['reimbursement_rules'])}条")
        print("🔄 开始审核流程...")
        print("=" * 60)
        
        # 统计变量
        step = 0
        rule_validations = {}  # 记录每条规则被验证的次数
        
        # 调用流式处理函数
        for empty_input, updated_history in answer_question_with_session(question, history, session_id, file_upload):
            step += 1
            
            if updated_history:
                last_msg = updated_history[-1]
                content = last_msg.get('content', '')
                
                # 检测规则验证（统计每条规则被提到的次数）
                for i in range(1, 5):  # 4条规则
                    rule_pattern = f"规则{i}"
                    if rule_pattern in content:
                        rule_validations[rule_pattern] = rule_validations.get(rule_pattern, 0) + 1
                
                print(f"步骤 #{step}: {content[:80]}...")
        
        print(f"\n🎉 测试完成！")
        print("=" * 60)
        
        # 分析验证提示的数量
        print(f"📊 验证提示分析:")
        print(f"  - 总AI调用次数: {mock_client.call_count}")
        print(f"  - 验证提示次数: {len(mock_client.validation_prompts)}")
        
        if len(mock_client.validation_prompts) <= 1:
            print("✅ 验证提示控制良好！没有重复的验证提示")
        else:
            print("⚠️ 检测到多个验证提示，可能存在重复:")
            for i, prompt in enumerate(mock_client.validation_prompts):
                print(f"  提示{i+1} (调用#{prompt['call_number']}): {prompt['content']}")
        
        # 分析规则验证的频率
        print(f"\n📋 规则验证频率分析:")
        for rule, count in rule_validations.items():
            print(f"  - {rule}: 被提到 {count} 次")
            if count > 3:  # 如果某条规则被提到超过3次，可能有重复
                print(f"    ⚠️ 可能存在重复验证")
            else:
                print(f"    ✅ 验证频率正常")
        
        # 总体评估
        max_mentions = max(rule_validations.values()) if rule_validations else 0
        avg_mentions = sum(rule_validations.values()) / len(rule_validations) if rule_validations else 0
        
        print(f"\n🎯 总体评估:")
        print(f"  - 规则最大提及次数: {max_mentions}")
        print(f"  - 规则平均提及次数: {avg_mentions:.1f}")
        
        if max_mentions <= 3 and len(mock_client.validation_prompts) <= 1:
            print("✅ 重复验证问题已解决！")
            print("👍 AI按照逐条验证的方式工作，没有重复验证规则")
        else:
            print("⚠️ 仍可能存在重复验证问题，需要进一步优化")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 恢复原始MCP客户端
        global_mcp_client.__dict__.update(original_mcp_client.__dict__)

if __name__ == "__main__":
    test_no_duplicate_validation()
