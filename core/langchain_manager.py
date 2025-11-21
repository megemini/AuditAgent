"""
基于LangChain的AI管理模块
提供统一的AI服务接口，支持会话管理和历史上下文
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import JsonOutputParser
from langchain.memory import ConversationBufferMemory

try:
    from reimbursement_rules import get_rules_manager
    REIMBURSEMENT_RULES_AVAILABLE = True
except ImportError:
    REIMBURSEMENT_RULES_AVAILABLE = False

# 配置日志
logger = logging.getLogger(__name__)

@dataclass
class SessionConfig:
    """会话配置"""
    session_id: str
    api_key: str
    base_url: str
    model: str
    max_history_length: int = 20
    system_prompt: str = ""
    reimbursement_rules: List[str] = field(default_factory=list)
    
class LangChainManager:
    """LangChain AI管理器"""
    
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.llm_instances: Dict[str, ChatOpenAI] = {}
        self.memories: Dict[str, ConversationBufferMemory] = {}
        
    def create_session(self, config: SessionConfig) -> bool:
        """创建新的AI会话"""
        try:
            # 初始化LLM实例
            llm = ChatOpenAI(
                openai_api_key=config.api_key,
                openai_api_base=config.base_url,
                model=config.model,
                temperature=0.3
            )
            
            # 初始化记忆
            memory = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True,
                max_token_limit=4000
            )
            
            # 构建系统提示词
            system_prompt = self._build_system_prompt(config)
            
            # 存储会话信息
            self.sessions[config.session_id] = {
                "config": config,
                "system_prompt": system_prompt,
                "created_at": datetime.now(),
                "last_used": datetime.now()
            }
            
            self.llm_instances[config.session_id] = llm
            self.memories[config.session_id] = memory
            
            logger.info(f"Created AI session: {config.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create session {config.session_id}: {e}")
            return False
    
    def _build_system_prompt(self, config: SessionConfig) -> str:
        """构建系统提示词"""
        base_prompt = config.system_prompt or """
你是一个财务报销专家，请基于以下财务报销规则对用户的问题进行详细分析和审核。

请始终：
1. 保持专业和客观
2. 基于提供的规则进行分析
3. 提供清晰的建议和结论
4. 保护用户隐私和数据安全
"""
        
        # 添加报销规则
        if config.reimbursement_rules:
            rules_text = "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(config.reimbursement_rules)])
            base_prompt += f"\n\n财务报销规则：\n{rules_text}"
        elif REIMBURSEMENT_RULES_AVAILABLE:
            # 如果没有提供规则但有规则管理器，使用默认规则
            try:
                rules_manager = get_rules_manager()
                default_rules = rules_manager.get_rules_for_ai_prompt()
                if default_rules and default_rules != "当前未配置财务报销规则":
                    base_prompt += f"\n\n{default_rules}"
                else:
                    base_prompt += "\n\n注意：当前未配置财务报销规则，请提示用户上传相关文档。"
            except Exception as e:
                logger.warning(f"Failed to get default rules: {e}")
                base_prompt += "\n\n注意：当前未配置财务报销规则，请提示用户上传相关文档。"
        else:
            base_prompt += "\n\n注意：当前未配置财务报销规则，请提示用户上传相关文档。"
        
        return base_prompt
    
    def update_reimbursement_rules(self, session_id: str, rules: List[str]) -> bool:
        """更新会话的报销规则"""
        if session_id not in self.sessions:
            logger.warning(f"Session {session_id} not found")
            return False
        
        try:
            self.sessions[session_id]["config"].reimbursement_rules = rules
            # 重新构建系统提示词
            config = self.sessions[session_id]["config"]
            system_prompt = self._build_system_prompt(config)
            self.sessions[session_id]["system_prompt"] = system_prompt
            
            logger.info(f"Updated reimbursement rules for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update rules for session {session_id}: {e}")
            return False
    
    async def chat(self, session_id: str, message: str, include_history: bool = True) -> str:
        """发送消息并获得AI回复"""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        try:
            session_data = self.sessions[session_id]
            llm = self.llm_instances[session_id]
            memory = self.memories[session_id]
            
            # 构建提示词模板
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", session_data["system_prompt"]),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}")
            ])
            
            # 构建链
            chain = prompt_template | llm
            
            # 准备输入
            inputs = {
                "input": message,
                "chat_history": memory.chat_memory.messages if include_history else []
            }
            
            # 调用链
            response = await chain.ainvoke(inputs)
            
            # 更新记忆
            memory.chat_memory.add_user_message(message)
            memory.chat_memory.add_ai_message(response.content)
            
            # 更新最后使用时间
            session_data["last_used"] = datetime.now()
            
            return response.content
            
        except Exception as e:
            logger.error(f"Error in chat for session {session_id}: {e}")
            raise
    
    async def extract_structured_data(self, session_id: str, content: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """提取结构化数据"""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        try:
            llm = self.llm_instances[session_id]
            
            # 使用JsonOutputParser
            parser = JsonOutputParser()
            
            # 构建提示词
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", self.sessions[session_id]["system_prompt"]),
                ("human", """请从以下内容中提取结构化信息：

{content}

请按照以下JSON格式返回：
{format_instructions}""")
            ])
            
            # 构建链
            chain = prompt_template | llm | parser
            
            # 调用链
            result = await chain.ainvoke({
                "content": content,
                "format_instructions": parser.get_format_instructions()
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error in extract_structured_data for session {session_id}: {e}")
            raise
    
    async def analyze_with_tools(self, session_id: str, message: str, tools: List[Any]) -> str:
        """使用工具进行分析"""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        try:
            llm = self.llm_instances[session_id]
            memory = self.memories[session_id]
            
            # 绑定工具
            llm_with_tools = llm.bind_tools(tools)
            
            # 构建提示词模板
            prompt_template = ChatPromptTemplate.from_messages([
                ("system", self.sessions[session_id]["system_prompt"]),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}")
            ])
            
            # 构建链
            chain = prompt_template | llm_with_tools
            
            # 准备输入
            inputs = {
                "input": message,
                "chat_history": memory.chat_memory.messages
            }
            
            # 调用链
            response = await chain.ainvoke(inputs)
            
            # 更新记忆
            memory.chat_memory.add_user_message(message)
            memory.chat_memory.add_ai_message(response.content)
            
            # 更新最后使用时间
            self.sessions[session_id]["last_used"] = datetime.now()
            
            return response.content
            
        except Exception as e:
            logger.error(f"Error in analyze_with_tools for session {session_id}: {e}")
            raise
    
    def get_session_history(self, session_id: str) -> List[Dict[str, str]]:
        """获取会话历史"""
        if session_id not in self.sessions:
            return []
        
        memory = self.memories[session_id]
        messages = memory.chat_memory.messages
        
        history = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                history.append({"role": "assistant", "content": msg.content})
        
        return history
    
    def clear_session_history(self, session_id: str) -> bool:
        """清空会话历史"""
        if session_id not in self.sessions:
            return False
        
        try:
            self.memories[session_id].clear()
            logger.info(f"Cleared history for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear history for session {session_id}: {e}")
            return False
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if session_id not in self.sessions:
            return False
        
        try:
            del self.sessions[session_id]
            del self.llm_instances[session_id]
            del self.memories[session_id]
            logger.info(f"Deleted session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        if session_id not in self.sessions:
            return None
        
        session_data = self.sessions[session_id]
        config = session_data["config"]
        
        return {
            "session_id": session_id,
            "model": config.model,
            "created_at": session_data["created_at"].isoformat(),
            "last_used": session_data["last_used"].isoformat(),
            "reimbursement_rules_count": len(config.reimbursement_rules),
            "history_length": len(self.memories[session_id].chat_memory.messages)
        }
    
    def list_sessions(self) -> List[str]:
        """列出所有会话ID"""
        return list(self.sessions.keys())

# 全局实例
ai_manager = LangChainManager()

def get_ai_manager() -> LangChainManager:
    """获取全局AI管理器实例"""
    return ai_manager
