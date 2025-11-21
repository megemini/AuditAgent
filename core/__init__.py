"""
AI核心模块
提供统一的AI服务接口
"""

from .langchain_manager import LangChainManager, SessionConfig, ai_manager

__all__ = ['LangChainManager', 'SessionConfig', 'ai_manager']
