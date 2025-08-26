#!/usr/bin/env python3
"""
测试逐条验证审核功能的脚本
"""

import asyncio
import json
import time
from app import answer_question_with_session

class MockClient:
    """模拟OpenAI客户端，模拟逐条验证流程"""
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
        
        # 检查是否有逐条验证的提示
        last_message = messages[-1] if messages else {}
        content = last_message.get('content', '')
        if isinstance(content, list):
            content = str(content)
        
        has_step_by_step_prompt = any([
            "逐条" in content,
            "一次只验证一条" in content,
            "按需调用工具" in content,
            "即时给出结果" in content
        ])
        
        if has_step_by_step_prompt:
            print("📋 检测到逐条验证提示")
        
        # 模拟思考时间
        time.sleep(0.3)
        
        # 第一次调用：识别发票
        if self.parent.call_count == 1:
            return MockResponse(
                content="我将开始逐条审核这张发票。首先识别发票信息。",
                tool_calls=[
                    MockToolCall("recognize_single_invoice", {"image_url": "test.jpg"})
                ]
            )
        
        # 第二次调用：验证第一条规则（时间限制）
        elif self.parent.call_count == 2:
            return MockResponse(
                content="发票信息已识别。现在开始逐条验证规则。\n\n**验证规则1：餐饮费报销时间限制**\n分析规则要求：餐饮费必须在发生后7天内报销\n检查发票信息：发票日期为2024-01-15\n需要获取当前时间进行对比。",
                tool_calls=[
                    MockToolCall("get_current_time", {})
                ]
            )
        
        # 第三次调用：给出第一条规则结果，开始验证第二条规则（城市标准）
        elif self.parent.call_count == 3:
            return MockResponse(
                content="**规则1验证结果**：✅ 符合 - 发票日期在7天内，符合时间限制要求\n\n**验证规则2：一线城市餐饮费标准**\n分析规则要求：一线城市餐饮费每餐不超过100元\n检查发票信息：发票金额为500元，城市为北京\n需要查询北京的城市分级标准。",
                tool_calls=[
                    MockToolCall("query_city_tier", {"city": "北京"})
                ]
            )
        
        # 第四次调用：给出第二条规则结果，验证第三条规则（发票完整性）
        elif self.parent.call_count == 4:
            return MockResponse(
                content="**规则2验证结果**：❌ 不符合 - 北京为一线城市，标准为100元/餐，但发票金额为500元，超出标准\n\n**验证规则3：发票完整性要求**\n分析规则要求：发票必须包含完整的商户信息、金额、日期\n检查发票信息：发票包含商户名称、金额、日期等完整信息\n无需调用额外工具，基于已识别信息即可验证。",
                tool_calls=None
            )
        
        # 第五次调用：给出第三条规则结果，验证第四条规则（业务合理性）
        elif self.parent.call_count == 5:
            return MockResponse(
                content="**规则3验证结果**：✅ 符合 - 发票信息完整，包含所有必要信息\n\n**验证规则4：业务合理性验证**\n分析规则要求：餐饮费用必须有合理的业务用途说明\n检查发票信息：发票显示为餐饮费，但缺少具体业务用途说明\n无需调用额外工具，基于发票内容即可判断。",
                tool_calls=None
            )
        
        # 第六次调用：给出第四条规则结果，生成最终汇总报告
        else:
            return MockResponse(
                content="""**规则4验证结果**：⚠️ 需注意 - 发票为餐饮费，但缺少具体业务用途说明，建议补充

---

📋 **最终审核报告汇总**

📄 **发票信息**：
- 金额：500.00元
- 日期：2024-01-15
- 城市：北京
- 类型：餐饮费
- 商户：某餐厅

📊 **逐条规则验证结果**：
✅ **规则1：餐饮费报销时间限制** - 符合
   └─ 发票日期在7天内，符合时间限制要求

❌ **规则2：一线城市餐饮费标准** - 不符合  
   └─ 北京为一线城市，标准为100元/餐，但发票金额为500元，超出标准

✅ **规则3：发票完整性要求** - 符合
   └─ 发票信息完整，包含所有必要信息

⚠️ **规则4：业务合理性验证** - 需注意
   └─ 缺少具体业务用途说明，建议补充

📈 **审核统计**：
- 总规则数：4条
- 符合规则：2条 (50%)
- 不符合规则：1条 (25%)
- 需注意规则：1条 (25%)

🎯 **最终结论**：部分通过

💡 **改进建议**：
1. **金额调整**：建议将单次餐饮费控制在100元以内，或分多次报销
2. **业务说明**：建议补充具体的业务用餐说明和参与人员信息
3. **其他方面**：时间和发票完整性均符合要求""",
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
        await asyncio.sleep(0.5)
        
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

def test_step_by_step_audit():
    """测试逐条验证审核功能"""
    print("🧪 开始测试逐条验证审核功能...")
    print("=" * 60)
    
    # 模拟会话存储
    from app import session_store, global_mcp_client
    
    session_id = "test_step_by_step"
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
            },
            {
                "rule_name": "发票完整性要求",
                "rule_description": "发票必须包含完整的商户信息、金额、日期",
                "rule_category": "发票要求"
            },
            {
                "rule_name": "业务合理性验证",
                "rule_description": "餐饮费用必须有合理的业务用途说明",
                "rule_category": "业务规则"
            }
        ]
    }
    
    # 替换全局MCP客户端
    original_mcp_client = global_mcp_client
    global_mcp_client.__dict__.update(MockMCPClient().__dict__)
    
    try:
        # 测试参数
        question = "请逐条审核这张发票，按需调用工具验证每条规则"
        history = []
        file_upload = None
        
        print(f"📝 用户问题: {question}")
        print(f"📋 规则总数: {len(session_store[session_id]['reimbursement_rules'])}条")
        print("🔄 开始逐条验证流程...")
        print("=" * 60)
        
        # 统计变量
        step = 0
        tool_calls_by_step = []
        rule_verifications = 0
        
        # 调用流式处理函数
        for empty_input, updated_history in answer_question_with_session(question, history, session_id, file_upload):
            step += 1
            
            if updated_history:
                last_msg = updated_history[-1]
                content = last_msg.get('content', '')
                role = last_msg.get('role', '')
                
                # 检测工具调用
                if "🔧 使用工具:" in content:
                    tool_name = content.split("🔧 使用工具:")[1].strip()
                    tool_calls_by_step.append((step, tool_name))
                    print(f"🔧 步骤{step}: 调用工具 {tool_name}")
                
                # 检测规则验证结果
                if any(marker in content for marker in ["规则1", "规则2", "规则3", "规则4"]) and any(result in content for result in ["✅ 符合", "❌ 不符合", "⚠️ 需注意"]):
                    rule_verifications += 1
                    print(f"📋 步骤{step}: 规则验证结果 #{rule_verifications}")
                
                # 检测最终汇总报告
                if "最终审核报告汇总" in content:
                    print(f"📊 步骤{step}: 生成最终汇总报告")
                
                print(f"步骤 #{step}: [{role}] {content[:100]}...")
        
        print(f"\n🎉 逐条验证测试完成！")
        print("=" * 60)
        print(f"📊 统计结果:")
        print(f"  - 总步骤数: {step}")
        print(f"  - 工具调用次数: {len(tool_calls_by_step)}")
        print(f"  - 规则验证次数: {rule_verifications}")
        
        print(f"\n🔧 工具调用顺序:")
        for step_num, tool_name in tool_calls_by_step:
            print(f"  步骤{step_num}: {tool_name}")
        
        # 验证是否实现了逐条验证
        expected_pattern = [
            "recognize_single_invoice",  # 发票识别
            "get_current_time",         # 时间规则验证
            "query_city_tier"           # 城市规则验证
        ]
        
        actual_tools = [tool for _, tool in tool_calls_by_step]
        
        print(f"\n📋 验证逐条调用模式:")
        print(f"期望的工具调用顺序: {expected_pattern}")
        print(f"实际的工具调用顺序: {actual_tools}")
        
        # 检查是否按需调用工具（不是一次性调用所有工具）
        if len(tool_calls_by_step) >= 2:
            # 检查工具调用是否分散在不同步骤
            steps = [step_num for step_num, _ in tool_calls_by_step]
            step_gaps = [steps[i+1] - steps[i] for i in range(len(steps)-1)]
            avg_gap = sum(step_gaps) / len(step_gaps) if step_gaps else 0
            
            if avg_gap > 2:  # 工具调用之间有足够的间隔
                print("✅ 成功实现逐条验证！工具调用分散在不同步骤")
            else:
                print("⚠️ 工具调用可能过于集中，需要改进")
        
        # 检查规则验证数量
        if rule_verifications >= 4:
            print("✅ 成功验证了所有规则！")
        else:
            print(f"⚠️ 只验证了{rule_verifications}条规则，可能有遗漏")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 恢复原始MCP客户端
        global_mcp_client.__dict__.update(original_mcp_client.__dict__)

if __name__ == "__main__":
    test_step_by_step_audit()
