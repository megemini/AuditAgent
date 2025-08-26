#!/usr/bin/env python3
"""
测试全面规则审核功能的脚本
"""

import asyncio
import json
import time
from app import answer_question_with_session

class MockClient:
    """模拟OpenAI客户端，模拟全面审核流程"""
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
        
        # 检查是否有全面审核的提示
        last_message = messages[-1] if messages else {}
        content = last_message.get('content', '')
        if isinstance(content, list):
            content = str(content)
        
        has_comprehensive_prompt = any([
            "全面" in content,
            "逐条" in content, 
            "所有规则" in content,
            "不能遗漏" in content
        ])
        
        if has_comprehensive_prompt:
            print("📋 检测到全面审核提示")
        
        # 模拟思考时间
        time.sleep(0.5)
        
        # 第一次调用：识别发票
        if self.parent.call_count == 1:
            return MockResponse(
                content="我将开始全面审核这张发票。首先识别发票信息。",
                tool_calls=[
                    MockToolCall("recognize_single_invoice", {"image_url": "test.jpg"})
                ]
            )
        
        # 第二次调用：时间规则验证
        elif self.parent.call_count == 2:
            return MockResponse(
                content="发票信息已识别。现在开始逐条验证规则。首先检查时间限制规则。",
                tool_calls=[
                    MockToolCall("get_current_time", {})
                ]
            )
        
        # 第三次调用：城市分级规则验证
        elif self.parent.call_count == 3:
            return MockResponse(
                content="时间规则验证完成。继续验证城市分级相关规则。",
                tool_calls=[
                    MockToolCall("query_city_tier", {"city": "北京"})
                ]
            )
        
        # 第四次调用：继续其他规则验证
        elif self.parent.call_count == 4:
            return MockResponse(
                content="城市分级验证完成。继续验证其他规则。",
                tool_calls=[
                    MockToolCall("get_current_time", {})  # 模拟验证另一个时间相关规则
                ]
            )
        
        # 第五次调用：最终全面报告
        else:
            return MockResponse(
                content="""基于全面的规则验证，我现在给出完整的审核报告：

📋 **发票审核报告**

📄 **发票信息**：
- 金额：500.00元
- 日期：2024-01-15
- 城市：北京
- 类型：餐饮费

📊 **规则验证结果**：
✅ 规则1：餐饮费报销时间限制 - 符合 - 发票日期在7天内
❌ 规则2：一线城市餐饮费标准 - 不符合 - 超出100元标准
✅ 规则3：发票完整性要求 - 符合 - 发票信息完整
⚠️ 规则4：业务合理性 - 需注意 - 建议提供业务说明

📈 **审核统计**：
- 总规则数：4条
- 符合规则：2条
- 不符合规则：1条
- 需注意规则：1条

🎯 **最终结论**：部分通过

💡 **改进建议**：
1. 金额超标：建议将餐饮费控制在100元以内
2. 业务说明：建议补充业务用餐的具体说明
3. 其他规则均符合要求，可以正常报销""",
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

def test_comprehensive_audit():
    """测试全面规则审核功能"""
    print("🧪 开始测试全面规则审核功能...")
    print("=" * 60)
    
    # 模拟会话存储
    from app import session_store, global_mcp_client
    
    session_id = "test_comprehensive"
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
        question = "请全面审核这张发票，检查所有规则"
        history = []
        file_upload = None
        
        print(f"📝 用户问题: {question}")
        print(f"📋 规则总数: {len(session_store[session_id]['reimbursement_rules'])}条")
        print("🔄 开始全面审核流程...")
        print("=" * 60)
        
        # 统计变量
        step = 0
        ai_calls = 0
        tool_calls = 0
        comprehensive_prompts = 0
        
        # 调用流式处理函数
        for empty_input, updated_history in answer_question_with_session(question, history, session_id, file_upload):
            step += 1
            
            if updated_history:
                last_msg = updated_history[-1]
                content = last_msg.get('content', '')
                role = last_msg.get('role', '')
                
                # 检测全面审核相关的内容
                if any(keyword in content for keyword in ["全面", "逐条", "所有规则", "不能遗漏"]):
                    comprehensive_prompts += 1
                    print(f"📋 检测到全面审核提示 #{comprehensive_prompts}")
                
                # 统计AI调用和工具调用
                if "🤔 AI正在思考" in content:
                    ai_calls += 1
                elif "🔧 使用工具:" in content:
                    tool_calls += 1
                
                print(f"步骤 #{step}: [{role}] {content[:80]}...")
        
        print(f"\n🎉 全面审核测试完成！")
        print("=" * 60)
        print(f"📊 统计结果:")
        print(f"  - 总步骤数: {step}")
        print(f"  - AI思考次数: {ai_calls}")
        print(f"  - 工具调用次数: {tool_calls}")
        print(f"  - 全面审核提示次数: {comprehensive_prompts}")
        
        # 检查最终结果
        if updated_history:
            final_messages = [msg for msg in updated_history if "审核报告" in msg.get('content', '')]
            if final_messages:
                print(f"\n📄 检测到完整审核报告:")
                final_content = final_messages[-1].get('content', '')
                
                # 检查报告是否包含全面审核的要素
                has_all_rules = "总规则数" in final_content
                has_statistics = "符合规则" in final_content and "不符合规则" in final_content
                has_conclusion = "最终结论" in final_content
                has_suggestions = "改进建议" in final_content
                
                print(f"  ✅ 包含规则统计: {has_all_rules}")
                print(f"  ✅ 包含符合性统计: {has_statistics}")
                print(f"  ✅ 包含最终结论: {has_conclusion}")
                print(f"  ✅ 包含改进建议: {has_suggestions}")
                
                if all([has_all_rules, has_statistics, has_conclusion, has_suggestions]):
                    print(f"\n🎯 全面审核功能测试通过！")
                    print(f"✅ AI成功进行了全面的规则验证")
                    print(f"✅ 生成了完整的审核报告")
                else:
                    print(f"\n⚠️ 审核报告不够完整，需要改进")
            else:
                print(f"\n❌ 未检测到完整的审核报告")
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 恢复原始MCP客户端
        global_mcp_client.__dict__.update(original_mcp_client.__dict__)

if __name__ == "__main__":
    test_comprehensive_audit()
