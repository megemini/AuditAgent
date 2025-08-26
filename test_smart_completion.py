#!/usr/bin/env python3
"""
测试智能完成判断逻辑
"""

import asyncio
import json
import time
from app import answer_question_with_session, _should_continue_audit

def test_should_continue_audit():
    """测试智能判断函数"""
    print("🧪 测试智能判断函数...")
    
    # 模拟规则
    rules = [
        {"rule_name": "规则1", "rule_description": "时间限制"},
        {"rule_name": "规则2", "rule_description": "金额标准"},
        {"rule_name": "规则3", "rule_description": "发票完整性"}
    ]
    
    # 测试场景1：刚开始，应该继续
    messages1 = [
        {"role": "user", "content": "请审核发票"},
        {"role": "assistant", "content": "我将开始审核发票"}
    ]
    result1 = _should_continue_audit(messages1, rules, 1)
    print(f"场景1 - 刚开始: {result1} (应该为True)")
    
    # 测试场景2：部分验证，应该继续
    messages2 = [
        {"role": "user", "content": "请审核发票"},
        {"role": "assistant", "content": "验证规则1：时间限制 ✅ 符合"},
        {"role": "assistant", "content": "正在验证规则2..."}
    ]
    result2 = _should_continue_audit(messages2, rules, 3)
    print(f"场景2 - 部分验证: {result2} (应该为True)")
    
    # 测试场景3：完成验证，应该停止
    messages3 = [
        {"role": "user", "content": "请审核发票"},
        {"role": "assistant", "content": "规则1：✅ 符合，规则2：❌ 不符合，规则3：✅ 符合"},
        {"role": "assistant", "content": "最终审核报告：总规则数3条，符合规则2条，不符合规则1条，最终结论：部分通过"}
    ]
    result3 = _should_continue_audit(messages3, rules, 5)
    print(f"场景3 - 完成验证: {result3} (应该为False)")
    
    # 测试场景4：迭代过多，应该停止
    messages4 = [
        {"role": "user", "content": "请审核发票"},
        {"role": "assistant", "content": "正在验证..."}
    ]
    result4 = _should_continue_audit(messages4, rules, 12)
    print(f"场景4 - 迭代过多: {result4} (应该为False)")
    
    print("✅ 智能判断函数测试完成")

class MockClient:
    """模拟OpenAI客户端，测试智能完成"""
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
        print(f"🤖 AI调用 #{self.parent.call_count}")
        
        # 模拟逐步完成审核的过程
        if self.parent.call_count == 1:
            return MockResponse("开始审核发票", [MockToolCall("recognize_single_invoice", {})])
        elif self.parent.call_count == 2:
            return MockResponse("发票已识别，开始验证规则1", [MockToolCall("get_current_time", {})])
        elif self.parent.call_count == 3:
            return MockResponse("规则1：✅ 符合 - 时间在限制内\n开始验证规则2", [MockToolCall("query_city_tier", {"city": "北京"})])
        elif self.parent.call_count == 4:
            return MockResponse("规则2：❌ 不符合 - 金额超标\n开始验证规则3", None)
        elif self.parent.call_count == 5:
            return MockResponse("规则3：✅ 符合 - 发票信息完整", None)
        elif self.parent.call_count == 6:
            return MockResponse("""📋 最终审核报告
            
规则验证结果：
✅ 规则1：餐饮费报销时间限制 - 符合
❌ 规则2：一线城市餐饮费标准 - 不符合  
✅ 规则3：发票完整性要求 - 符合

📈 审核统计：
- 总规则数：3条
- 符合规则：2条
- 不符合规则：1条

🎯 最终结论：部分通过

💡 改进建议：调整金额至标准范围内""", None)
        else:
            return MockResponse("审核已完成，如有其他问题请提问", None)

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
    def __init__(self):
        self.connected_servers = ["test_server"]
        self.sessions = {"test_server": MockSession()}
    
    def get_all_tools(self):
        return [
            {"type": "function", "function": {"name": "recognize_single_invoice", "description": "识别发票", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "get_current_time", "description": "获取时间", "parameters": {"type": "object"}}},
            {"type": "function", "function": {"name": "query_city_tier", "description": "查询城市", "parameters": {"type": "object"}}}
        ]
    
    def get_server_for_tool(self, tool_name):
        return "test_server"

class MockSession:
    async def call_tool(self, tool_name, tool_args):
        await asyncio.sleep(0.1)
        return {"result": f"Tool {tool_name} executed"}

def test_smart_completion():
    """测试智能完成功能"""
    print("\n🧪 测试智能完成功能...")
    print("=" * 50)
    
    # 先测试判断函数
    test_should_continue_audit()
    
    print("\n🔄 测试完整审核流程...")
    
    # 模拟会话存储
    from app import session_store, global_mcp_client
    
    session_id = "test_smart"
    mock_client = MockClient()
    session_store[session_id] = {
        "client": mock_client,
        "model": "test-model",
        "reimbursement_rules": [
            {"rule_name": "餐饮费报销时间限制", "rule_description": "时间限制"},
            {"rule_name": "一线城市餐饮费标准", "rule_description": "金额标准"},
            {"rule_name": "发票完整性要求", "rule_description": "完整性"}
        ]
    }
    
    # 替换全局MCP客户端
    original_mcp_client = global_mcp_client
    global_mcp_client.__dict__.update(MockMCPClient().__dict__)
    
    try:
        question = "请审核这张发票"
        history = []
        
        step_count = 0
        final_history = None
        
        for empty_input, updated_history in answer_question_with_session(question, history, session_id, None):
            step_count += 1
            final_history = updated_history
            
            if updated_history:
                last_msg = updated_history[-1]
                content = last_msg.get('content', '')
                print(f"步骤{step_count}: {content[:80]}...")
        
        print(f"\n✅ 审核流程完成！")
        print(f"📊 统计:")
        print(f"  - AI调用次数: {mock_client.call_count}")
        print(f"  - 流式输出步骤: {step_count}")
        print(f"  - 最终历史长度: {len(final_history) if final_history else 0}")
        
        # 检查是否智能完成
        if final_history:
            final_content = " ".join([msg.get('content', '') for msg in final_history[-3:]])
            has_final_report = any(keyword in final_content for keyword in ["最终审核报告", "审核统计", "最终结论"])
            
            if has_final_report:
                print("✅ 智能判断成功！检测到完整的审核报告，正确停止了流程")
            else:
                print("⚠️ 可能未完成完整审核")
        
        # 验证AI调用次数是否合理
        if 4 <= mock_client.call_count <= 8:
            print("✅ AI调用次数合理，避免了无限循环")
        else:
            print(f"⚠️ AI调用次数可能不合理: {mock_client.call_count}")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 恢复原始MCP客户端
        global_mcp_client.__dict__.update(original_mcp_client.__dict__)

if __name__ == "__main__":
    test_smart_completion()
