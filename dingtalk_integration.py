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
from typing import Optional, Dict, Any

# DingTalk integration
try:
    import dingtalk_stream
    from dingtalk_stream import AckMessage
    DINGTALK_AVAILABLE = True
except ImportError:
    DINGTALK_AVAILABLE = False
    logging.warning("dingtalk-stream not available. DingTalk integration will be disabled.")

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

# Global AI service configuration
ai_service_config: Dict[str, Any] = {
    "document_server": None,
    "invoice_server": None,
    "api_key": None,
    "base_url": None,
    "model": None
}

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
    
    async def analyze_document(self, image_url: str = None, image_data: str = None, user_text: str = "") -> Dict[str, Any]:
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
                    ai_service_config["model"]
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
    """钉钉消息处理器，支持文本和图片消息，集成AI分析功能"""
    
    def __init__(self, logger: Optional[logging.Logger] = None, ai_client: Optional[AIServiceClient] = None):
        # Initialize the parent class
        try:
            super(dingtalk_stream.ChatbotHandler, self).__init__()
        except:
            # Fallback: just initialize without parent
            pass
        self.logger = logger
        self.ai_client = ai_client
        self.loop = None
    
    async def process(self, callback: dingtalk_stream.CallbackMessage):
        """处理钉钉消息，支持多种消息类型和AI分析"""
        try:
            if not DINGTALK_AVAILABLE:
                return AckMessage.STATUS_OK, 'OK'
                
            # 解析消息
            incoming_message = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
            
            if self.logger:
                self.logger.info(f"Received DingTalk message: {incoming_message}")
            
            # 根据消息类型处理
            reply_message = None
            
            if incoming_message.message_type == 'text':
                # 文本消息 - 进行AI分析
                if self.logger:
                    self.logger.info(f"Text message: {incoming_message.text.content}")
                
                # 如果有AI客户端，进行文本分析
                if self.ai_client and self.ai_client.connected:
                    try:
                        # 简单的文本分析响应
                        user_text = incoming_message.text.content
                        ai_result = await self.ai_client.analyze_document(user_text=user_text)
                        
                        if ai_result.get("success"):
                            # 格式化AI分析结果
                            doc_data = ai_result.get("document_data", {})
                            if isinstance(doc_data, dict):
                                formatted_result = "🤖 AI分析结果：\n\n"
                                for key, value in doc_data.items():
                                    if key != "document_type":
                                        formatted_result += f"📋 {key}: {value}\n"
                                reply_message = formatted_result
                            else:
                                reply_message = f"🤖 AI分析结果：\n{doc_data}"
                        else:
                            reply_message = f"❌ AI分析失败：{ai_result.get('message', '未知错误')}"
                    except Exception as e:
                        if self.logger:
                            self.logger.error(f"AI analysis error: {e}")
                        reply_message = f"❌ AI分析出错：{str(e)}"
                else:
                    reply_message = f"收到文本消息：{incoming_message.text.content}\n\n💡 提示：AI服务未启用，无法进行智能分析"
                
            elif incoming_message.message_type == 'picture':
                # 图片消息 - 进行AI分析
                if incoming_message.image_content and incoming_message.image_content.download_code:
                    download_code = incoming_message.image_content.download_code
                    if self.logger:
                        self.logger.info(f"Picture message detected, download code: {download_code}")
                    
                    # 获取访问令牌
                    access_token = get_dingtalk_access_token(dingtalk_app_key, dingtalk_app_secret)
                    if not access_token:
                        if self.logger:
                            self.logger.error("Failed to get access token for image download")
                        reply_message = "❌ 无法获取访问令牌，图片分析失败"
                    else:
                        # 获取下载URL
                        # 添加延迟以防止与get_dingtalk_access_token产生并发请求
                        time.sleep(0.5)
                        download_url = get_file_download_url(access_token, download_code, dingtalk_app_key)
                        if download_url:
                            if self.logger:
                                self.logger.info(f"Got download URL: {download_url}")
                            
                            # 如果有AI客户端，进行图片分析
                            if self.ai_client and self.ai_client.connected:
                                if self.logger:
                                    self.logger.info("AI client available, starting document analysis...")
                                try:
                                    # 使用文档分析
                                    if self.logger:
                                        self.logger.info(f"Calling analyze_document with image_url: {download_url[:50]}...")
                                    doc_result = await self.ai_client.analyze_document(image_url=download_url)
                                    if self.logger:
                                        self.logger.info(f"Document analysis result: {doc_result}")
                                    
                                    if doc_result.get("success"):
                                        doc_data = doc_result.get("document_data", {})
                                        if isinstance(doc_data, dict):
                                            formatted_result = "📄 文档识别结果：\n\n"
                                            for key, value in doc_data.items():
                                                if key != "document_type":
                                                    formatted_result += f"📋 {key}: {value}\n"
                                            reply_message = formatted_result
                                        else:
                                            reply_message = f"📄 文档识别结果：\n{doc_data}"
                                    else:
                                        reply_message = f"❌ 图片分析失败：{doc_result.get('message', '未知错误')}"
                                except Exception as e:
                                    if self.logger:
                                        self.logger.error(f"AI image analysis error: {e}", exc_info=True)
                                    reply_message = f"❌ 图片分析出错：{str(e)}"
                            else:
                                reply_message = f"📷 图片下载地址：\n{download_url}\n\n💡 提示：AI服务未启用，无法进行智能识别"
                        else:
                            reply_message = "❌ 获取图片下载地址失败"
                            if self.logger:
                                self.logger.warning("Failed to get download URL for image")
                else:
                    reply_message = "❌ 图片消息格式错误"
                
            elif incoming_message.message_type == 'richText':
                # 富文本消息
                if self.logger:
                    self.logger.info("Rich text message received")
                reply_message = "📝 收到富文本消息\n\n💡 提示：目前仅支持纯文本和图片的AI分析"
                
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
                reply_message = f"❓ 未知消息类型 {incoming_message.message_type}\n\n💡 提示：目前支持文本和图片消息的AI分析"
            
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
            return AckMessage.STATUS_OK, 'OK'

def start_dingtalk_bot(app_key: str, app_secret: str,
                      api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None) -> str:
    """Start DingTalk bot in a separate thread with AI service integration"""
    global dingtalk_bot_thread, dingtalk_bot_status, dingtalk_app_key, dingtalk_app_secret
    
    if not DINGTALK_AVAILABLE:
        dingtalk_bot_status = "❌ dingtalk-stream 库不可用"
        return dingtalk_bot_status
    
    if dingtalk_bot_thread and dingtalk_bot_thread.is_alive():
        dingtalk_bot_status = "✅ DingTalk 机器人已正在运行"
        return dingtalk_bot_status
    
    try:
        dingtalk_app_key = app_key
        dingtalk_app_secret = app_secret
        
        # Use a threading.Event to signal when the bot has started
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
                
                # Create handler instance with logger and AI client
                handler = DingTalkSimpleHandler(logger, ai_client)
                client.register_callback_handler(
                    dingtalk_stream.chatbot.ChatbotMessage.TOPIC,
                    handler
                )
                
                dingtalk_bot_status = "✅ DingTalk 机器人已启动" + (" (AI集成已启用)" if ai_client else " (无AI集成)")
                final_status[0] = dingtalk_bot_status  # Store the final status
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
        
        # Start the bot in a daemon thread
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
