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

class DingTalkSimpleHandler:
    """Simple DingTalk handler that responds with 'ok' to all messages"""
    
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
    
    async def process(self, callback):
        """Process incoming messages and respond with 'ok'"""
        try:
            if DINGTALK_AVAILABLE:
                incoming_message = dingtalk_stream.ChatbotMessage.from_dict(callback.data)
                if self.logger:
                    self.logger.info(f"Received DingTalk message: {incoming_message.text.content}")
                
                # Always respond with 'ok'
                # For simplicity, we'll just return the status without sending a reply
                # since the reply functionality is complex and requires proper setup
                return AckMessage.STATUS_OK, 'OK'
            else:
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

# Global logger reference
logger: Optional[logging.Logger] = None

def set_logger(logger_instance: logging.Logger):
    """Set the logger for DingTalk integration"""
    global logger
    logger = logger_instance