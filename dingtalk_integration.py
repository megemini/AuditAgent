#!/usr/bin/env python3
"""
钉钉机器人集成模块
提供钉钉机器人的创建、启动、停止和管理功能
"""

import logging
import threading
import time
from typing import Optional

# DingTalk integration
try:
    import dingtalk_stream
    from dingtalk_stream import AckMessage
    DINGTALK_AVAILABLE = True
except ImportError:
    DINGTALK_AVAILABLE = False
    logging.warning("dingtalk-stream not available. DingTalk integration will be disabled.")

# Global DingTalk bot status
dingtalk_bot_thread: Optional[threading.Thread] = None
dingtalk_bot_status = "未启动"
dingtalk_app_key = ""
dingtalk_app_secret = ""

class DingTalkSimpleHandler(dingtalk_stream.ChatbotHandler):
    """钉钉消息处理器，支持文本和图片消息"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        # Initialize the parent class if dingtalk_stream is available
        if DINGTALK_AVAILABLE:
            try:
                # Try to initialize properly based on dingtalk_stream version
                super(dingtalk_stream.ChatbotHandler, self).__init__()
            except:
                # Fallback: just initialize without parent
                pass
        if logger:
            self.logger = logger

    async def process(self, callback: dingtalk_stream.CallbackMessage):
        """处理钉钉消息，支持多种消息类型"""
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
                # 文本消息
                if self.logger:
                    self.logger.info(f"Text message: {incoming_message.text.content}")
                reply_message = f"text: {incoming_message.text.content}"
                
            elif incoming_message.message_type == 'picture':
                # 图片消息
                if incoming_message.image_content and incoming_message.image_content.download_code:
                    download_code = incoming_message.image_content.download_code
                    if self.logger:
                        self.logger.info(f"Picture message detected, download code: {download_code}")
                    
                    # 获取访问令牌
                    access_token = get_dingtalk_access_token(dingtalk_app_key, dingtalk_app_secret)
                    if not access_token:
                        if self.logger:
                            self.logger.error("Failed to get access token for image download")
                        return AckMessage.STATUS_OK, 'OK'
                    
                    # 获取下载URL
                    download_url = get_file_download_url(access_token, download_code, dingtalk_app_key)
                    if download_url:
                        reply_message = f"picture: 下载地址：\n{download_url}"
                    else:
                        reply_message = "picture: 获取下载地址失败"
                        if self.logger:
                            self.logger.warning("Failed to get download URL for image")
                else:
                    reply_message = "picture: 图片消息格式错误"
                
            elif incoming_message.message_type == 'richText':
                # 富文本消息
                if self.logger:
                    self.logger.info("Rich text message received")
                reply_message = "richText: 收到富文本消息"
                
            elif incoming_message.message_type == 'audio':
                # 语音消息
                if self.logger:
                    self.logger.info("Audio message received")
                reply_message = "audio: 收到语音消息"
                
            elif incoming_message.message_type == 'video':
                # 视频消息
                if self.logger:
                    self.logger.info("Video message received")
                reply_message = "video: 收到视频消息"
                
            elif incoming_message.message_type == 'file':
                # 文件消息
                if self.logger:
                    self.logger.info("File message received")
                reply_message = "file: 收到文件消息"
                
            else:
                # 未知消息类型
                if self.logger:
                    self.logger.warning(f"Unknown message type: {incoming_message.message_type}")
                reply_message = f"unknown: 未知消息类型 {incoming_message.message_type}"
            
            # 使用reply_text回复消息类型
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

def start_dingtalk_bot(app_key: str, app_secret: str) -> str:
    """Start DingTalk bot in a separate thread"""
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
        
        def run_dingtalk_bot():
            global dingtalk_bot_status
            try:
                dingtalk_bot_status = "🔄 DingTalk 机器人启动中..."
                if logger:
                    logger.info("Starting DingTalk bot...")
                
                credential = dingtalk_stream.Credential(app_key, app_secret)
                client = dingtalk_stream.DingTalkStreamClient(credential)
                
                # Create handler instance with logger
                handler = DingTalkSimpleHandler(logger)
                client.register_callback_handler(
                    dingtalk_stream.chatbot.ChatbotMessage.TOPIC, 
                    handler
                )
                
                dingtalk_bot_status = "✅ DingTalk 机器人已启动"
                if logger:
                    logger.info("DingTalk bot started successfully")
                client.start_forever()
                
            except Exception as e:
                dingtalk_bot_status = f"❌ DingTalk 机器人启动失败: {str(e)}"
                if logger:
                    logger.error(f"Failed to start DingTalk bot: {e}")
        
        # Start the bot in a daemon thread
        dingtalk_bot_thread = threading.Thread(target=run_dingtalk_bot, daemon=True)
        dingtalk_bot_thread.start()
        
        # Wait a moment for the bot to initialize
        time.sleep(2)
        return dingtalk_bot_status
        
    except Exception as e:
        dingtalk_bot_status = f"❌ DingTalk 机器人启动失败: {str(e)}"
        return dingtalk_bot_status

def stop_dingtalk_bot() -> str:
    """Stop DingTalk bot"""
    global dingtalk_bot_thread, dingtalk_bot_status
    
    # We can't actually stop the dingtalk client easily since it runs forever
    # The daemon thread will be terminated when the main program exits
    dingtalk_bot_status = "⏹️ DingTalk 机器人将在程序退出时停止"
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
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json().get("accessToken")
        else:
            logger.error(f"Failed to get access token: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error getting access token: {e}")
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
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json().get("downloadUrl")
        else:
            logger.error(f"Failed to get download URL: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error getting download URL: {e}")
        return None

# Global logger reference
logger: Optional[logging.Logger] = None

def set_logger(logger_instance: logging.Logger):
    """Set the logger for DingTalk integration"""
    global logger
    logger = logger_instance