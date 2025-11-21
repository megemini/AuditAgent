#!/usr/bin/env python3
"""
钉钉机器人集成模块
提供钉钉机器人的创建、启动、停止和管理功能
集成AI服务，支持用户信息处理和AI分析
"""

import logging
import threading
import time
import asyncio
import json
import os
from typing import Optional, Dict, Any, List

# DingTalk integration
try:
    import dingtalk_stream
    from dingtalk_stream import AckMessage
    DINGTALK_AVAILABLE = True
except ImportError:
    DINGTALK_AVAILABLE = False
    logging.warning("dingtalk-stream not available. DingTalk integration will be disabled.")

# Import OpenAI and logging
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from core import ai_manager, SessionConfig
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logging.warning("LangChain not available. Using legacy OpenAI client.")

# AI service integration - direct function import
try:
    import sys
    # 确保可以导入mcp_document_stdio
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from mcp_document_stdio import download_image, extract_text_with_ocr, analyze_document_with_ai
    AI_SERVICE_AVAILABLE = True
except ImportError as e:
    AI_SERVICE_AVAILABLE = False
    logging.warning(f"mcp_document_stdio import failed: {e}. AI service integration will be disabled.")

# Global DingTalk bot status
dingtalk_bot_thread: Optional[threading.Thread] = None
dingtalk_bot_status = "未启动"
dingtalk_app_key = ""
dingtalk_app_secret = ""

class ConversationHistory:
    """对话历史管理器，支持按session_id存储多个独立对话"""
    
    def __init__(self, max_history_per_session: int = 50):
        """
        初始化对话历史管理器
        
        Args:
            max_history_per_session: 每个session保存的最大对话数
        """
        self.conversations: Dict[str, List[Dict[str, str]]] = {}
        self.max_history_per_session = max_history_per_session
        self.lock = threading.Lock()
    
    def add_message(self, session_id: str, role: str, content: str, timestamp: Optional[str] = None):
        """
        添加一条消息到对话历史
        
        Args:
            session_id: 会话ID
            role: 消息角色，'user' 或 'assistant'
            content: 消息内容
            timestamp: 消息时间戳（可选）
        """
        with self.lock:
            if session_id not in self.conversations:
                self.conversations[session_id] = []
            
            message = {
                "role": role,
                "content": content,
                "timestamp": timestamp or time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            self.conversations[session_id].append(message)
            
            # 限制历史数量，保留最近的对话
            if len(self.conversations[session_id]) > self.max_history_per_session:
                self.conversations[session_id] = self.conversations[session_id][-self.max_history_per_session:]
    
    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """
        获取某个session的对话历史
        
        Args:
            session_id: 会话ID
            
        Returns:
            对话历史列表
        """
        with self.lock:
            return self.conversations.get(session_id, []).copy()
    
    def get_formatted_context(self, session_id: str, max_messages: int = 10) -> str:
        """
        获取格式化的对话上下文，用于AI提示
        
        Args:
            session_id: 会话ID
            max_messages: 最多返回最近的消息数
            
        Returns:
            格式化的对话上下文字符串
        """
        history = self.get_history(session_id)
        
        # 只取最近的消息
        if len(history) > max_messages:
            history = history[-max_messages:]
        
        if not history:
            return ""
        
        context_lines = ["【对话历史】"]
        for msg in history:
            role = "用户" if msg["role"] == "user" else "助手"
            context_lines.append(f"{role}: {msg['content']}")
        
        return "\n".join(context_lines)
    
    def clear_history(self, session_id: str) -> bool:
        """
        清空某个session的对话历史
        
        Args:
            session_id: 会话ID
            
        Returns:
            操作成功状态
        """
        with self.lock:
            if session_id in self.conversations:
                self.conversations[session_id] = []
                return True
            return False
    
    def get_all_sessions(self) -> List[str]:
        """获取所有active的session_id"""
        with self.lock:
            return list(self.conversations.keys())

# Global AI service configuration
ai_service_config: Dict[str, Any] = {
    "document_server": None,
    "invoice_server": None,
    "api_key": None,
    "base_url": None,
    "model": None
}

# Global conversation history manager
conversation_history_manager: Optional[ConversationHistory] = None

class AIServiceClient:
    """AI服务客户端，直接调用mcp_document_stdio中的函数"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger
        self.connected = False
    
    async def connect(self, api_key: str, base_url: str, model: str):
        """初始化AI服务配置"""
        if not AI_SERVICE_AVAILABLE:
            if self.logger:
                self.logger.error("AI service not available")
            return False
        
        try:
            # 保存配置
            ai_service_config["api_key"] = api_key
            ai_service_config["base_url"] = base_url
            ai_service_config["model"] = model
            
            self.connected = True
            if self.logger:
                self.logger.info("AI services configured successfully")
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to configure AI services: {e}")
            return False
    
    async def analyze_text(self, user_text: str = "", conversation_history: Optional[List[Dict[str, str]]] = None,
                          reimbursement_rules: Optional[list] = None) -> Dict[str, Any]:
        """分析用户文本 - 基于对话历史和报销规则进行文本分析"""
        if not self.connected:
            return {"success": False, "message": "AI服务未初始化"}
        
        try:
            if not user_text:
                return {"success": False, "message": "请提供用户文本"}
            
            if not ai_service_config["api_key"] or not ai_service_config["base_url"] or not ai_service_config["model"]:
                return {"success": False, "message": "缺少OpenAI配置信息"}
            
            # 构建报销规则上下文
            rules_context = ""
            if reimbursement_rules:
                rules_context = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(reimbursement_rules)])
            else:
                rules_context = "未提供具体的财务报销规则"
            
            # 构建对话历史上下文
            history_context = ""
            if conversation_history:
                history_lines = ["【对话历史】"]
                for msg in conversation_history[-5:]:  # 只取最近5条
                    role = "用户" if msg["role"] == "user" else "助手"
                    history_lines.append(f"{role}: {msg['content']}")
                history_context = "\n".join(history_lines)
            
            # 构建财务咨询提示
            prompt = f"""你是一个财务报销专家，根据以下信息回答用户的问题。

    财务报销规则：
    {rules_context}

    {history_context}

    用户新消息：{user_text}

    请基于上述规则和对话历史，详细分析用户的问题，提供专业的财务建议。"""
            
            if self.logger:
                self.logger.info(f"生成的文本分析提示长度: {len(prompt)}字符")
            
            try:
                import openai
                client = openai.OpenAI(
                    api_key=ai_service_config["api_key"],
                    base_url=ai_service_config["base_url"]
                )
                
                response = client.chat.completions.create(
                    model=ai_service_config["model"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=2000
                )
                
                content = response.choices[0].message.content
                
                return {
                    "success": True,
                    "analysis": content,
                    "message": "文本分析完成"
                }
                
            except Exception as e:
                if self.logger:
                    self.logger.error(f"OpenAI API调用失败: {e}")
                return {"success": False, "message": f"AI分析失败: {e}"}
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Text analysis failed: {e}")
            return {"success": False, "message": f"文本分析失败: {e}"}
    
    async def analyze_document(self, image_url: str = None, image_data: str = None, user_text: str = "", 
                              reimbursement_rules: list = None) -> Dict[str, Any]:
        """分析文档 - 直接调用mcp_document_stdio中的函数"""
        if not self.connected:
            return {"success": False, "message": "AI服务未初始化"}
        
        try:
            # 检查必需参数
            if not (image_url or image_data):
                return {"success": False, "message": "请提供有效的 image_url 或 image_data 参数"}
            
            if not ai_service_config["api_key"] or not ai_service_config["base_url"] or not ai_service_config["model"]:
                return {"success": False, "message": "缺少OpenAI配置信息"}
            
            # 确定图像源并进行OCR
            tmp_file_path = None
            try:
                if image_url:
                    if self.logger:
                        self.logger.info("使用URL图像源...")
                    # 从 URL 下载图像
                    tmp_file_path = download_image(image_url)
                    ocr_text = extract_text_with_ocr(tmp_file_path)
                elif image_data and image_data != "base64_encoded_image_data":
                    if self.logger:
                        self.logger.info("使用Base64图像数据...")
                    # 解码 base64 图像数据
                    import base64
                    import io
                    from PIL import Image
                    
                    try:
                        image_bytes = base64.b64decode(image_data)
                        # 转换为PIL图像
                        image = Image.open(io.BytesIO(image_bytes))
                        if image.mode != 'RGB':
                            image = image.convert('RGB')
                        # 进行OCR
                        ocr_text = extract_text_with_ocr(image)
                    except Exception as e:
                        if self.logger:
                            self.logger.error(f"Base64解码失败: {e}")
                        return {"success": False, "message": f"Base64 解码失败: {e}"}
                else:
                    return {"success": False, "message": "请提供有效的图像数据"}
                
                # 使用AI分析单据内容
                if self.logger:
                    self.logger.info("开始AI分析单据内容...")
                analysis_result = analyze_document_with_ai(
                    ocr_text,
                    user_text,
                    ai_service_config["api_key"],
                    ai_service_config["base_url"],
                    ai_service_config["model"],
                    image_url=image_url,
                    reimbursement_rules=reimbursement_rules
                )
                
                # 清理临时文件
                if tmp_file_path and os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)
                    if self.logger:
                        self.logger.info("临时文件已清理")
                
                # 检查分析结果是否包含错误
                if "error" in analysis_result:
                    if self.logger:
                        self.logger.error(f"AI分析失败: {analysis_result['error']}")
                    return {
                        "success": False,
                        "message": analysis_result["error"],
                        "raw_content": analysis_result.get("raw_content", "")
                    }
                
                # 返回成功结果
                return {
                    "success": True,
                    "document_data": analysis_result,
                    "ocr_text": ocr_text,
                    "message": "单据识别完成"
                }
                
            finally:
                # 确保清理临时文件
                if tmp_file_path and os.path.exists(tmp_file_path):
                    try:
                        os.unlink(tmp_file_path)
                    except:
                        pass
                        
        except Exception as e:
            if self.logger:
                self.logger.error(f"Document analysis failed: {e}")
            return {"success": False, "message": f"文档分析失败: {e}"}
    
    async def close(self):
        """关闭连接"""
        self.connected = False

class DingTalkSimpleHandler(dingtalk_stream.ChatbotHandler):
    """钉钉消息处理器，支持文本、图片和富文本消息，集成AI分析功能和对话历史"""
    
    def __init__(self, logger: Optional[logging.Logger] = None, ai_client: Optional[AIServiceClient] = None, session_id: str = None, session_store_ref: Optional[Dict] = None, conversation_history: Optional[ConversationHistory] = None):
        # Initialize the parent class
        try:
            super(dingtalk_stream.ChatbotHandler, self).__init__()
        except:
            # Fallback: just initialize without parent
            pass
        self.logger = logger
        self.ai_client = ai_client
        self.session_id = session_id
        self.session_store_ref = session_store_ref or {}
        self.conversation_history = conversation_history or ConversationHistory()
        self.loop = None
    
    def _extract_message_content(self, incoming_message) -> Dict[str, Any]:
        """
        从不同类型的消息中提取文本和图片内容
        
        Args:
            incoming_message: 钉钉消息对象
            
        Returns:
            包含文本和图片信息的字典
        """
        result = {
            "text_parts": [],
            "image_download_codes": [],
            "has_images": False,
            "has_text": False
        }
        
        if incoming_message.message_type == 'text':
            # 文本消息
            if hasattr(incoming_message, 'text') and incoming_message.text:
                result["text_parts"].append(incoming_message.text.content)
                result["has_text"] = True
                
        elif incoming_message.message_type == 'picture':
            # 图片消息
            if hasattr(incoming_message, 'image_content') and incoming_message.image_content:
                if hasattr(incoming_message.image_content, 'download_code') and incoming_message.image_content.download_code:
                    result["image_download_codes"].append(incoming_message.image_content.download_code)
                    result["has_images"] = True
                    
        elif incoming_message.message_type == 'richText':
            # 富文本消息
            if hasattr(incoming_message, 'rich_text_content') and incoming_message.rich_text_content:
                # 处理富文本列表
                if hasattr(incoming_message.rich_text_content, 'rich_text_list') and incoming_message.rich_text_content.rich_text_list:
                    for item in incoming_message.rich_text_content.rich_text_list:
                        if isinstance(item, dict):
                            # 如果是字典格式
                            if 'text' in item and item['text']:
                                result["text_parts"].append(item['text'])
                                result["has_text"] = True
                            elif 'downloadCode' in item and item['downloadCode']:
                                result["image_download_codes"].append(item['downloadCode'])
                                result["has_images"] = True
                        else:
                            # 如果是对象格式
                            if hasattr(item, 'text') and item.text:
                                result["text_parts"].append(item.text)
                                result["has_text"] = True
                            elif hasattr(item, 'downloadCode') and item.downloadCode:
                                result["image_download_codes"].append(item.downloadCode)
                                result["has_images"] = True
        
        return result
    
    async def _process_unified_message(self, text_parts: List[str], image_download_codes: List[str],
                                      current_session_id: str) -> str:
        """
        统一处理包含文本和图片的消息
        
        Args:
            text_parts: 文本内容列表
            image_download_codes: 图片下载码列表
            current_session_id: 当前会话ID
            
        Returns:
            处理结果消息
        """
        # 合并所有文本部分
        user_text = "\n".join(text_parts) if text_parts else ""
        
        # 保存用户消息到历史
        if user_text:
            self.conversation_history.add_message(current_session_id, "user", user_text)
        
        # 如果没有AI客户端，返回简单响应
        if not (self.ai_client and self.ai_client.connected):
            response_parts = []
            if user_text:
                response_parts.append(f"收到文本消息：{user_text}")
            if image_download_codes:
                response_parts.append(f"收到 {len(image_download_codes)} 张图片")
            response_parts.append("\n\n💡 提示：AI服务未启用，无法进行智能分析")
            return "\n".join(response_parts)
        
        try:
            # 获取对话历史
            conversation_history = self.conversation_history.get_history(current_session_id)
            
            # 获取报销规则
            reimbursement_rules = []
            try:
                if self.session_id:
                    session_data = self.session_store_ref.get(self.session_id, {})
                    reimbursement_rules = session_data.get("reimbursement_rules", [])
                
                if not reimbursement_rules:
                    reimbursement_rules = [
                        "发票必须为真实有效的增值税发票",
                        "发票金额必须在合理范围内",
                        "发票日期必须在报销有效期内",
                        "发票内容必须与实际业务相符"
                    ]
                    if self.logger:
                        self.logger.info("使用默认报销规则")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Failed to get reimbursement rules: {e}, using default rules")
                reimbursement_rules = [
                    "发票必须为真实有效的增值税发票",
                    "发票金额必须在合理范围内",
                    "发票日期必须在报销有效期内",
                    "发票内容必须与实际业务相符"
                ]
            
            # 如果有图片，先处理图片
            image_urls = []
            if image_download_codes:
                # 获取访问令牌
                access_token = get_dingtalk_access_token(dingtalk_app_key, dingtalk_app_secret)
                if not access_token:
                    if self.logger:
                        self.logger.error("Failed to get access token for image download")
                    return "❌ 无法获取访问令牌，图片分析失败"
                
                # 获取所有图片的下载URL
                for download_code in image_download_codes:
                    # 添加延迟以防止并发请求
                    time.sleep(0.5)
                    download_url = get_file_download_url(access_token, download_code, dingtalk_app_key)
                    if download_url:
                        image_urls.append(download_url)
                        if self.logger:
                            self.logger.info(f"Got download URL: {download_url[:50]}...")
                    else:
                        if self.logger:
                            self.logger.warning(f"Failed to get download URL for code: {download_code}")
            
            # 根据内容类型决定处理方式
            if image_urls:
                # 有图片，使用文档分析
                if self.logger:
                    self.logger.info(f"Processing {len(image_urls)} images with text: {user_text[:50]}...")
                
                # 处理每张图片
                all_results = []
                for i, image_url in enumerate(image_urls):
                    if self.logger:
                        self.logger.info(f"Analyzing image {i+1}/{len(image_urls)}...")
                    
                    doc_result = await self.ai_client.analyze_document(
                        image_url=image_url,
                        user_text=user_text,
                        reimbursement_rules=reimbursement_rules
                    )
                    
                    if doc_result.get("success"):
                        doc_data = doc_result.get("document_data", {})
                        if isinstance(doc_data, dict):
                            # 格式化财务审核结果
                            formatted_result = f"🔍 图片 {i+1} 财务审核结果：\n\n"
                            
                            # 添加提取的关键信息
                            if "extracted_info" in doc_data:
                                formatted_result += "📋 提取信息：\n"
                                extracted_info = doc_data["extracted_info"]
                                if isinstance(extracted_info, dict):
                                    for key, value in extracted_info.items():
                                        formatted_result += f"  • {key}: {value}\n"
                                else:
                                    formatted_result += f"  • {extracted_info}\n"
                                formatted_result += "\n"
                            
                            # 添加验证结果
                            if "verification_results" in doc_data:
                                formatted_result += "✅ 规则验证：\n"
                                verification_results = doc_data["verification_results"]
                                if isinstance(verification_results, list):
                                    for item in verification_results:
                                        if isinstance(item, dict):
                                            rule_name = item.get("rule_name", "未知规则")
                                            verification_result = item.get("verification_result", "")
                                            detail = item.get("detail", "")
                                            formatted_result += f"  • {rule_name}: {verification_result}\n"
                                            if detail:
                                                formatted_result += f"    └─ {detail}\n"
                                        else:
                                            formatted_result += f"  • {item}\n"
                                elif isinstance(verification_results, dict):
                                    for rule, result in verification_results.items():
                                        formatted_result += f"  • {rule}: {result}\n"
                                else:
                                    formatted_result += f"  • {verification_results}\n"
                                formatted_result += "\n"
                            
                            # 添加审核结论
                            if "audit_conclusion" in doc_data:
                                formatted_result += "📝 审核结论：\n"
                                formatted_result += f"  • {doc_data['audit_conclusion']}\n\n"
                            
                            # 添加改进建议
                            if "suggestions" in doc_data:
                                formatted_result += "💡 改进建议：\n"
                                suggestions = doc_data["suggestions"]
                                if isinstance(suggestions, list):
                                    for suggestion in suggestions:
                                        formatted_result += f"  • {suggestion}\n"
                                else:
                                    formatted_result += f"  • {suggestions}\n"
                            
                            all_results.append(formatted_result)
                        else:
                            all_results.append(f"📄 图片 {i+1} 财务审核结果：\n{doc_data}")
                    else:
                        all_results.append(f"❌ 图片 {i+1} 财务审核失败：{doc_result.get('message', '未知错误')}")
                
                # 合并所有图片的分析结果
                reply_message = "\n\n".join(all_results)
            else:
                # 只有文本，使用文本分析
                if self.logger:
                    self.logger.info(f"Processing text-only message: {user_text[:50]}...")
                
                ai_result = await self.ai_client.analyze_text(
                    user_text=user_text,
                    conversation_history=conversation_history,
                    reimbursement_rules=reimbursement_rules
                )
                
                if ai_result.get("success"):
                    # 获取AI分析结果
                    analysis = ai_result.get("analysis", "")
                    reply_message = f"🤖 财务顾问分析：\n\n{analysis}"
                else:
                    reply_message = f"❌ AI分析失败：{ai_result.get('message', '未知错误')}"
            
            return reply_message
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error in unified message processing: {e}", exc_info=True)
            return f"❌ 消息处理出错：{str(e)}"
    
    async def process(self, callback: dingtalk_stream.CallbackMessage):
        """处理钉钉消息，支持多种消息类型和AI分析，包含对话历史上下文"""
        try:
            if not DINGTALK_AVAILABLE:
                return AckMessage.STATUS_OK, 'OK'
                
            # 解析消息
            incoming_message = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
            
            # 提取session_id（使用user_id或conversation_id）
            current_session_id = self.session_id or getattr(incoming_message, 'sender_id', None) or getattr(incoming_message, 'conversation_id', 'default')
            
            if self.logger:
                self.logger.info(f"Received DingTalk message from session: {current_session_id}")
                self.logger.info(f"Received DingTalk message: {incoming_message}")
            
            # 根据消息类型处理
            reply_message = None
            
            if incoming_message.message_type in ['text', 'picture', 'richText']:
                # 使用统一的消息处理方法
                if self.logger:
                    self.logger.info(f"Processing {incoming_message.message_type} message with unified handler")
                
                # 提取消息内容
                content_info = self._extract_message_content(incoming_message)
                
                if self.logger:
                    self.logger.info(f"Extracted content: text_parts={len(content_info['text_parts'])}, images={len(content_info['image_download_codes'])}")
                
                # 处理消息
                reply_message = await self._process_unified_message(
                    content_info['text_parts'],
                    content_info['image_download_codes'],
                    current_session_id
                )
                
            elif incoming_message.message_type == 'audio':
                # 语音消息
                if self.logger:
                    self.logger.info("Audio message received")
                reply_message = "🎵 收到语音消息\n\n💡 提示：目前不支持语音消息的AI分析"
                
            elif incoming_message.message_type == 'video':
                # 视频消息
                if self.logger:
                    self.logger.info("Video message received")
                reply_message = "🎬 收到视频消息\n\n💡 提示：目前不支持视频消息的AI分析"
                
            elif incoming_message.message_type == 'file':
                # 文件消息
                if self.logger:
                    self.logger.info("File message received")
                reply_message = "📎 收到文件消息\n\n💡 提示：目前不支持文件消息的AI分析"
                
            else:
                # 未知消息类型
                if self.logger:
                    self.logger.warning(f"Unknown message type: {incoming_message.message_type}")
                reply_message = f"❓ 未知消息类型 {incoming_message.message_type}\n\n💡 提示：目前支持文本、图片和富文本消息的AI分析"
            
            # 保存AI回复到历史
            if reply_message and incoming_message.message_type in ['text', 'picture', 'richText']:
                self.conversation_history.add_message(current_session_id, "assistant", reply_message)
            
            # 使用reply_text回复消息
            if reply_message and hasattr(self, 'reply_text'):
                self.reply_text(reply_message, incoming_message)
            elif reply_message:
                if self.logger:
                    self.logger.info(f"Would reply with: {reply_message}")
            
            return AckMessage.STATUS_OK, 'OK'
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error processing DingTalk message: {e}")
def start_dingtalk_bot(app_key: str, app_secret: str,
                      api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None, session_id: str = None, session_store: dict = None) -> str:
    """Start DingTalk bot in a separate thread with AI service integration and conversation history"""
    global dingtalk_bot_thread, dingtalk_bot_status, dingtalk_app_key, dingtalk_app_secret, conversation_history_manager
    
    if not DINGTALK_AVAILABLE:
        dingtalk_bot_status = "❌ dingtalk-stream 库不可用"
        return dingtalk_bot_status
    
    if dingtalk_bot_thread and dingtalk_bot_thread.is_alive():
        dingtalk_bot_status = "✅ DingTalk 机器人已正在运行"
        return dingtalk_bot_status
    
    try:
        dingtalk_app_key = app_key
        dingtalk_app_secret = app_secret
        
        # Initialize conversation history manager if not already initialized
        if conversation_history_manager is None:
            conversation_history_manager = ConversationHistory(max_history_per_session=50)
            if logger:
                logger.info("Conversation history manager initialized")
        
        # Use session_store passed as parameter
        session_store_ref = session_store if session_store is not None else {}
        if logger and session_store is None:
            logger.warning("No session_store provided, using empty reference")
        
        # Use a threading.Event to signal when as bot has started
        startup_complete = threading.Event()
        final_status = [None]  # Use a list to store the final status
        
        def run_dingtalk_bot():
            global dingtalk_bot_status
            try:
                dingtalk_bot_status = "🔄 DingTalk 机器人启动中..."
                if logger:
                    logger.info("Starting DingTalk bot with AI integration...")
                
                # Create AI client if AI service is available
                ai_client = None
                event_loop = None
                if AI_SERVICE_AVAILABLE and api_key and base_url and model:
                    try:
                        ai_client = AIServiceClient(logger)
                        # Run async connection in sync context (keep loop alive for handler)
                        event_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(event_loop)
                        connected = event_loop.run_until_complete(ai_client.connect(api_key, base_url, model))
                        
                        if connected:
                            if logger:
                                logger.info("AI services configured successfully")
                            dingtalk_bot_status = "🔄 DingTalk 机器人启动中... (AI服务已配置)"
                        else:
                            if logger:
                                logger.warning("Failed to configure AI services, running without AI")
                            ai_client = None
                    except Exception as e:
                        if logger:
                            logger.error(f"Failed to initialize AI services: {e}")
                        ai_client = None
                else:
                    if logger:
                        logger.info("AI service configuration not provided, running without AI")
                
                credential = dingtalk_stream.Credential(app_key, app_secret)
                client = dingtalk_stream.DingTalkStreamClient(credential)
                
                # Create handler instance with logger, AI client, session_id, session_store reference and conversation history
                handler = DingTalkSimpleHandler(logger, ai_client, session_id, session_store_ref, conversation_history_manager)
                client.register_callback_handler(
                    dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
                    handler
                )
                
                dingtalk_bot_status = "✅ DingTalk 机器人已启动" + (" (AI集成已启用)" if ai_client else " (无AI集成)")
                final_status[0] = dingtalk_bot_status  # Store final status
                if logger:
                    logger.info(f"DingTalk bot started successfully with AI: {'enabled' if ai_client else 'disabled'}")
                
                # Signal that startup is complete
                startup_complete.set()
                
                client.start_forever()
                
            except Exception as e:
                dingtalk_bot_status = f"❌ DingTalk 机器人启动失败: {str(e)}"
                final_status[0] = dingtalk_bot_status  # Store the final status
                startup_complete.set()  # Signal that startup is complete (even if it failed)
                if logger:
                    logger.error(f"Failed to start DingTalk bot: {e}")
        
        # Start bot in a daemon thread
        dingtalk_bot_thread = threading.Thread(target=run_dingtalk_bot, daemon=True)
        dingtalk_bot_thread.start()
        
        # Wait for startup to complete or timeout after 10 seconds
        if startup_complete.wait(timeout=10):
            return final_status[0] if final_status[0] else dingtalk_bot_status
        else:
            # Timeout occurred, return current status
            if logger:
                logger.warning("DingTalk bot startup timed out")
            return dingtalk_bot_status + " (启动超时，请检查日志)"
        
    except Exception as e:
        dingtalk_bot_status = f"❌ DingTalk 机器人启动失败: {str(e)}"
        return dingtalk_bot_status

def stop_dingtalk_bot() -> str:
    """Stop DingTalk bot and AI services"""
    global dingtalk_bot_thread, dingtalk_bot_status
    
    # We can't actually stop the dingtalk client easily since it runs forever
    # The daemon thread will be terminated when the main program exits
    dingtalk_bot_status = "⏹️ DingTalk 机器人将在程序退出时停止"
    
    # Reset AI service configuration
    global ai_service_config
    ai_service_config = {
        "document_server": None,
        "invoice_server": None,
        "api_key": None,
        "base_url": None,
        "model": None
    }
    
    return dingtalk_bot_status

def get_dingtalk_status() -> str:
    """Get current DingTalk bot status"""
    global dingtalk_bot_status
    return dingtalk_bot_status

def is_dingtalk_available() -> bool:
    """Check if DingTalk integration is available"""
    return DINGTALK_AVAILABLE

def get_dingtalk_access_token(app_key: str, app_secret: str) -> Optional[str]:
    """Get access token from DingTalk API"""
    if not DINGTALK_AVAILABLE:
        return None
    
    try:
        import requests
        url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
        headers = {"Content-Type": "application/json"}
        data = {"appKey": app_key, "appSecret": app_secret}
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if logger:
                logger.info(f"Successfully obtained DingTalk access token")
            return result.get("accessToken")
        else:
            if logger:
                logger.error(f"Failed to get access token: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.Timeout:
        if logger:
            logger.error("Timeout while getting DingTalk access token")
        return None
    except requests.exceptions.RequestException as e:
        if logger:
            logger.error(f"Request error getting DingTalk access token: {e}")
        return None
    except Exception as e:
        if logger:
            logger.error(f"Unexpected error getting DingTalk access token: {e}")
        return None

def get_file_download_url(access_token: str, download_code: str, robot_code: str) -> Optional[str]:
    """Get file download URL from DingTalk"""
    if not DINGTALK_AVAILABLE:
        return None
    
    try:
        import requests
        url = "https://api.dingtalk.com/v1.0/robot/messageFiles/download"
        headers = {
            "x-acs-dingtalk-access-token": access_token,
            "Content-Type": "application/json"
        }
        data = {"downloadCode": download_code, "robotCode": robot_code}
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if logger:
                logger.info(f"Successfully obtained file download URL")
            return result.get("downloadUrl")
        else:
            if logger:
                logger.error(f"Failed to get download URL: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.Timeout:
        if logger:
            logger.error("Timeout while getting DingTalk file download URL")
        return None
    except requests.exceptions.RequestException as e:
        if logger:
            logger.error(f"Request error getting DingTalk file download URL: {e}")
        return None
    except Exception as e:
        if logger:
            logger.error(f"Unexpected error getting DingTalk file download URL: {e}")
        return None

# Global logger reference
logger: Optional[logging.Logger] = None

def set_logger(logger_instance: logging.Logger):
    """Set the logger for DingTalk integration"""
    global logger
    logger = logger_instance

def get_ai_service_status() -> Dict[str, Any]:
    """Get AI service status and configuration"""
    return {
        "ai_service_available": AI_SERVICE_AVAILABLE,
        "dingtalk_available": DINGTALK_AVAILABLE,
        "ai_configured": bool(ai_service_config["api_key"] and ai_service_config["base_url"] and ai_service_config["model"]),
        "ai_config": {
            "api_key_configured": bool(ai_service_config["api_key"]),
            "base_url_configured": bool(ai_service_config["base_url"]),
            "model_configured": bool(ai_service_config["model"])
        }
    }

def configure_ai_service(api_key: str, base_url: str, model: str) -> bool:
    """Configure AI service settings"""
    global ai_service_config
    
    try:
        ai_service_config["api_key"] = api_key
        ai_service_config["base_url"] = base_url
        ai_service_config["model"] = model
        
        if logger:
            logger.info("AI service configuration updated")
        
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to configure AI service: {e}")
        return False

def get_conversation_history(session_id: str) -> List[Dict[str, str]]:
    """Get conversation history for a specific session"""
    global conversation_history_manager
    if conversation_history_manager is None:
        return []
    return conversation_history_manager.get_history(session_id)

def get_conversation_context(session_id: str, max_messages: int = 10) -> str:
    """Get formatted conversation context for a specific session"""
    global conversation_history_manager
    if conversation_history_manager is None:
        return ""
    return conversation_history_manager.get_formatted_context(session_id, max_messages)

def clear_conversation_history(session_id: str) -> bool:
    """Clear conversation history for a specific session"""
    global conversation_history_manager
    if conversation_history_manager is None:
        return False
    return conversation_history_manager.clear_history(session_id)

def get_all_sessions() -> List[str]:
    """Get all active session IDs"""
    global conversation_history_manager
    if conversation_history_manager is None:
        return []
    return conversation_history_manager.get_all_sessions()
