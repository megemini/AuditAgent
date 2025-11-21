#!/usr/bin/env python3
"""
会话管理模块
提供统一的会话管理、历史记录和上下文管理功能
"""

import json
import time
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class Message:
    """消息数据结构"""
    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    message_id: Optional[str] = None

@dataclass
class SessionConfig:
    """会话配置数据结构"""
    session_id: str
    created_at: str
    last_activity: str
    max_messages: int = 100
    max_hours: int = 24  # 会话最大保存时间（小时）
    system_prompt: Optional[str] = None
    user_context: Optional[Dict[str, Any]] = None
    ai_config: Optional[Dict[str, Any]] = None

class SessionManager:
    """会话管理器 - 管理多个会话的消息历史和配置"""
    
    def __init__(self, max_sessions: int = 1000):
        """
        初始化会话管理器
        
        Args:
            max_sessions: 最大会话数量
        """
        self.sessions: Dict[str, SessionConfig] = {}
        self.messages: Dict[str, List[Message]] = {}
        self.max_sessions = max_sessions
        self.lock = threading.RLock()
        
        logger.info(f"会话管理器初始化完成，最大会话数: {max_sessions}")
    
    def create_session(self, session_id: str = None, system_prompt: str = None, 
                      max_messages: int = 100, max_hours: int = 24,
                      ai_config: Dict[str, Any] = None) -> str:
        """
        创建新会话
        
        Args:
            session_id: 会话ID，如果不提供则自动生成
            system_prompt: 系统提示词
            max_messages: 最大消息数
            max_hours: 会话最大保存时间（小时）
            ai_config: AI配置信息
        
        Returns:
            会话ID
        """
        with self.lock:
            if session_id is None:
                import uuid
                session_id = str(uuid.uuid4())
            
            # 检查会话是否已存在
            if session_id in self.sessions:
                logger.warning(f"会话 {session_id} 已存在，将重置")
                self.reset_session(session_id)
            
            current_time = datetime.now().isoformat()
            
            # 创建会话配置
            config = SessionConfig(
                session_id=session_id,
                created_at=current_time,
                last_activity=current_time,
                max_messages=max_messages,
                max_hours=max_hours,
                system_prompt=system_prompt,
                ai_config=ai_config or {}
            )
            
            self.sessions[session_id] = config
            self.messages[session_id] = []
            
            # 如果提供了系统提示词，添加系统消息
            if system_prompt:
                system_msg = Message(
                    role="system",
                    content=system_prompt,
                    timestamp=current_time,
                    session_id=session_id
                )
                self.messages[session_id].append(system_msg)
            
            # 检查会话数量限制
            self._cleanup_old_sessions()
            
            logger.info(f"创建新会话: {session_id}")
            return session_id
    
    def get_session(self, session_id: str) -> Optional[SessionConfig]:
        """获取会话配置"""
        with self.lock:
            return self.sessions.get(session_id)
    
    def session_exists(self, session_id: str) -> bool:
        """检查会话是否存在"""
        with self.lock:
            return session_id in self.sessions
    
    def add_message(self, session_id: str, role: str, content: str, 
                   metadata: Dict[str, Any] = None, message_id: str = None) -> bool:
        """
        添加消息到会话
        
        Args:
            session_id: 会话ID
            role: 消息角色 ('user', 'assistant', 'system', 'tool')
            content: 消息内容
            metadata: 元数据
            message_id: 消息ID
        
        Returns:
            是否添加成功
        """
        with self.lock:
            if session_id not in self.sessions:
                logger.warning(f"会话 {session_id} 不存在，无法添加消息")
                return False
            
            # 更新会话最后活动时间
            self.sessions[session_id].last_activity = datetime.now().isoformat()
            
            # 创建消息对象
            message = Message(
                role=role,
                content=content,
                timestamp=datetime.now().isoformat(),
                metadata=metadata or {},
                session_id=session_id,
                message_id=message_id
            )
            
            # 添加消息
            self.messages[session_id].append(message)
            
            # 限制消息数量
            max_messages = self.sessions[session_id].max_messages
            if len(self.messages[session_id]) > max_messages:
                # 保留系统消息和最近的消息
                system_msgs = [msg for msg in self.messages[session_id] if msg.role == 'system']
                other_msgs = [msg for msg in self.messages[session_id] if msg.role != 'system']
                other_msgs = other_msgs[-(max_messages - len(system_msgs)):]
                self.messages[session_id] = system_msgs + other_msgs
                logger.debug(f"会话 {session_id} 消息数量超限，已截断")
            
            return True
    
    def get_messages(self, session_id: str, include_system: bool = True,
                    max_messages: int = None) -> List[Message]:
        """
        获取会话消息
        
        Args:
            session_id: 会话ID
            include_system: 是否包含系统消息
            max_messages: 最大返回消息数
        
        Returns:
            消息列表
        """
        with self.lock:
            if session_id not in self.messages:
                return []
            
            messages = self.messages[session_id]
            
            # 过滤系统消息
            if not include_system:
                messages = [msg for msg in messages if msg.role != 'system']
            
            # 限制消息数量
            if max_messages:
                messages = messages[-max_messages:]
            
            return messages.copy()
    
    def get_context_for_llm(self, session_id: str, include_system: bool = True,
                           max_messages: int = 20) -> List[Dict[str, str]]:
        """
        获取适合LLM使用的上下文格式
        
        Args:
            session_id: 会话ID
            include_system: 是否包含系统消息
            max_messages: 最大消息数
        
        Returns:
            LLM格式的上下文列表
        """
        messages = self.get_messages(session_id, include_system, max_messages)
        
        context = []
        for msg in messages:
            context.append({
                "role": msg.role,
                "content": msg.content
            })
        
        return context
    
    def get_conversation_summary(self, session_id: str) -> str:
        """
        获取对话摘要
        
        Args:
            session_id: 会话ID
        
        Returns:
            对话摘要字符串
        """
        messages = self.get_messages(session_id, include_system=False, max_messages=10)
        
        if not messages:
            return "暂无对话记录"
        
        summary_lines = ["【对话摘要】"]
        for i, msg in enumerate(messages[-5:], 1):  # 只显示最近5条
            role_name = {"user": "用户", "assistant": "助手", "tool": "工具"}.get(msg.role, msg.role)
            content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            summary_lines.append(f"{i}. {role_name}: {content_preview}")
        
        return "\n".join(summary_lines)
    
    def update_session_config(self, session_id: str, **kwargs) -> bool:
        """
        更新会话配置
        
        Args:
            session_id: 会话ID
            **kwargs: 配置参数
        
        Returns:
            是否更新成功
        """
        with self.lock:
            if session_id not in self.sessions:
                return False
            
            config = self.sessions[session_id]
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            # 更新最后活动时间
            config.last_activity = datetime.now().isoformat()
            
            return True
    
    def set_system_prompt(self, session_id: str, system_prompt: str) -> bool:
        """
        设置系统提示词
        
        Args:
            session_id: 会话ID
            system_prompt: 系统提示词
        
        Returns:
            是否设置成功
        """
        with self.lock:
            if session_id not in self.sessions:
                return False
            
            # 更新配置
            self.sessions[session_id].system_prompt = system_prompt
            self.sessions[session_id].last_activity = datetime.now().isoformat()
            
            # 移除旧的系统消息
            self.messages[session_id] = [
                msg for msg in self.messages[session_id] if msg.role != 'system'
            ]
            
            # 添加新的系统消息
            system_msg = Message(
                role="system",
                content=system_prompt,
                timestamp=datetime.now().isoformat(),
                session_id=session_id
            )
            self.messages[session_id].insert(0, system_msg)
            
            return True
    
    def clear_session(self, session_id: str, keep_system_prompt: bool = True) -> bool:
        """
        清空会话消息
        
        Args:
            session_id: 会话ID
            keep_system_prompt: 是否保留系统提示词
        
        Returns:
            是否清空成功
        """
        with self.lock:
            if session_id not in self.sessions:
                return False
            
            config = self.sessions[session_id]
            config.last_activity = datetime.now().isoformat()
            
            if keep_system_prompt and config.system_prompt:
                # 只保留系统消息
                system_msgs = [msg for msg in self.messages[session_id] if msg.role == 'system']
                self.messages[session_id] = system_msgs
            else:
                self.messages[session_id] = []
            
            return True
    
    def reset_session(self, session_id: str) -> bool:
        """
        重置会话（清空所有消息和配置）
        
        Args:
            session_id: 会话ID
        
        Returns:
            是否重置成功
        """
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
            if session_id in self.messages:
                del self.messages[session_id]
            
            return True
    
    def get_all_sessions(self) -> List[str]:
        """获取所有会话ID"""
        with self.lock:
            return list(self.sessions.keys())
    
    def get_active_sessions(self, hours: int = 1) -> List[str]:
        """
        获取活跃会话（指定时间内有活动的会话）
        
        Args:
            hours: 时间范围（小时）
        
        Returns:
            活跃会话ID列表
        """
        with self.lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            active_sessions = []
            
            for session_id, config in self.sessions.items():
                last_activity = datetime.fromisoformat(config.last_activity)
                if last_activity > cutoff_time:
                    active_sessions.append(session_id)
            
            return active_sessions
    
    def _cleanup_old_sessions(self):
        """清理过期会话"""
        if len(self.sessions) <= self.max_sessions:
            return
        
        # 按最后活动时间排序
        sorted_sessions = sorted(
            self.sessions.items(),
            key=lambda x: x[1].last_activity
        )
        
        # 删除最旧的会话
        sessions_to_delete = len(self.sessions) - self.max_sessions + 100
        for i in range(sessions_to_delete):
            session_id = sorted_sessions[i][0]
            del self.sessions[session_id]
            if session_id in self.messages:
                del self.messages[session_id]
        
        logger.info(f"清理了 {sessions_to_delete} 个过期会话")
    
    def export_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        导出会话数据
        
        Args:
            session_id: 会话ID
        
        Returns:
            会话数据字典
        """
        with self.lock:
            if session_id not in self.sessions:
                return None
            
            return {
                "config": asdict(self.sessions[session_id]),
                "messages": [asdict(msg) for msg in self.messages[session_id]]
            }
    
    def import_session(self, session_data: Dict[str, Any]) -> bool:
        """
        导入会话数据
        
        Args:
            session_data: 会话数据字典
        
        Returns:
            是否导入成功
        """
        try:
            with self.lock:
                config_data = session_data["config"]
                messages_data = session_data["messages"]
                
                session_id = config_data["session_id"]
                
                # 导入配置
                self.sessions[session_id] = SessionConfig(**config_data)
                
                # 导入消息
                self.messages[session_id] = [Message(**msg_data) for msg_data in messages_data]
                
                # 清理旧会话
                self._cleanup_old_sessions()
                
                logger.info(f"导入会话成功: {session_id}")
                return True
                
        except Exception as e:
            logger.error(f"导入会话失败: {e}")
            return False

# 全局会话管理器实例
session_manager = SessionManager()

def get_session_manager() -> SessionManager:
    """获取全局会话管理器实例"""
    return session_manager

# 便捷函数
def create_session(session_id: str = None, system_prompt: str = None, **kwargs) -> str:
    """创建新会话的便捷函数"""
    return session_manager.create_session(session_id, system_prompt, **kwargs)

def add_message(session_id: str, role: str, content: str, **kwargs) -> bool:
    """添加消息的便捷函数"""
    return session_manager.add_message(session_id, role, content, **kwargs)

def get_messages(session_id: str, **kwargs) -> List[Message]:
    """获取消息的便捷函数"""
    return session_manager.get_messages(session_id, **kwargs)

def get_context_for_llm(session_id: str, **kwargs) -> List[Dict[str, str]]:
    """获取LLM上下文的便捷函数"""
    return session_manager.get_context_for_llm(session_id, **kwargs)
