#!/usr/bin/env python3
"""
测试避免重复审核的脚本
"""

import asyncio
import json
import time
from app import answer_question_with_session, _should_continue_audit

def test_should_continue_logic():
    """测试智能判断逻辑"""
    print("🧪 测试智能判断逻辑...")
    
    rules = [
        {"rule_name": "规则1", "rule_description": "时间限制"},
        {"rule_name": "规则2", "rule_description": "金额标准"},
        {"rule_name": "规则3", "rule_description": "发票完整性"}
    ]
    
    # 测试场景1：所有规则已完成，应该停止
    messages_completed = [
        {"role": "user", "content": "请审核发票"},
        {"role": "assistant", "content": "规则1：✅ 符合 - 时间在限制内"},
        {"role": "assistant", "content": "规则2：❌ 不符合 - 金额超标"},
        {"role": "assistant", "content": "规则3：✅ 符合 - 发票完整"},
        {"role": "assistant", "content": "📋 最终审核报告 总规则数：3条 符合规则：2条 不符合规则：1条"}
    ]
    result1 = _should_continue_audit(messages_completed, rules, 5)
    print(f"场景1 - 所有规则已完成: {result1} (应该为False)")
    
    # 测试场景2：有最终报告，应该停止
    messages_with_report = [
        {"role": "user", "content": "请审核发票"},
        {"role": "assistant", "content": "规则1：✅ 符合"},
        {"role": "assistant", "content": "📊 审核统计：总规则数3条，符合2条"}
    ]
    result2 = _should_continue_audit(messages_with_report, rules, 3)
    print(f"场景2 - 有最终报告: {result2} (应该为False)")
    
    # 测试场景3：规则重复提及过多，应该停止
    messages_repeated = [
        {"role": "user", "content": "请审核发票"},
        {"role": "assistant", "content": "规则1 规则2 规则3 规则1 规则2 规则3 规则1 规则2 规则3"}
    ]
    result3 = _should_continue_audit(messages_repeated, rules, 4)
    print(f"场景3 - 规则重复过多: {result3} (应该为False)")
    
    # 测试场景4：正常进行中，应该继续
    messages_in_progress = [
        {"role": "user", "content": "请审核发票"},
        {"role": "assistant", "content": "规则1：✅ 符合 - 时间在限制内"},
        {"role": "assistant", "content": "正在验证规则2..."}
    ]
    result4 = _should_continue_audit(messages_in_progress, rules, 2)
    print(f"场景4 - 正常进行中: {result4} (应该为True)")
    
    print("✅ 智能判断逻辑测试完成\n")

class MockClient:
    """模拟OpenAI客户端，测试重复审核问题"""
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
        
        print(f"🤖 AI调用 #{self.parent.call_count}")
        
        # 检查消息中是否包含已完成的审核内容
        full_content = " ".join([msg.get("content", "") for msg in messages if isinstance(msg.get("content"), str)])
        has_completed_audit = "最终审核报告" in full_content or "审核统计" in full_content
        
        if has_completed_audit:
            print("⚠️ 检测到已完成的审核内容，AI不应该重新审核")
        
        # 模拟完整的审核流程
        if self.parent.call_count == 1:
            return MockResponse("开始审核发票", [MockToolCall("recognize_single_invoice", {})])
        elif self.parent.call_count == 2:
            return MockResponse("发票已识别，验证规则1：时间限制", [MockToolCall("get_current_time", {})])
        elif self.parent.call_count == 3:
            return MockResponse("规则1：✅ 符合 - 时间在限制内\n验证规则2：金额标准", [MockToolCall("query_city_tier", {"city": "北京"})])
        elif self.parent.call_count == 4:
            return MockResponse("规则2：❌ 不符合 - 金额超标\n验证规则3：发票完整性", None)
        elif self.parent.call_count == 5:
            return MockResponse("规则3：✅ 符合 - 发票信息完整", None)
        elif self.parent.call_count == 6:
            return MockResponse("""📋 最终审核报告

📊 规则验证结果：
✅ 规则1：餐饮费报销时间限制 - 符合
❌ 规则2：一线城市餐饮费标准 - 不符合  
✅ 规则3：发票完整性要求 - 符合

📈 审核统计：
- 总规则数：3条
- 符合规则：2条
- 不符合规则：1条

🎯 最终结论：部分通过""", None)
        else:
            # 如果还有第7次及以后的调用，说明有重复审核问题
            print("❌ 检测到重复审核！系统应该在第6次调用后停止")
            return MockResponse("审核已完成，不应该重复进行", None)

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

def test_no_repeat_audit():
    """测试避免重复审核功能"""
    print("🧪 测试避免重复审核功能...")
    print("=" * 50)
    
    # 先测试判断逻辑
    test_should_continue_logic()
    
    # 模拟会话存储
    from app import session_store, global_mcp_client
    
    session_id = "test_no_repeat"
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
        
        print("🔄 开始审核流程...")
        for empty_input, updated_history in answer_question_with_session(question, history, session_id, None):
            step_count += 1
            final_history = updated_history
            
            if updated_history:
                last_msg = updated_history[-1]
                content = last_msg.get('content', '')
                print(f"步骤{step_count}: {content[:60]}...")
        
        print(f"\n✅ 审核流程完成！")
        print("=" * 50)
        print(f"📊 结果统计:")
        print(f"  - AI调用次数: {mock_client.call_count}")
        print(f"  - 流式输出步骤: {step_count}")
        
        # 检查是否避免了重复审核
        if mock_client.call_count <= 7:  # 正常应该在6-7次内完成
            print("✅ 成功避免重复审核！AI调用次数合理")
        else:
            print(f"❌ 可能存在重复审核问题，AI调用次数过多: {mock_client.call_count}")
        
        # 检查最终结果
        if final_history:
            final_content = " ".join([msg.get('content', '') for msg in final_history[-3:]])
            has_final_report = any(keyword in final_content for keyword in ["最终审核报告", "审核统计", "最终结论"])
            
            if has_final_report:
                print("✅ 生成了完整的最终审核报告")
            else:
                print("⚠️ 可能缺少完整的最终报告")
            
            # 检查规则验证情况
            rule_mentions = {}
            for msg in final_history:
                content = msg.get('content', '')
                for i in range(1, 4):  # 3条规则
                    if f"规则{i}" in content:
                        rule_mentions[f"规则{i}"] = rule_mentions.get(f"规则{i}", 0) + 1
            
            print(f"📋 规则提及统计:")
            for rule, count in rule_mentions.items():
                print(f"  - {rule}: {count}次")
                if count > 3:
                    print(f"    ⚠️ 提及次数过多，可能有重复")
                else:
                    print(f"    ✅ 提及次数正常")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 恢复原始MCP客户端
        global_mcp_client.__dict__.update(original_mcp_client.__dict__)

if __name__ == "__main__":
    test_no_repeat_audit()
