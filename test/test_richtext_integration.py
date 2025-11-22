#!/usr/bin/env python3
"""
测试脚本：验证钉钉富文本消息处理功能
"""

import sys
import os
import json
import asyncio
from unittest.mock import Mock, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入我们的模块
from core.dingtalk_integration import DingTalkSimpleHandler, ConversationHistory, AIServiceClient

class MockDingTalkMessage:
    """模拟钉钉消息对象"""
    def __init__(self, message_type, content=None):
        self.message_type = message_type
        self.sender_id = "test_user_123"
        self.conversation_id = "test_session_456"
        
        if message_type == 'text' and content:
            self.text = Mock()
            self.text.content = content
            
        elif message_type == 'picture' and content:
            self.image_content = Mock()
            self.image_content.download_code = content
            
        elif message_type == 'richText' and content:
            self.content = Mock()
            self.content.richText = content

class MockCallbackMessage:
    """模拟回调消息对象"""
    def __init__(self, message_type, content=None):
        self.data = {
            "message_type": message_type,
            "sender_id": "test_user_123",
            "conversation_id": "test_session_456"
        }
        
        if message_type == 'text' and content:
            self.data["text"] = {"content": content}
            
        elif message_type == 'picture' and content:
            self.data["image_content"] = {"download_code": content}
            
        elif message_type == 'richText' and content:
            self.data["content"] = {"richText": content}

def create_mock_ai_client():
    """创建模拟的AI客户端"""
    ai_client = Mock(spec=AIServiceClient)
    ai_client.connected = True
    
    # 模拟analyze_text方法
    async def mock_analyze_text(user_text, conversation_history, document_review_rules):
        return {
            "success": True,
            "analysis": f"这是对文本 '{user_text}' 的分析结果。基于规则：{', '.join(document_review_rules[:2])}..."
        }
    
    # 模拟analyze_document方法
    async def mock_analyze_document(image_url, user_text="", document_review_rules=None):
        return {
            "success": True,
            "document_data": {
                "document_type": "发票",
                "extracted_info": {
                    "金额": "100.00元",
                    "日期": "2023-01-01",
                    "类型": "增值税发票"
                },
                "verification_results": [
                    {
                        "rule_name": "发票有效性",
                        "verification_result": "✅ 符合",
                        "detail": "发票为真实有效的增值税发票"
                    },
                    {
                        "rule_name": "金额合理性",
                        "verification_result": "✅ 符合",
                        "detail": "发票金额在合理范围内"
                    }
                ],
                "audit_conclusion": "发票审核通过，符合所有审核规则",
                "suggestions": ["建议保留原始发票", "建议按时提交审核申请"]
            }
        }
    
    ai_client.analyze_text = mock_analyze_text
    ai_client.analyze_document = mock_analyze_document
    
    return ai_client

def test_text_message():
    """测试文本消息处理"""
    print("=" * 50)
    print("测试文本消息处理")
    print("=" * 50)
    
    # 创建模拟消息
    message = MockDingTalkMessage('text', "这是一张发票，请帮我审核")
    callback = MockCallbackMessage('text', "这是一张发票，请帮我审核")
    
    # 创建处理器
    handler = DingTalkSimpleHandler(
        logger=None,
        ai_client=create_mock_ai_client(),
        session_id="test_session",
        conversation_history=ConversationHistory()
    )
    
    # 模拟dingtalk_stream.ChatbotMessage.from_dict
    original_from_dict = None
    try:
        import dingtalk_stream
        original_from_dict = dingtalk_stream.ChatbotMessage.from_dict
        dingtalk_stream.ChatbotMessage.from_dict = Mock(return_value=message)
    except ImportError:
        print("警告: dingtalk_stream 模块未安装，跳过测试")
        return
    
    try:
        # 运行测试
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(handler.process(callback))
        print(f"文本消息处理结果: {result}")
        print("✅ 文本消息处理测试通过")
    except Exception as e:
        print(f"❌ 文本消息处理测试失败: {e}")
    finally:
        # 恢复原始方法
        if original_from_dict:
            dingtalk_stream.ChatbotMessage.from_dict = original_from_dict
        loop.close()

def test_picture_message():
    """测试图片消息处理"""
    print("\n" + "=" * 50)
    print("测试图片消息处理")
    print("=" * 50)
    
    # 创建模拟消息
    message = MockDingTalkMessage('picture', "test_download_code_123")
    callback = MockCallbackMessage('picture', "test_download_code_123")
    
    # 创建处理器
    handler = DingTalkSimpleHandler(
        logger=None,
        ai_client=create_mock_ai_client(),
        session_id="test_session",
        conversation_history=ConversationHistory()
    )
    
    # 模拟dingtalk_stream.ChatbotMessage.from_dict
    original_from_dict = None
    try:
        import dingtalk_stream
        original_from_dict = dingtalk_stream.ChatbotMessage.from_dict
        dingtalk_stream.ChatbotMessage.from_dict = Mock(return_value=message)
    except ImportError:
        print("警告: dingtalk_stream 模块未安装，跳过测试")
        return
    
    try:
        # 运行测试
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(handler.process(callback))
        print(f"图片消息处理结果: {result}")
        print("✅ 图片消息处理测试通过")
    except Exception as e:
        print(f"❌ 图片消息处理测试失败: {e}")
    finally:
        # 恢复原始方法
        if original_from_dict:
            dingtalk_stream.ChatbotMessage.from_dict = original_from_dict
        loop.close()

def test_richtext_message():
    """测试富文本消息处理"""
    print("\n" + "=" * 50)
    print("测试富文本消息处理")
    print("=" * 50)
    
    # 创建模拟富文本内容
    rich_text_content = [
        {"text": "请帮我审核这些发票："},
        {"downloadCode": "test_download_code_456"},
        {"text": "这是第二张发票"}
    ]
    
    # 创建模拟消息
    message = MockDingTalkMessage('richText', rich_text_content)
    callback = MockCallbackMessage('richText', rich_text_content)
    
    # 创建处理器
    handler = DingTalkSimpleHandler(
        logger=None,
        ai_client=create_mock_ai_client(),
        session_id="test_session",
        conversation_history=ConversationHistory()
    )
    
    # 模拟dingtalk_stream.ChatbotMessage.from_dict
    original_from_dict = None
    try:
        import dingtalk_stream
        original_from_dict = dingtalk_stream.ChatbotMessage.from_dict
        dingtalk_stream.ChatbotMessage.from_dict = Mock(return_value=message)
    except ImportError:
        print("警告: dingtalk_stream 模块未安装，跳过测试")
        return
    
    try:
        # 运行测试
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(handler.process(callback))
        print(f"富文本消息处理结果: {result}")
        print("✅ 富文本消息处理测试通过")
    except Exception as e:
        print(f"❌ 富文本消息处理测试失败: {e}")
    finally:
        # 恢复原始方法
        if original_from_dict:
            dingtalk_stream.ChatbotMessage.from_dict = original_from_dict
        loop.close()

def test_content_extraction():
    """测试内容提取功能"""
    print("\n" + "=" * 50)
    print("测试内容提取功能")
    print("=" * 50)
    
    # 创建处理器
    handler = DingTalkSimpleHandler()
    
    # 测试文本消息
    text_message = MockDingTalkMessage('text', "这是一条测试文本")
    text_content = handler._extract_message_content(text_message)
    print(f"文本消息提取结果: {text_content}")
    assert text_content['has_text'] == True
    assert text_content['text_parts'] == ["这是一条测试文本"]
    assert text_content['has_images'] == False
    print("✅ 文本消息内容提取测试通过")
    
    # 测试图片消息
    picture_message = MockDingTalkMessage('picture', "test_download_code_789")
    picture_content = handler._extract_message_content(picture_message)
    print(f"图片消息提取结果: {picture_content}")
    assert picture_content['has_images'] == True
    assert picture_content['image_download_codes'] == ["test_download_code_789"]
    assert picture_content['has_text'] == False
    print("✅ 图片消息内容提取测试通过")
    
    # 测试富文本消息
    rich_text_content = [
        {"text": "请审核这些发票："},
        {"downloadCode": "test_download_code_101"},
        {"text": "谢谢"},
        {"downloadCode": "test_download_code_202"}
    ]
    richtext_message = MockDingTalkMessage('richText', rich_text_content)
    richtext_content = handler._extract_message_content(richtext_message)
    print(f"富文本消息提取结果: {richtext_content}")
    assert richtext_content['has_text'] == True
    assert richtext_content['has_images'] == True
    assert richtext_content['text_parts'] == ["请审核这些发票：", "谢谢"]
    assert richtext_content['image_download_codes'] == ["test_download_code_101", "test_download_code_202"]
    print("✅ 富文本消息内容提取测试通过")

if __name__ == "__main__":
    print("开始测试钉钉富文本消息处理功能")
    
    # 测试内容提取功能
    test_content_extraction()
    
    # 测试各种消息类型
    test_text_message()
    test_picture_message()
    test_richtext_message()
    
    print("\n" + "=" * 50)
    print("所有测试完成")
    print("=" * 50)