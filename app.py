import gradio as gr
import openai
import os
import json
from typing import List, Dict, Any
import tempfile
import fitz  # PyMuPDF
from docx import Document
from uuid import uuid4
import asyncio
import logging
import threading
import base64
import uuid
import shutil
import time
from contextlib import AsyncExitStack
from dotenv import load_dotenv

# DingTalk integration
from dingtalk_integration import (
    is_dingtalk_available,
    set_logger,
    start_dingtalk_bot,
    stop_dingtalk_bot,
    get_dingtalk_status,
    configure_ai_service
)

DINGTALK_AVAILABLE = is_dingtalk_available()

from fastmcp.client import Client
from fastmcp.client.transports import PythonStdioTransport
from openai import AsyncOpenAI

# 会话存储（模拟）
session_store = {}

# 全局MCP服务器连接状态
global_city_server_status = ""
global_invoice_server_status = ""
global_datetime_server_status = ""

# 配置日志
import sys
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ],
    force=True
)
logger = logging.getLogger(__name__)

# DingTalk bot thread and status - imported from dingtalk_integration
dingtalk_bot_thread = None
dingtalk_bot_status = get_dingtalk_status()
dingtalk_app_key = ""
dingtalk_app_secret = ""

# Set the logger for dingtalk integration
set_logger(logger)

# Load environment variables from .env file
load_dotenv()

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

def load_config_from_env():
    """从.env文件中加载配置"""
    config = {
        "api_key_input": os.getenv("api_key_input", ""),
        "base_url_input": os.getenv("base_url_input", "https://aistudio.baidu.com/llm/lmapi/v3"),
        "model_input": os.getenv("model_input", "ernie-4.5-turbo-vl-preview"),
        "dingtalk_app_key": os.getenv("dingtalk_app_key", ""),
        "dingtalk_app_secret": os.getenv("dingtalk_app_secret", "")
    }
    logger.info(f"Configuration loaded from .env file: api_key={'***' if config['api_key_input'] else 'not set'}, base_url_input={'set' if config['base_url_input'] else 'not set'}, model_input={'set' if config['model_input'] else 'not set'}, dingtalk_app_key={'***' if config['dingtalk_app_key'] else 'not set'}, dingtalk_app_secret={'***' if config['dingtalk_app_secret'] else 'not set'}")
    return config

def start_dingtalk_bot_with_ai(dingtalk_app_key: str, dingtalk_app_secret: str, session_id: str) -> str:
    """启动带AI服务的钉钉机器人，使用已有的OpenAI配置"""
    try:
        # 获取有效的会话ID和OpenAI配置
        api_key = None
        base_url = None
        model = None
        
        # 首先尝试使用传入的session_id
        if session_id and session_id in session_store:
            api_key = os.environ.get(f"OPENAI_API_KEY_{session_id}")
            base_url = os.environ.get(f"OPENAI_BASE_URL_{session_id}")
            model = os.environ.get(f"OPENAI_MODEL_{session_id}")
        
        # 如果传入的session_id无效，尝试获取第一个有效会话
        if not api_key or not base_url or not model:
            for sid, session_data in session_store.items():
                test_api_key = os.environ.get(f"OPENAI_API_KEY_{sid}")
                test_base_url = os.environ.get(f"OPENAI_BASE_URL_{sid}")
                test_model = os.environ.get(f"OPENAI_MODEL_{sid}")
                
                if test_api_key and test_base_url and test_model:
                    api_key = test_api_key
                    base_url = test_base_url
                    model = test_model
                    session_id = sid
                    logger.info(f"Using session {sid} for DingTalk bot configuration")
                    break
        
        if not api_key or not base_url or not model:
            return "❌ 请先在 Step 1 中配置 OpenAI API 设置并确保连接成功"
        
        # 配置AI服务
        configure_ai_service(api_key, base_url, model)
        logger.info(f"AI service configured for DingTalk bot using session {session_id}")
        
        # 启动钉钉机器人
        result = start_dingtalk_bot(dingtalk_app_key, dingtalk_app_secret, api_key, base_url, model)
        return result
    except Exception as e:
        logger.error(f"Failed to start DingTalk bot with AI: {e}")
        return f"❌ 启动失败: {str(e)}"

def cleanup_upload_files():
    """清理upload_files文件夹中不是当天上传的文件"""
    import time
    from datetime import datetime
    
    upload_dir = os.path.join(os.getcwd(), "upload_files")
    if not os.path.exists(upload_dir):
        return
    
    current_time = time.time()
    current_date = datetime.now().date()
    
    for filename in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, filename)
        if os.path.isfile(file_path):
            # 获取文件的修改时间
            file_mtime = os.path.getmtime(file_path)
            file_date = datetime.fromtimestamp(file_mtime).date()
            
            # 如果文件不是今天创建的，则删除
            if file_date != current_date:
                try:
                    os.remove(file_path)
                    logger.info(f"已删除旧文件: {filename}")
                except Exception as e:
                    logger.error(f"删除文件 {filename} 失败: {e}")




class FastMCPStdioClientWrapper:
    def __init__(self):
        self.sessions: Dict[str, Client] = {}  # 存储多个服务器连接
        self.exit_stacks: Dict[str, AsyncExitStack] = {}  # 存储多个服务器的exit_stack
        self.tools: Dict[str, List[Dict[str, Any]]] = {}  # 存储每个服务器的工具
        self.connected_servers: List[str] = []  # 已连接的服务器列表

    # ------------------------- 连接 -------------------------
    def connect(self, server_command: List[str], server_name: str) -> str:
        """同步封装，方便 Gradio 直接调用"""
        logger.info(f"开始连接MCP服务器: {server_name}")
        logger.debug(f"服务器命令: {server_command}")
        connect_start_time = time.time()
        
        result = loop.run_until_complete(self._connect(server_command, server_name))
        
        connect_end_time = time.time()
        logger.info(f"MCP服务器连接完成，耗时: {connect_end_time - connect_start_time:.2f}秒")
        
        return result

    async def _connect(self, server_command: List[str], server_name: str) -> str:
        logger.debug(f"开始异步连接MCP服务器: {server_name}")
        
        # 关闭该服务器的旧连接
        if server_name in self.exit_stacks:
            logger.debug(f"关闭服务器 {server_name} 的旧连接")
            await self.exit_stacks[server_name].aclose()
        
        self.exit_stacks[server_name] = AsyncExitStack()
        logger.debug(f"为服务器 {server_name} 创建新的AsyncExitStack")

        try:
            # 使用 PythonStdioTransport 创建 Client
            if len(server_command) >= 2 and server_command[0] == "python":
                script_path = server_command[1]
                logger.debug(f"使用PythonStdioTransport，脚本路径: {script_path}")
                transport = PythonStdioTransport(script_path)
            else:
                # 如果不是标准的 python 命令，使用通用的方式
                logger.debug(f"使用StdioTransport，命令: {server_command[0]}, 参数: {server_command[1:]}")
                from fastmcp.client.transports import StdioTransport
                transport = StdioTransport(command=server_command[0], args=server_command[1:])

            # 创建 Client 并进入上下文
            logger.debug("创建MCP客户端...")
            client = Client(transport)
            self.sessions[server_name] = await self.exit_stacks[server_name].enter_async_context(client)
            logger.debug(f"MCP客户端创建成功，服务器: {server_name}")

            # 拉取工具
            logger.debug(f"拉取服务器 {server_name} 的工具列表...")
            tools_resp = await self.sessions[server_name].list_tools()
            logger.debug(f"获取到 {len(tools_resp)} 个工具")
            
            self.tools[server_name] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                }
                for tool in tools_resp
            ]
            
            tool_names = [t['function']['name'] for t in self.tools[server_name]]
            logger.debug(f"服务器 {server_name} 的工具列表: {tool_names}")
            
            # 添加到已连接服务器列表
            if server_name not in self.connected_servers:
                self.connected_servers.append(server_name)
                logger.info(f"服务器 {server_name} 添加到已连接列表")
            
            result = f"✅ Connected to {server_name}. Available tools: {', '.join(tool_names)}"
            logger.info(f"服务器 {server_name} 连接成功")
            
            return result
            
        except Exception as e:
            logger.error(f"连接服务器 {server_name} 失败: {str(e)}")
            
            # 清理失败的连接
            if server_name in self.exit_stacks:
                try:
                    await self.exit_stacks[server_name].aclose()
                    logger.debug("已清理失败的exit_stack")
                except:
                    pass
                del self.exit_stacks[server_name]
            
            if server_name in self.sessions:
                del self.sessions[server_name]
                logger.debug("已清理失败的session")
            
            if server_name in self.tools:
                del self.tools[server_name]
                logger.debug("已清理失败的工具列表")
            
            if server_name in self.connected_servers:
                self.connected_servers.remove(server_name)
                logger.debug("已从已连接列表中移除")
            
            return f"❌ Failed to connect to {server_name}: {str(e)}"
    
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """获取所有已连接服务器的工具"""
        all_tools = []
        for server_name in self.connected_servers:
            if server_name in self.tools:
                all_tools.extend(self.tools[server_name])
        return all_tools
    
    def get_server_for_tool(self, tool_name: str) -> str | None:
        """根据工具名称获取对应的服务器名称"""
        for server_name in self.connected_servers:
            if server_name in self.tools:
                for tool in self.tools[server_name]:
                    if tool['function']['name'] == tool_name:
                        return server_name
        return None
    
    def test_connection(self, server_command: List[str], server_name: str) -> str:
        """测试服务器连接"""
        return loop.run_until_complete(self._test_connection(server_command, server_name))
    
    async def _test_connection(self, server_command: List[str], server_name: str) -> str:
        """测试服务器连接的异步实现"""
        try:
            # 尝试创建临时连接进行测试
            temp_exit_stack = AsyncExitStack()

            # 创建传输层
            if len(server_command) >= 2 and server_command[0] == "python":
                script_path = server_command[1]
                transport = PythonStdioTransport(script_path)
            else:
                from fastmcp.client.transports import StdioTransport
                transport = StdioTransport(command=server_command[0], args=server_command[1:])

            # 创建临时客户端
            temp_client = Client(transport)
            temp_session = await temp_exit_stack.enter_async_context(temp_client)

            # 尝试获取工具列表来验证连接
            await temp_session.list_tools()

            # 清理临时连接
            await temp_exit_stack.aclose()

            return f"✅ Connection test successful for {server_name}. Server is responding."
            
        except Exception as e:
            logger.error(f"Connection test failed for {server_name} with command {server_command}: {str(e)}")
            return f"❌ Connection test failed for {server_name}: {str(e)}"

# 全局MCP客户端
global_mcp_client = FastMCPStdioClientWrapper()

def init_session():
    session_id = str(uuid4())
    session_store[session_id] = {
        "client": None,
        "model": None,
        "reimbursement_rules": []
    }
    return session_id

def test_and_store_client(api_key: str, base_url: str, model: str, session_id: str):
    """Test OpenAI API connection and store client in session"""
    try:
        # Set up the OpenAI client
        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        # Test the connection with a simple request
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hello, this is a test."}],
            max_tokens=10,
            extra_body={
                "enable_thinking": False
            }
        )
        
        # Store client and model in session
        session_store[session_id]["client"] = client
        session_store[session_id]["model"] = model
        
        # Save API credentials to environment variables with session_id
        os.environ[f"OPENAI_API_KEY_{session_id}"] = api_key
        os.environ[f"OPENAI_BASE_URL_{session_id}"] = base_url
        os.environ[f"OPENAI_MODEL_{session_id}"] = model
        os.environ[f"SESSION_ID"] = session_id
        
        return "✅ 连接成功！API 配置有效。"
    except Exception as e:
        return f"❌ 连接失败: {str(e)}"

def load_example_text():
    """Load example invoice rules text"""
    try:
        example_path = os.path.join("examples", "invoice_rules.txt")
        if os.path.exists(example_path):
            with open(example_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # 添加免责声明
                disclaimer = """
【免责声明】
本示例文本仅供参考学习使用，不构成任何法律或财务建议。
实际财务报销制度应根据公司具体情况、行业特点和当地法律法规进行定制。
使用本示例前，请务必咨询专业的财务、法律顾问，并根据实际需求进行适当修改。
对于因直接使用或参考本示例而产生的任何损失，开发者不承担任何责任。

----------------------------------------
"""
                
                return f"✅ 示例文本加载成功！\n\n{disclaimer}{content}"
        else:
            return "❌ 示例文件不存在：examples/invoice_rules.txt"
    except Exception as e:
        return f"❌ 加载示例文件失败: {str(e)}"


def upload_example_document():
    """Upload example document as a file object"""
    try:
        example_path = os.path.join("examples", "invoice_rules.txt")
        if os.path.exists(example_path):
            # Create a temporary file to return as a file-like object
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
            
            # Read the example content and write to temp file
            with open(example_path, 'r', encoding='utf-8') as f:
                content = f.read()
                temp_file.write(content)
            
            temp_file.close()
            
            # Return the path of the temporary file
            return temp_file.name
        else:
            return None
    except Exception as e:
        print(f"Error uploading example document: {e}")
        return None


def extract_reimbursement_rules_with_session(files, session_id: str):
    """Extract reimbursement rules from uploaded documents using session client"""
    if not files:
        return "❌ 请先上传文档", []
    
    session_data = session_store.get(session_id, {})
    client = session_data.get("client")
    model = session_data.get("model")
    
    if not client or not model:
        return "❌ 请先在 Step 1 中配置并测试 OpenAI API 连接", []
    
    try:
        # Run cleanup before processing new files
        cleanup_upload_files()
        
        # Process uploaded files
        document_text = ""
        for file in files:
            try:
                if file.name.endswith('.txt'):
                    with open(file.name, 'r', encoding='utf-8') as f:
                        document_text += f.read() + "\n\n"
                elif file.name.endswith('.pdf'):
                    # PDF processing using PyMuPDF
                    pdf_document = fitz.open(file.name)
                    pdf_text = ""
                    for page_num in range(len(pdf_document)):
                        page = pdf_document.load_page(page_num)
                        pdf_text += page.get_text()
                    pdf_document.close()
                    document_text += f"=== PDF文件: {file.name} ===\n{pdf_text}\n\n"
                elif file.name.endswith('.docx'):
                    # Word document processing using python-docx
                    doc = Document(file.name)
                    doc_text = ""
                    for paragraph in doc.paragraphs:
                        doc_text += paragraph.text + "\n"
                    document_text += f"=== Word文档: {file.name} ===\n{doc_text}\n\n"
                elif file.name.endswith('.doc'):
                    # For .doc files, we'll note that they need conversion
                    document_text += f"=== Word文档 (.doc): {file.name} ===\n请将 .doc 文件转换为 .docx 格式以便处理\n\n"
            except Exception as e:
                document_text += f"=== 文件处理错误: {file.name} ===\n错误: {str(e)}\n\n"
        
        # Create prompt for rule extraction
        prompt = f"""
        请从以下文档内容中提取所有关于财务报销的规则，并以JSON格式返回。
        返回格式应该是一个规则列表，每个规则包含以下字段：
        - rule_name: 规则名称
        - rule_description: 规则描述
        - rule_category: 规则类别（如：差旅费、办公用品、业务招待等）
        
        文档内容：
        {document_text}
        """
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            extra_body={
                "enable_thinking": False
            }
        )
        
        # Parse the response to extract rules
        rules_text = response.choices[0].message.content
        
        # Try to parse as JSON, if fails, return as text
        try:
            # Extract JSON from the response if it's wrapped in markdown code blocks
            if "```json" in rules_text:
                json_start = rules_text.find("```json") + 7
                json_end = rules_text.find("```", json_start)
                rules_json = rules_text[json_start:json_end].strip()
                rules = json.loads(rules_json)
            else:
                rules = json.loads(rules_text)
            
            # Store rules in session
            session_store[session_id]["reimbursement_rules"] = rules
            return "✅ 规则提取成功！", rules
        except json.JSONDecodeError:
            # If JSON parsing fails, return the raw text
            return "⚠️ 规则已提取，但JSON解析失败，请查看原始文本", rules_text
        
    except Exception as e:
        return f"❌ 处理失败: {str(e)}", []

def answer_question_with_session(question, history, session_id: str, file_upload=None):
    """Answer user's question with streaming output support"""
    logger.info("开始处理用户问题...")
    answer_start_time = time.time()
    
    logger.info(f"问题内容: {question}")
    logger.info(f"会话ID: {session_id}")
    logger.info(f"文件上传: {'提供' if file_upload else '未提供'}")
    
    if not question.strip():
        logger.info("问题为空，返回空响应")
        yield "", history, None  # Return None for file_upload to clear it
        return

    session_data = session_store.get(session_id, {})
    client = session_data.get("client")
    model = session_data.get("model")
    reimbursement_rules = session_data.get("reimbursement_rules", [])
    mcp_client = global_mcp_client

    logger.info(f"会话数据状态: client={'存在' if client else '不存在'}, "
               f"model={'存在' if model else '不存在'}, "
               f"报销规则数量: {len(reimbursement_rules)}")
    logger.info(f"MCP客户端状态: 已连接服务器数量: {len(mcp_client.connected_servers)}")
    if mcp_client.connected_servers:
        logger.info(f"已连接的服务器: {', '.join(mcp_client.connected_servers)}")

    # Add user question to history first
    history = history + [{"role": "user", "content": question}]
    logger.info("用户问题已添加到历史记录")
    yield "", history, None  # Return None for file_upload to clear it after sending

    if not reimbursement_rules:
        logger.warning("未找到报销规则，提示用户先上传文档")
        response = "❌ 请先在 Step 2 中上传文档并提取财务报销规则。"
        history.append({"role": "assistant", "content": response})
        yield "", history, None
        return

    if not client or not model:
        logger.warning("未找到OpenAI客户端或模型，提示用户先配置API")
        response = "❌ 请先在 Step 1 中配置 OpenAI API 设置。"
        history.append({"role": "assistant", "content": response})
        yield "", history, None
        return

    try:
        logger.info("开始处理查询，支持流式多工具调用...")
        process_start_time = time.time()
        
        # Process the query with streaming multi-tool support
        async def stream_process():
            logger.info("创建异步流处理生成器...")
            async for updated_history in _process_query_with_tools_streaming(
                question, history, session_id, file_upload, client, model, reimbursement_rules, mcp_client
            ):
                logger.info("流处理生成器产生新的历史记录")
                yield "", updated_history

        # Run the async generator
        logger.info("运行异步生成器...")
        async_gen = stream_process()
        while True:
            try:
                result = loop.run_until_complete(async_gen.__anext__())
                # result is already a tuple with (empty_string, updated_history)
                # add None for file_upload clearing
                yield result[0], result[1], None
            except StopAsyncIteration:
                logger.info("异步生成器迭代完成")
                break
        
        process_end_time = time.time()
        logger.info(f"查询处理完成，耗时: {process_end_time - process_start_time:.2f}秒")

    except Exception as e:
        logger.error(f"处理问题时出错: {str(e)}")
        error_response = f"❌ 回答问题时出错: {str(e)}"
        history.append({"role": "assistant", "content": error_response})
        yield "", history, None
    
    answer_end_time = time.time()
    logger.info(f"用户问题处理完成，总耗时: {answer_end_time - answer_start_time:.2f}秒")


async def _process_query_with_tools_streaming(question, history, session_id: str, file_upload, client, model, reimbursement_rules, mcp_client):
    """Process query with streaming multi-tool calling support"""
    logger.info("开始处理查询，支持流式多工具调用...")
    process_start_time = time.time()
    
    logger.info(f"问题: {question}")
    logger.info(f"历史记录数量: {len(history)}")
    logger.info(f"文件上传: {'提供' if file_upload else '未提供'}")
    logger.info(f"报销规则数量: {len(reimbursement_rules)}")
    logger.info(f"已连接MCP服务器: {mcp_client.connected_servers}")
    if mcp_client.connected_servers:
        logger.info(f"已连接的服务器: {', '.join(mcp_client.connected_servers)}")
    
    # Create context with rules
    logger.info("创建规则上下文...")
    rules_context = json.dumps(reimbursement_rules, ensure_ascii=False, indent=2)
    logger.info(f"规则上下文长度: {len(rules_context)}字符")

    # Build conversation messages from history (including all previous messages)
    logger.info("构建对话消息...")
    claude_messages = []
    for msg in history:  # Include all history messages
        if isinstance(msg, dict):
            role, content = msg.get("role"), msg.get("content")
            if role in ["user", "assistant", "system"] and content:
                # Skip metadata-only messages to keep conversation clean
                if not (role == "assistant" and ("🤔 AI正在思考" in content or "🔧 使用工具:" in content)):
                    claude_messages.append({"role": role, "content": content})
    
    logger.info(f"构建了 {len(claude_messages)} 条对话消息")

    # Prepare the main prompt with step-by-step audit instructions
    logger.info("准备主要提示...")
    base_prompt = f"""
    你是一个财务报销专家，请基于以下财务报销规则对用户的问题进行详细分析和审核。

    财务报销规则：
    {rules_context}

    用户问题：{question}

    **重要：如果用户上传了单据或要求审核单据，请按以下步骤进行逐条验证的审核流程：**

    **第一步：单据识别**
    - 使用 recognize_document 工具识别单据信息
    - 提取单据的关键信息：金额、日期、城市、类型等
    - 该工具支持多种单据类型：发票、收据、合同、订单、报销单等
    - 支持灵活的 JSON 格式输出，不严格限制字段结构

    **第二步：逐条规则验证**
    - **一次只验证一条规则，按顺序进行**
    - **每条规则验证时，如果需要额外信息，就调用相应的MCP工具**
    - **验证完一条规则后，立即给出该规则的验证结果**
    - **然后继续验证下一条规则**

    **验证流程示例**：
    ```
    正在验证规则1：[规则名称]
    → 需要获取当前时间 → 调用 get_current_time 工具
    → 验证结果：✅ 符合 / ❌ 不符合 / ⚠️ 需注意
    → 详细说明：[具体验证过程和结果]

    正在验证规则2：[规则名称]
    → 需要查询城市分级 → 调用 query_city_tier 工具
    → 验证结果：✅ 符合 / ❌ 不符合 / ⚠️ 需注意
    → 详细说明：[具体验证过程和结果]

    ... 继续验证其他规则
    ```

    **第三步：汇总审核结果**
    - 只有在所有规则都验证完成后，才生成最终的审核报告
    - 统计所有规则的验证结果
    - 给出最终结论和改进建议

    **重要原则**：
    - 🔄 **逐条进行**：一次只验证一条规则，不要批量处理
    - 🛠️ **按需调用工具**：只有当验证某条规则需要额外信息时，才调用相应工具
    - 📝 **即时反馈**：每验证完一条规则，立即给出该规则的结果
    - 🎯 **最后汇总**：所有规则验证完成后，再生成最终的审核报告
    - ✅ **不中断流程**：即使某条规则不符合，也要继续验证其他规则

    **可用的MCP工具**（按需调用）：
    - recognize_document: 识别单据信息（支持发票、收据、合同、订单等多种单据类型）
    - get_current_time: 获取当前时间（用于时间相关规则验证）
    - query_city_tier: 查询单个城市分级（用于城市标准相关规则验证）
    - query_multiple_cities: 批量查询多个城市分级
    - get_cities_by_tier: 获取指定分级的所有城市

    会话ID: {session_id}
    """

    # Only add the main message if this is the first question (not a follow-up)
    # Check if we already have conversation history
    has_previous_conversation = len(claude_messages) > 1

    if not has_previous_conversation:
        # This is the first question, add the main message with full context
        main_message = await _prepare_main_message(question, file_upload, session_id, rules_context, base_prompt)
        claude_messages.append(main_message)
    else:
        # This is a follow-up question, just add the user question without repeating the full context
        claude_messages.append({"role": "user", "content": question})

    # Get MCP tools if available
    mcp_tools = []
    if mcp_client and mcp_client.connected_servers:
        mcp_tools = mcp_client.get_all_tools()

    # Process with streaming multi-tool calling
    current_history = history.copy()
    max_iterations = 8  # Increase iterations for multi-step audit process
    iteration = 0
    invoice_recognized = False  # Track if invoice has been recognized
    rules_validation_started = False  # Track if rules validation has started

    while iteration < max_iterations:
        iteration += 1

        # Show "AI thinking" indicator before making API call
        thinking_msg = {
            "role": "assistant",
            "content": "🤔 AI正在思考中...",
            "metadata": {
                "title": f"AI思考 - 第{iteration}轮分析",
                "status": "pending",
                "id": f"thinking_{iteration}"
            }
        }
        current_history.append(thinking_msg)
        yield current_history

        # Make the API call with or without tools
        current_messages = claude_messages.copy()

        response = client.chat.completions.create(
            model=model,
            messages=current_messages,
            temperature=0.3,
            tools=mcp_tools if mcp_tools else None,
            tool_choice="auto" if mcp_tools else None,
            extra_body={
                "enable_thinking": False
            }
        )

        # Remove the "thinking" message and replace with actual response
        current_history.pop()  # Remove the thinking message

        assistant_msg = response.choices[0].message

        # Add assistant response to history and yield immediately
        if assistant_msg.content:
            current_history.append({
                "role": "assistant",
                "content": assistant_msg.content
            })
            yield current_history

        # Check if there are tool calls
        if assistant_msg.tool_calls and mcp_client:
            # Process all tool calls in this iteration
            tool_results = []

            for call in assistant_msg.tool_calls:
                tool_name = call.function.name
                tool_args = json.loads(call.function.arguments)

                # Track if invoice recognition tool was called
                if tool_name == "recognize_single_invoice":
                    invoice_recognized = True

                # Add tool call message to history and yield
                current_history.append({
                    "role": "assistant",
                    "content": f"🔧 使用工具: {tool_name}",
                    "metadata": {
                        "title": f"Tool: {tool_name}",
                        "log": f"参数: {json.dumps(tool_args, ensure_ascii=False)}",
                        "status": "pending",
                        "id": f"tool_call_{tool_name}_{iteration}"
                    }
                })
                yield current_history

                # Execute the tool
                try:
                    tool_result = await _execute_tool(tool_name, tool_args, session_id, mcp_client)
                    tool_results.append((call.id, tool_name, tool_result))

                    # Update the tool call status to done
                    if current_history and "metadata" in current_history[-1]:
                        current_history[-1]["metadata"]["status"] = "done"
                        # Update content to show completion
                        current_history[-1]["content"] = f"✅ 工具完成: {tool_name}"

                    # Add tool result to history and yield
                    current_history.append({
                        "role": "assistant",
                        "content": f"📊 工具结果: {tool_name}",
                        "metadata": {
                            "title": f"Result: {tool_name}",
                            "status": "done",
                            "id": f"result_{tool_name}_{iteration}"
                        }
                    })

                    # Format and add the actual result
                    if isinstance(tool_result, dict):
                        formatted_result = json.dumps(tool_result, ensure_ascii=False, indent=2)
                    elif isinstance(tool_result, list):
                        formatted_result = "\n".join(map(str, tool_result))
                    else:
                        formatted_result = str(tool_result)

                    current_history.append({
                        "role": "assistant",
                        "content": f"```\n{formatted_result}\n```",
                        "metadata": {"title": "Raw Output"}
                    })
                    yield current_history

                except Exception as e:
                    # Update the tool call status to error
                    if current_history and "metadata" in current_history[-1]:
                        current_history[-1]["metadata"]["status"] = "error"
                        current_history[-1]["content"] = f"❌ 工具执行失败: {tool_name}"

                    error_msg = f"❌ 执行工具 '{tool_name}' 时出错: {str(e)}"
                    current_history.append({
                        "role": "assistant",
                        "content": error_msg,
                        "metadata": {
                            "title": f"Error: {tool_name}",
                            "status": "error"
                        }
                    })
                    tool_results.append((call.id, tool_name, error_msg))
                    yield current_history

            # Add tool calls and results to conversation history
            claude_messages.append({
                "role": "assistant",
                "content": assistant_msg.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments}
                    } for call in assistant_msg.tool_calls
                ]
            })

            # Add tool results to conversation
            for call_id, tool_name, tool_result in tool_results:
                claude_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": str(tool_result)
                })

            # Continue the loop to allow for more tool calls
            continue
        else:
            # No more tool calls
            # Check if we need to continue with rule validation based on content analysis
            if invoice_recognized and _should_continue_audit(claude_messages, reimbursement_rules, iteration):
                # Check if we have completed rule validation by looking at the conversation
                conversation_text = " ".join([msg.get("content", "") for msg in claude_messages[-3:] if isinstance(msg.get("content"), str)])

                # Check if we have a comprehensive audit report
                has_final_report = any(keyword in conversation_text.lower() for keyword in [
                    "最终审核报告", "审核统计", "最终结论", "改进建议", "总规则数"
                ])

                # Check if we have validated multiple rules
                rule_validations = sum(1 for i in range(1, len(reimbursement_rules) + 1)
                                     if f"规则{i}" in conversation_text)

                # If we don't have a final report and haven't validated enough rules, continue
                if not has_final_report and rule_validations < len(reimbursement_rules):
                    total_rules = len(reimbursement_rules)

                    # Determine what to prompt based on current state
                    if not rules_validation_started:
                        # First time prompting for rule validation
                        rules_validation_started = True
                        follow_up_prompt = f"""
                        **请开始逐条验证规则！**

                        发票信息已识别完成。现在需要逐条验证所有{total_rules}条财务报销规则。

                        **逐条验证要求**：
                        🔄 一次只验证一条规则，不要批量处理
                        🛠️ 只有当验证某条规则需要额外信息时，才调用工具
                        📝 每验证完一条规则，立即给出该规则的结果
                        ➡️ 然后继续验证下一条规则
                        🎯 所有规则验证完成后，再生成最终汇总报告

                        请现在开始验证第一条规则！
                        """
                    else:
                        # Continue with remaining rule validation
                        follow_up_prompt = f"""
                        **请继续验证剩余规则！**

                        您已经验证了一些规则，但还需要继续验证剩余的规则。
                        总共有{total_rules}条规则需要验证。

                        请继续逐条验证剩余的规则，每条规则验证完成后立即给出结果。
                        最后生成完整的审核报告汇总。
                        """

                    claude_messages.append({
                        "role": "user",
                        "content": follow_up_prompt
                    })
                    continue

            # Really no more tool calls and validation seems complete, break the loop
            break

async def _process_query_with_tools(question, history, session_id: str, file_upload, client, model, reimbursement_rules, mcp_client):
    """Process query with multi-tool calling support"""
    # Create context with rules
    rules_context = json.dumps(reimbursement_rules, ensure_ascii=False, indent=2)

    # Build conversation messages from history
    claude_messages = []
    for msg in history:
        if isinstance(msg, dict):
            role, content = msg.get("role"), msg.get("content")
            if role in ["user", "assistant", "system"] and content:
                claude_messages.append({"role": role, "content": content})

    # Prepare the main prompt with detailed audit instructions
    base_prompt = f"""
    你是一个财务报销专家，请基于以下财务报销规则对用户的问题进行详细分析和审核。

    财务报销规则：
    {rules_context}

    用户问题：{question}

    **重要：如果用户上传了单据或要求审核单据，请按以下步骤进行完整的审核流程：**

    1. **单据识别阶段**：
       - 首先使用 recognize_document 工具识别单据信息
       - 提取单据的关键信息：金额、日期、城市、类型等
       - 该工具支持多种单据类型：发票、收据、合同、订单、报销单等
       - 支持灵活的 JSON 格式输出，自适应识别单据字段

    2. **规则验证阶段**：
       - 针对每条相关的财务报销规则，逐一进行验证
       - 根据需要调用相应的工具：
         * 如果涉及时间限制，使用 get_current_time 工具获取当前时间进行对比
         * 如果涉及城市分级标准，使用 query_city_tier 工具查询城市分级
         * 如果需要批量查询城市，使用 query_multiple_cities 工具
         * 如果需要获取某个分级的所有城市，使用 get_cities_by_tier 工具

    3. **综合分析阶段**：
       - 汇总所有验证结果
       - 给出明确的审核结论：通过/不通过
       - 列出不符合规则的具体项目
       - 提供改进建议

    **注意**：
    - 必须逐条验证所有相关规则，不能跳过任何步骤
    - 每个验证步骤都要使用相应的工具获取准确信息
    - 最终给出详细的审核报告

    可用的MCP工具：
    - recognize_document: 识别单据信息（支持发票、收据、合同、订单等多种单据类型）
    - get_current_time: 获取当前时间
    - query_city_tier: 查询单个城市分级
    - query_multiple_cities: 批量查询多个城市分级
    - get_cities_by_tier: 获取指定分级的所有城市

    会话ID: {session_id}
    """

    # Handle file upload and create the main message
    main_message = await _prepare_main_message(question, file_upload, session_id, rules_context, base_prompt)
    claude_messages.append(main_message)

    # Get MCP tools if available
    mcp_tools = []
    if mcp_client and mcp_client.connected_servers:
        mcp_tools = mcp_client.get_all_tools()

    # Process with multi-tool calling
    result_messages = []
    max_iterations = 8  # Increase iterations for multi-step audit process
    iteration = 0
    invoice_recognized = False  # Track if invoice has been recognized

    while iteration < max_iterations:
        iteration += 1

        # Prepare additional context for continuing audit process
        additional_context = ""
        if invoice_recognized and iteration > 1:
            additional_context = f"""

            **继续审核流程**：
            发票信息已识别完成。现在请继续进行第{iteration}步：逐条验证财务报销规则。

            请检查以下方面（根据需要调用相应工具）：
            1. 时间限制验证 - 使用 get_current_time 工具检查报销是否超时
            2. 城市分级验证 - 使用 query_city_tier 工具检查城市分级标准
            3. 金额标准验证 - 根据城市分级和规则检查金额是否符合标准
            4. 其他规则验证 - 逐一检查所有相关规则

            **重要**：必须调用相应的工具来获取准确信息进行验证，不能仅凭推测。
            """

        # Make the API call with or without tools
        current_messages = claude_messages.copy()
        if additional_context and len(current_messages) > 0:
            # Add continuation prompt to the last user message
            last_message = current_messages[-1]
            if last_message["role"] == "user":
                if isinstance(last_message["content"], str):
                    last_message["content"] += additional_context
                elif isinstance(last_message["content"], list):
                    last_message["content"].append({
                        "type": "text",
                        "text": additional_context
                    })

        response = client.chat.completions.create(
            model=model,
            messages=current_messages,
            temperature=0.3,
            tools=mcp_tools if mcp_tools else None,
            tool_choice="auto" if mcp_tools else None,
            extra_body={
                "enable_thinking": False
            }
        )

        assistant_msg = response.choices[0].message

        # Add assistant response to messages
        if assistant_msg.content:
            result_messages.append({
                "role": "assistant",
                "content": assistant_msg.content
            })

        # Check if there are tool calls
        if assistant_msg.tool_calls and mcp_client:
            # Process all tool calls in this iteration
            tool_results = []

            for call in assistant_msg.tool_calls:
                tool_name = call.function.name
                tool_args = json.loads(call.function.arguments)

                # Track if invoice recognition tool was called
                if tool_name == "recognize_single_invoice":
                    invoice_recognized = True

                # Add tool call message to result
                result_messages.append({
                    "role": "assistant",
                    "content": f"使用工具: {tool_name}",
                    "metadata": {
                        "title": f"Tool: {tool_name}",
                        "log": f"参数: {json.dumps(tool_args, ensure_ascii=False)}",
                        "status": "pending",
                        "id": f"tool_call_{tool_name}_{iteration}"
                    }
                })

                # Execute the tool
                try:
                    tool_result = await _execute_tool(tool_name, tool_args, session_id, mcp_client)
                    tool_results.append((call.id, tool_name, tool_result))

                    # Add tool result to result messages
                    result_messages.append({
                        "role": "assistant",
                        "content": f"工具结果: {tool_name}",
                        "metadata": {
                            "title": f"Result: {tool_name}",
                            "status": "done",
                            "id": f"result_{tool_name}_{iteration}"
                        }
                    })

                    # Format and add the actual result
                    if isinstance(tool_result, dict):
                        formatted_result = json.dumps(tool_result, ensure_ascii=False, indent=2)
                    elif isinstance(tool_result, list):
                        formatted_result = "\n".join(map(str, tool_result))
                    else:
                        formatted_result = str(tool_result)

                    result_messages.append({
                        "role": "assistant",
                        "content": f"```\n{formatted_result}\n```",
                        "metadata": {"title": "Raw Output"}
                    })

                except Exception as e:
                    error_msg = f"❌ 执行工具 '{tool_name}' 时出错: {str(e)}"
                    result_messages.append({
                        "role": "assistant",
                        "content": error_msg
                    })
                    tool_results.append((call.id, tool_name, error_msg))

            # Add tool calls and results to conversation history
            claude_messages.append({
                "role": "assistant",
                "content": assistant_msg.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments}
                    } for call in assistant_msg.tool_calls
                ]
            })

            # Add tool results to conversation
            for call_id, tool_name, tool_result in tool_results:
                claude_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": str(tool_result)
                })

            # Continue the loop to allow for more tool calls
            continue
        else:
            # No more tool calls
            # If invoice was recognized but we haven't done rule validation, prompt for it
            if invoice_recognized and iteration <= 3:
                # Add a follow-up prompt to encourage rule validation
                follow_up_prompt = """
                请继续完成审核流程。现在需要逐条验证财务报销规则：

                1. 检查报销时间是否超时（使用 get_current_time 工具）
                2. 检查城市分级标准（使用 query_city_tier 工具）
                3. 验证金额是否符合标准
                4. 检查其他相关规则

                请调用相应的工具来获取准确信息进行验证。
                """

                claude_messages.append({
                    "role": "user",
                    "content": follow_up_prompt
                })
                continue
            else:
                # Really no more tool calls, break the loop
                break

    return result_messages


def _should_continue_audit(claude_messages, reimbursement_rules, iteration):
    """
    智能判断是否应该继续审核流程
    基于对话内容、规则验证进度和迭代次数综合判断
    """
    # 安全上限：防止无限循环
    if iteration > 8:  # 降低上限，更早停止
        return False

    # 获取完整的对话内容（不只是最近5条）
    full_conversation = " ".join([
        msg.get("content", "") for msg in claude_messages
        if isinstance(msg.get("content"), str)
    ])

    # 检查是否有最终审核报告的标志
    final_report_indicators = [
        "最终审核报告", "审核统计", "最终结论", "改进建议",
        "总规则数", "符合规则", "不符合规则", "审核完成",
        "📋 发票审核报告", "📊 规则验证结果", "📈 审核统计"
    ]
    has_final_report = any(indicator in full_conversation for indicator in final_report_indicators)

    # 检查规则验证进度（在完整对话中查找）
    total_rules = len(reimbursement_rules)
    completed_rules = 0

    # 更精确的规则完成检测
    for i in range(1, total_rules + 1):
        rule_pattern = f"规则{i}"
        if rule_pattern in full_conversation:
            # 检查该规则是否有明确的验证结果
            rule_section = full_conversation[full_conversation.find(rule_pattern):]
            if any(result in rule_section[:200] for result in ["✅ 符合", "❌ 不符合", "⚠️ 需注意"]):
                completed_rules += 1

    # 检查是否有重复审核的迹象
    rule_mentions = sum(full_conversation.count(f"规则{i}") for i in range(1, total_rules + 1))
    if rule_mentions > total_rules * 2:  # 如果规则被提及次数过多，可能在重复
        return False

    # 检查对话长度
    if len(full_conversation) > 3000:  # 对话过长，停止
        return False

    print(f"🔍 审核进度检查: 完成规则 {completed_rules}/{total_rules}, 有最终报告: {has_final_report}, 迭代: {iteration}")

    # 更严格的判断逻辑：
    # 1. 如果有最终报告，立即停止
    if has_final_report:
        return False

    # 2. 如果所有规则都已验证完成，停止
    if completed_rules >= total_rules:
        return False

    # 3. 如果迭代次数过多，停止
    if iteration > 5:
        return False

    # 4. 如果是早期阶段且还有规则未完成，继续
    if iteration <= 3 and completed_rules < total_rules:
        return True

    # 5. 如果有部分进度但未完成，谨慎继续
    if completed_rules > 0 and completed_rules < total_rules and iteration <= 4:
        return True

    # 6. 其他情况，停止审核
    return False


async def _prepare_main_message(question, file_upload, session_id: str, rules_context: str, base_prompt: str):
    """Prepare the main message with file upload handling"""
    if file_upload:
        logger.info(f">>> file_upload: {file_upload}")

        # Run cleanup before processing new file
        cleanup_upload_files()

        message_content = []

        try:
            # Read file content directly and convert to base64
            with open(file_upload.name, "rb") as file_content:
                file_data = file_content.read()
                file_base64 = base64.b64encode(file_data).decode('utf-8')

            # Check file type and process accordingly
            file_ext = os.path.splitext(file_upload.name)[1].lower()

            if file_ext == '.pdf':
                # Process PDF file
                pdf_text = ""
                try:
                    # Extract text from PDF using PyMuPDF
                    pdf_document = fitz.open(file_upload.name)
                    for page_num in range(len(pdf_document)):
                        page = pdf_document.load_page(page_num)
                        pdf_text += page.get_text() + "\n"
                    pdf_document.close()

                    # Add text content with PDF processing instructions
                    message_content.append({
                        "type": "text",
                        "text": f"{base_prompt}\n\n请注意：用户已上传了一个PDF文件，文件内容如下：\n\n{pdf_text}\n\n如果PDF中包含单据信息，请使用 recognize_document 工具来识别单据信息。该工具支持多种单据类型（发票、收据、合同、订单、报销单等），并能灵活识别其中的内容。请将PDF中的单据内容完整提取出来。\n\n请使用 recognize_document 工具，该工具接受以下参数：\n- image_data: base64编码的图片数据\n- user_text: 用户提供的补充文字信息（可选）\n\n已准备好base64编码的PDF数据，可以直接使用。"
                    })

                    # Store base64 data for tool usage
                    session_store[session_id]["file_base64"] = file_base64
                    session_store[session_id]["file_type"] = "pdf"

                except Exception as e:
                    logger.error(f"Error processing PDF: {e}")
                    message_content.append({
                        "type": "text",
                        "text": f"{base_prompt}\n\n请注意：用户上传了一个PDF文件，但在处理文件时出错：{str(e)}"
                    })
            else:
                # Process image file
                # Get MIME type for image
                mime_type = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.bmp': 'image/bmp',
                    '.webp': 'image/webp'
                }.get(file_ext, 'image/jpeg')

                # Create data URL
                data_url = f"data:{mime_type};base64,{file_base64}"

                # Add text content with image processing instructions
                message_content.append({
                    "type": "text",
                    "text": f"{base_prompt}\n\n请注意：用户已上传了一张图片，请使用 recognize_document 工具来识别图片中的单据信息。该工具支持多种单据类型（发票、收据、合同、订单、报销单等），并能灵活识别其中的内容。请将图片中的单据内容完整提取出来。\n\n请使用 recognize_document 工具，该工具接受以下参数：\n- image_data: base64编码的图片数据\n- user_text: 用户提供的补充文字信息（可选）\n\n已准备好base64编码的图片数据，可以直接使用。"
                })

                # Add image content
                message_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": data_url
                    }
                })

                # Store base64 data for tool usage
                session_store[session_id]["file_base64"] = file_base64
                session_store[session_id]["file_type"] = "image"

            return {"role": "user", "content": message_content}

        except Exception as e:
            logger.error(f"Error processing file: {e}")
            # Fall back to text-only if file processing fails
            return {"role": "user", "content": base_prompt}
    else:
        # No file upload, use standard text prompt
        return {"role": "user", "content": base_prompt}


async def _execute_tool(tool_name: str, tool_args: dict, session_id: str, mcp_client):
    """Execute a single tool and return the result"""
    try:
        # Special handling for document recognition tool
        if tool_name == "recognize_document":
            logger.info(f"处理单据识别工具参数: {tool_args}")

            # Get OpenAI configuration from session
            session_data = session_store.get(session_id, {})
            if session_data:
                # Try to get API key and base URL from environment variables
                api_key = os.environ.get(f"OPENAI_API_KEY_{session_id}")
                base_url = os.environ.get(f"OPENAI_BASE_URL_{session_id}")
                model = os.environ.get(f"OPENAI_MODEL_{session_id}")

                if api_key and base_url and model:
                    tool_args["api_key"] = api_key
                    tool_args["base_url"] = base_url
                    tool_args["model"] = model
                    logger.info("已添加OpenAI配置参数到工具调用")

            # Use base64 image data from session storage instead of file URLs
            if "file_base64" in session_data:
                file_base64 = session_data["file_base64"]
                file_type = session_data.get("file_type", "image")
                
                # For PDF files, we need to handle them differently
                if file_type == "pdf":
                    # For PDF, we need to convert to image first or handle differently
                    # For now, we'll skip PDF processing in OCR tools
                    logger.info("PDF文件暂不支持OCR识别")
                else:
                    # Use base64 image data directly
                    tool_args["image_data"] = file_base64
                    logger.info("已使用base64图片数据")
                    
                    # Remove image_url if it exists to avoid conflicts
                    if "image_url" in tool_args:
                        del tool_args["image_url"]
                        logger.info("已移除image_url参数，使用image_data")

            # Ensure only document recognition tool supported parameters are passed
            valid_args = {}
            if "image_data" in tool_args:
                valid_args["image_data"] = tool_args["image_data"]
            if "image_url" in tool_args:
                valid_args["image_url"] = tool_args["image_url"]
            # Include user_text if provided
            if "user_text" in tool_args:
                valid_args["user_text"] = tool_args["user_text"]
            # Include OpenAI configuration if available
            if "api_key" in tool_args:
                valid_args["api_key"] = tool_args["api_key"]
            if "base_url" in tool_args:
                valid_args["base_url"] = tool_args["base_url"]
            if "model" in tool_args:
                valid_args["model"] = tool_args["model"]

            tool_args = valid_args
            logger.info(f"最终传递给单据识别工具的参数: {list(tool_args.keys())}")

        # Get the target server for the tool
        target_server = mcp_client.get_server_for_tool(tool_name)
        if target_server and target_server in mcp_client.sessions:
            tool_result = await mcp_client.sessions[target_server].call_tool(tool_name, tool_args)

            # Process tool result
            if hasattr(tool_result, 'content'):
                return tool_result.content
            elif isinstance(tool_result, dict):
                return tool_result
            else:
                return str(tool_result)
        else:
            return f"❌ 工具 '{tool_name}' 未找到对应的服务器连接"

    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return f"❌ 执行工具 '{tool_name}' 时出错: {str(e)}"

def clear_chat_history(history):
    """Clear chat history"""
    return []

def load_example_invoice():
    """Load example invoice from examples directory"""
    example_path = os.path.join(os.getcwd(), "examples", "invoice.jpg")
    if os.path.exists(example_path):
        return example_path
    else:
        logger.error(f"Example invoice not found at {example_path}")
        return None

def load_example_invoice_with_text():
    """Load example invoice and set question text"""
    example_path = os.path.join(os.getcwd(), "examples", "invoice.jpg")
    if os.path.exists(example_path):
        return example_path, "审核一下此张单据"
    else:
        logger.error(f"Example invoice not found at {example_path}")
        return None, "审核一下此张单据"

def connect_city_server_with_session(command, session_id: str):
    """Connect to city tier MCP server"""
    import subprocess
    import time
    global global_city_server_status
    
    if not global_mcp_client:
        global_city_server_status = "❌ MCP客户端未初始化"
        return global_city_server_status
    
    try:
        # 首先检查是否已经连接到服务器
        if "citytier_server" in global_mcp_client.connected_servers:
            global_city_server_status = "✅ 城市分级服务器已连接"
            return global_city_server_status
        
        # 如果未连接，尝试连接
        command_list = command.split()
        result = global_mcp_client.connect(command_list, "citytier_server")
        
        # 如果连接失败，尝试启动服务器
        if "❌" in result:
            logger.info("城市分级服务器连接失败，尝试启动服务器...")
            try:
                # 启动服务器
                server_process = subprocess.Popen(
                    command_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                logger.info(f"城市分级服务器已启动，PID: {server_process.pid}")
                time.sleep(3)  # 等待服务器启动
                
                # 再次尝试连接
                result = global_mcp_client.connect(command_list, "citytier_server")
            except Exception as start_e:
                logger.error(f"启动城市分级服务器失败: {start_e}")
                global_city_server_status = f"❌ 连接和启动城市分级服务器都失败: {str(e)}; 启动失败: {str(start_e)}"
                return global_city_server_status
        
        global_city_server_status = result
        return global_city_server_status
    except Exception as e:
        global_city_server_status = f"❌ 连接城市分级服务器失败: {str(e)}"
        return global_city_server_status

def connect_invoice_server_with_session(command, session_id: str):
    """Connect to document recognition MCP server"""
    import subprocess
    import time
    global global_invoice_server_status
    
    if not global_mcp_client:
        global_invoice_server_status = "❌ MCP客户端未初始化"
        return global_invoice_server_status
    
    try:
        # 首先检查是否已经连接到服务器
        if "document_server" in global_mcp_client.connected_servers:
            global_invoice_server_status = "✅ 单据识别服务器已连接"
            return global_invoice_server_status
        
        # 如果未连接，尝试连接
        command_list = command.split()
        result = global_mcp_client.connect(command_list, "document_server")
        
        # 如果连接失败，尝试启动服务器
        if "❌" in result:
            logger.info("单据识别服务器连接失败，尝试启动服务器...")
            try:
                # 启动服务器
                server_process = subprocess.Popen(
                    command_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                logger.info(f"单据识别服务器已启动，PID: {server_process.pid}")
                time.sleep(3)  # 等待服务器启动
                
                # 再次尝试连接
                result = global_mcp_client.connect(command_list, "document_server")
            except Exception as start_e:
                logger.error(f"启动单据识别服务器失败: {start_e}")
                global_invoice_server_status = f"❌ 连接和启动单据识别服务器都失败: {str(e)}; 启动失败: {str(start_e)}"
                return global_invoice_server_status
        
        global_invoice_server_status = result
        return global_invoice_server_status
    except Exception as e:
        global_invoice_server_status = f"❌ 连接单据识别服务器失败: {str(e)}"
        return global_invoice_server_status

def connect_datetime_server_with_session(command, session_id: str):
    """Connect to datetime MCP server"""
    import subprocess
    import time
    global global_datetime_server_status
    
    if not global_mcp_client:
        global_datetime_server_status = "❌ MCP客户端未初始化"
        return global_datetime_server_status
    
    try:
        # 首先检查是否已经连接到服务器
        if "datetime_server" in global_mcp_client.connected_servers:
            global_datetime_server_status = "✅ 日期时间服务器已连接"
            return global_datetime_server_status
        
        # 如果未连接，尝试连接
        command_list = command.split()
        result = global_mcp_client.connect(command_list, "datetime_server")
        
        # 如果连接失败，尝试启动服务器
        if "❌" in result:
            logger.info("日期时间服务器连接失败，尝试启动服务器...")
            try:
                # 启动服务器
                server_process = subprocess.Popen(
                    command_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                logger.info(f"日期时间服务器已启动，PID: {server_process.pid}")
                time.sleep(3)  # 等待服务器启动
                
                # 再次尝试连接
                result = global_mcp_client.connect(command_list, "datetime_server")
            except Exception as start_e:
                logger.error(f"启动日期时间服务器失败: {start_e}")
                global_datetime_server_status = f"❌ 连接和启动日期时间服务器都失败: {str(e)}; 启动失败: {str(start_e)}"
                return global_datetime_server_status
        
        global_datetime_server_status = result
        return global_datetime_server_status
    except Exception as e:
        global_datetime_server_status = f"❌ 连接日期时间服务器失败: {str(e)}"
        return global_datetime_server_status

class AuditAgentApp:
    def __init__(self):
        self.setup_ui()
    
    def setup_ui(self):
        with gr.Blocks(title="财务报销智能体") as self.app:
            # Initialize session state
            session_id = gr.State(init_session)
            
            gr.Markdown("# 财务报销智能体")
            
            with gr.Tabs():
                # Step 1: Settings Tab
                with gr.TabItem("Step 1: 设置"):
                    self.setup_settings_tab(session_id)
                
                # Step 2: Knowledge Base Tab
                with gr.TabItem("Step 2: 知识库"):
                    self.setup_knowledge_base_tab(session_id)
                
                # Step 3: MCP Server Management Tab
                with gr.TabItem("Step 3: MCP服务器管理"):
                    self.setup_mcp_server_tab(session_id)
                
                # Step 4: Agent Tab
                with gr.TabItem("Step 4: 智能体"):
                    self.setup_agent_tab(session_id)
    
    def setup_settings_tab(self, session_id):
        # Load configuration from .env file
        env_config = load_config_from_env()
        
        with gr.Row():
            with gr.Column():
                gr.Markdown("## OpenAI API 设置")
                
                api_key_input = gr.Textbox(
                    label="API Key",
                    placeholder="请输入您的 OpenAI API Key",
                    type="password",
                    value=env_config["api_key_input"]
                )
                
                base_url_input = gr.Textbox(
                    label="Base URL",
                    placeholder="请输入 OpenAI API 的 Base URL (例如: https://api.openai.com/v1)",
                    value=env_config["base_url_input"]
                )
                
                model_input = gr.Textbox(
                    label="Model",
                    placeholder="请输入模型名称 (例如: gpt-3.5-turbo)",
                    value=env_config["model_input"]
                )
                
                test_connection_btn = gr.Button("测试连接", variant="primary")
                
                connection_status = gr.Textbox(
                    label="连接状态",
                    interactive=False
                )
        
        # Set up event handler for connection test
        test_connection_btn.click(
            fn=test_and_store_client,
            inputs=[api_key_input, base_url_input, model_input, session_id],
            outputs=connection_status
        )
        
        # DingTalk Integration Section
        if DINGTALK_AVAILABLE:
            gr.Markdown("## 钉钉机器人集成")
            gr.Markdown("配置钉钉机器人消息推送功能")
            
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### 🔧 钉钉机器人配置")
                    dingtalk_app_key = gr.Textbox(
                        label="钉钉 App Key",
                        placeholder="请输入您的钉钉 App Key",
                        type="password",
                        value=env_config["dingtalk_app_key"]
                    )
                    
                    dingtalk_app_secret = gr.Textbox(
                        label="钉钉 App Secret",
                        placeholder="请输入您的钉钉 App Secret",
                        type="password",
                        value=env_config["dingtalk_app_secret"]
                    )
                    
                    gr.Markdown("### 🤖 AI集成说明")
                    gr.Markdown("✅ 机器人将自动使用 **Step 1** 中配置的 OpenAI API 设置进行智能分析")
                    gr.Markdown("📋 支持功能：")
                    gr.Markdown("• 📝 文本消息的AI分析")
                    gr.Markdown("• 🖼️ 图片消息的智能识别（发票、文档等）")
                    
                    # 隐藏的会话ID输入，用于传递当前会话
                    current_session = list(session_store.keys())[0] if session_store else ""
                    session_id_input = gr.Textbox(
                        value=current_session,
                        visible=False
                    )
                    
                    with gr.Row():
                        dingtalk_start_btn = gr.Button("🚀 启动机器人", variant="primary")
                        dingtalk_stop_btn = gr.Button("⏹️ 停止机器人", variant="secondary")
                    
                    dingtalk_status = gr.Textbox(
                        label="机器人状态",
                        value=dingtalk_bot_status,
                        interactive=False,
                        lines=3
                    )
            
            # Set up event handlers for DingTalk bot with AI integration
            dingtalk_start_btn.click(
                fn=start_dingtalk_bot_with_ai,
                inputs=[dingtalk_app_key, dingtalk_app_secret, session_id_input],
                outputs=dingtalk_status
            )
            
            dingtalk_stop_btn.click(
                fn=stop_dingtalk_bot,
                outputs=dingtalk_status
            )
        else:
            gr.Markdown("## 钉钉机器人集成")
            gr.Markdown("⚠️ dingtalk-stream 库未安装，钉钉机器人功能不可用。请先安装依赖：`pip install dingtalk-stream`")
        
        gr.HTML("""
        <div style="
            background-color: white;
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 20px;
            margin: 10px 0;
        ">
            <h2>📋 项目使用说明</h2>
            <h3>🎯 项目概述</h3>
            <p>财务报销智能体是一个基于大语言模型的智能助手，旨在帮助企业员工快速了解财务报销规则、审核报销材料，提高报销效率。</p>
            
            <h3>🔧 系统架构</h3>
            <ul>
                <li><strong>大语言模型</strong>: 使用 Step 1 中配置的模型进行智能问答和规则提取</li>
                <li><strong>MCP 服务器</strong>: 提供多种专业功能服务
                    <ul>
                        <li>🏙️ 城市分级查询服务器：查询城市分级信息</li>
                        <li>📄 发票识别LLM服务器：识别发票信息（<strong>使用 Step 1 中配置的大语言模型</strong>）</li>
                        <li>📅 日期时间服务器：提供日期时间相关功能</li>
                    </ul>
                </li>
            </ul>
            
            <h3>📝 使用步骤</h3>
            <ol>
                <li><strong>Step 1: 设置</strong> - 配置大语言模型 API</li>
                <li><strong>Step 2: 知识库</strong> - 上传财务报销规则文档</li>
                <li><strong>Step 3: MCP服务器管理</strong> - 连接各种功能服务器</li>
                <li><strong>Step 4: 智能问答</strong> - 基于规则进行智能问答</li>
            </ol>
            
            <h3>⚠️ 重要说明</h3>
            <ul>
                <li><strong>发票识别服务器</strong>使用的是 Step 1 中配置的大语言模型，确保模型配置正确</li>
                <li><strong>实际办公环境建议</strong>：出于数据安全和隐私保护考虑，建议在实际办公环境中使用本地部署的大语言模型</li>
                <li><strong>本地 LLM 优势</strong>：
                    <ul>
                        <li>数据不出本地，保障敏感财务信息安全</li>
                        <li>响应速度更快，不受网络限制</li>
                        <li>可根据企业需求进行定制化训练</li>
                        <li>长期使用成本更低</li>
                    </ul>
                </li>
            </ul>
            
            <h3>🔐 安全建议</h3>
            <ul>
                <li>涉及敏感财务数据时，优先使用本地部署的 LLM</li>
                <li>定期更新财务报销规则，确保信息准确性</li>
                <li>妥善保管 API 密钥，避免泄露</li>
            </ul>
        </div>
        """)
        
        # Set up event handler for connection test
        test_connection_btn.click(
            fn=test_and_store_client,
            inputs=[api_key_input, base_url_input, model_input, session_id],
            outputs=connection_status
        )
    
    def setup_knowledge_base_tab(self, session_id):
        with gr.Row():
            with gr.Column():
                gr.Markdown("## 知识库 - 财务报销规则提取")
                gr.Markdown("### 🤖 使用LLM大模型抽取报销规则")
                gr.Markdown("本步骤使用您在Step 1中配置的大语言模型（LLM）来智能抽取财务报销规则。系统会分析您上传的文档内容，自动识别并提取其中的报销规则，并转换为结构化的JSON格式。")
                gr.Markdown("支持上传的文档类型：.txt（文本文档）、.pdf（PDF文档）、.docx（Word文档）、.doc（旧版Word文档，建议转换为.docx格式）")
                
                file_upload = gr.File(
                    label="上传文档",
                    file_types=[".txt", ".pdf", ".docx", ".doc"],
                    file_count="multiple"
                )
                
                # 将处理文档按钮放在上传控件下面
                process_docs_btn = gr.Button("处理文档", variant="primary")
                
                # 添加示例文本显示区域，自动加载
                example_content = load_example_text()
                example_text = gr.Textbox(
                    label="示例文本内容（内置财务报销规则）",
                    lines=10,
                    value=example_content,
                    interactive=False
                )
                
                # 在示例文本下方添加上传示例文档按钮
                upload_example_btn = gr.Button("上传示例文档", variant="secondary")
                
                rules_output = gr.JSON(
                    label="提取的财务报销规则"
                )
                
                processing_status = gr.Textbox(
                    label="处理状态",
                    interactive=False
                )
        
        # Set up event handler for document processing
        process_docs_btn.click(
            fn=extract_reimbursement_rules_with_session,
            inputs=[file_upload, session_id],
            outputs=[processing_status, rules_output]
        )
        
        # Set up event handler for uploading example document
        def process_example_document(session_id):
            """Process example document directly"""
            try:
                example_path = os.path.join("examples", "invoice_rules.txt")
                if os.path.exists(example_path):
                    # Read the example file content
                    with open(example_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Create a mock file object for processing
                    class MockFile:
                        def __init__(self, name, content):
                            self.name = name
                            self.content = content
                        
                        def read(self):
                            return self.content.encode('utf-8')
                    
                    mock_file = MockFile("invoice_rules.txt", content)
                    
                    # Process the example file directly
                    session_data = session_store.get(session_id, {})
                    client = session_data.get("client")
                    model = session_data.get("model")
                    
                    if not client or not model:
                        return "❌ 请先在 Step 1 中配置并测试 OpenAI API 连接", []
                    
                    # Process the file content
                    document_text = content
                    
                    # Create prompt for rule extraction
                    prompt = f"""
                    请从以下文档内容中提取所有关于财务报销的规则，并以JSON格式返回。
                    返回格式应该是一个规则列表，每个规则包含以下字段：
                    - rule_name: 规则名称
                    - rule_description: 规则描述
                    - rule_category: 规则类别（如：差旅费、办公用品、业务招待等）
                    
                    文档内容：
                    {document_text}
                    """
                    
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                        extra_body={
                            "enable_thinking": False
                        }
                    )
                    
                    # Parse the response to extract rules
                    rules_text = response.choices[0].message.content
                    
                    # Try to parse as JSON, if fails, return as text
                    try:
                        # Extract JSON from the response if it's wrapped in markdown code blocks
                        if "```json" in rules_text:
                            json_start = rules_text.find("```json") + 7
                            json_end = rules_text.find("```", json_start)
                            rules_json = rules_text[json_start:json_end].strip()
                            rules = json.loads(rules_json)
                        else:
                            rules = json.loads(rules_text)
                        
                        # Store rules in session
                        session_store[session_id]["reimbursement_rules"] = rules
                        return "✅ 示例文档处理成功！", rules
                    except json.JSONDecodeError:
                        # If JSON parsing fails, return the raw text
                        return "⚠️ 规则已提取，但JSON解析失败，请查看原始文本", rules_text
                    
                else:
                    return "❌ 示例文件不存在：examples/invoice_rules.txt", []
                    
            except Exception as e:
                return f"❌ 处理示例文档失败: {str(e)}", []
        
        upload_example_btn.click(
            fn=process_example_document,
            inputs=[session_id],
            outputs=[processing_status, rules_output]
        )
    
    def setup_mcp_server_tab(self, session_id):
        with gr.Row():
            with gr.Column():
                gr.Markdown("## MCP服务器管理")
                gr.Markdown("在此步骤中，您可以连接和管理MCP（Model Context Protocol）服务器，包括城市分级查询、发票识别LLM服务器和日期时间服务器。")
                
                # City Tier Server Configuration
                gr.Markdown("### 🏙️ 城市分级查询服务器")
                gr.Markdown("""
                **功能说明：**
                - 🏙️ **城市分级查询**: 根据城市名称查询城市分级信息
                - 📊 **分级覆盖**: 覆盖一线、新一线、二线、三线、四线、五线城市
                - 🔍 **批量查询**: 支持批量查询多个城市的分级信息
                - 📋 **分级列表**: 获取指定分级的所有城市列表
                
                **可用工具：**
                - query_city_tier: 查询单个城市分级
                - query_multiple_cities: 批量查询多个城市分级
                - get_tier_cities: 获取指定分级的城市列表
                """)
                
                city_server_command = gr.Textbox(
                    label="服务器命令",
                    placeholder="python mcp_citytier_stdio.py",
                    value="python mcp_citytier_stdio.py",
                    interactive=False
                )
                
                city_connect_btn = gr.Button("连接服务器", variant="primary")
                
                city_status = gr.Textbox(
                    label="连接状态",
                    value=global_city_server_status,
                    interactive=False
                )
                # Invoice Server Configuration
                gr.Markdown("### 📄 单据识别LLM服务器")
                gr.Markdown("""
                **功能说明：**
                - 📋 **多类型单据支持**: 支持发票、收据、合同、订单、报销单等多种单据类型
                - 🖼️ **多格式处理**: 处理图片文件（JPG、PNG等）和PDF文档
                - 🔍 **先进OCR技术**: 使用PaddleOCR进行准确的文本提取
                - 🤖 **AI驱动分析**: 利用大模型进行智能字段提取，自适应识别单据字段
                - 🔒 **隐私保护**: 所有处理都在本地进行，确保敏感单据数据安全
                
                **技术架构：**
                1. **文档处理**:
                   - 🖼️ 图片：使用PaddleOCR进行OCR处理
                   - 📑 PDF：使用PyMuPDF直接提取文本
                2. **智能信息提取**:
                   - 🤖 使用大模型进行智能字段解析，支持多种单据类型
                   - ✅ 灵活的JSON格式输出，不严格限制字段结构
                   - 🔄 自适应识别不同单据的关键信息
                """)
                    
                invoice_server_command = gr.Textbox(
                    label="服务器命令",
                    placeholder="python mcp_document_stdio.py",
                    value="python mcp_document_stdio.py",
                    interactive=False
                )
                    
                invoice_connect_btn = gr.Button("连接服务器", variant="primary")
                
                invoice_status = gr.Textbox(
                    label="连接状态",
                    value=global_invoice_server_status,
                    interactive=False
                )
                
                # Datetime Server Configuration
                gr.Markdown("### 📅 日期时间服务器")
                gr.Markdown("""
                **功能说明：**
                - 📅 **日期查询**: 获取当前日期、时间、日期时间
                - 🌍 **时区支持**: 支持多个时区的日期时间查询
                - 🔄 **日期计算**: 支持日期差值计算和日期加减操作
                - 📝 **格式化**: 支持自定义日期时间格式化
                
                **可用工具：**
                - get_current_date: 获取当前日期
                - get_current_time: 获取当前时间
                - get_current_datetime: 获取当前日期时间
                - get_datetime_by_timezone: 获取指定时区的日期时间
                - format_datetime: 格式化日期时间
                - calculate_date_difference: 计算日期差值
                - add_days_to_date: 日期加减天数
                - get_timezones: 获取常用时区列表
                """)
                
                datetime_server_command = gr.Textbox(
                    label="服务器命令",
                    placeholder="python mcp_datetime_stdio.py",
                    value="python mcp_datetime_stdio.py",
                    interactive=False
                )
                
                datetime_connect_btn = gr.Button("连接服务器", variant="primary")
                
                datetime_status = gr.Textbox(
                    label="连接状态",
                    value=global_datetime_server_status,
                    interactive=False
                )
                
        # Set up event handlers for MCP server management
        city_connect_btn.click(
            fn=connect_city_server_with_session,
            inputs=[city_server_command, session_id],
            outputs=city_status
        )
        
        invoice_connect_btn.click(
            fn=connect_invoice_server_with_session,
            inputs=[invoice_server_command, session_id],
            outputs=invoice_status
        )
        
        datetime_connect_btn.click(
            fn=connect_datetime_server_with_session,
            inputs=[datetime_server_command, session_id],
            outputs=datetime_status
        )
    
    def setup_agent_tab(self, session_id):
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("## 对话记录")
                
                chatbot = gr.Chatbot(
                    label="对话记录",
                    height=800,
                    type="messages"
                )
            
            with gr.Column(scale=1):
                gr.Markdown("## 智能问答")
                
                question_input = gr.Textbox(
                    label="请输入您的问题",
                    placeholder="例如: 差旅费的报销标准是什么？"
                )
                
                file_upload = gr.File(
                    label="📄 上传文件（可选）",
                    file_types=["image", ".pdf"],
                    type="filepath"
                )
                
                with gr.Row():
                    example_btn = gr.Button("使用示例发票", variant="secondary")
                    ask_btn = gr.Button("提问", variant="primary")
                
                clear_chat_btn = gr.Button("清空对话")
                
                # Example image preview
                gr.Markdown("### 示例发票预览")
                example_image = gr.Image(
                    label="示例发票",
                    value=os.path.join(os.getcwd(), "examples", "invoice.jpg"),
                    interactive=False,
                    height=200
                )
                gr.Markdown("*免责声明：此示例发票图片仅用于演示目的，图片来源于网络。*")
                gr.Markdown("*使用说明：由于线上部署的限制，目前仅支持图片格式。*")
        
        # Set up event handlers for chat functionality with streaming
        ask_btn.click(
            fn=answer_question_with_session,
            inputs=[question_input, chatbot, session_id, file_upload],
            outputs=[question_input, chatbot, file_upload],  # Add file_upload to outputs to clear it
            show_progress="full"  # Show progress for streaming
        )
        
        # Set up event handler for example button
        example_btn.click(
            fn=load_example_invoice_with_text,
            outputs=[file_upload, question_input]
        )
        
        clear_chat_btn.click(
            fn=clear_chat_history,
            inputs=chatbot,
            outputs=chatbot
        )
    
    def launch(self):
        """Launch the Gradio app"""
        # Launch the app
        self.app.launch(debug=True)

if __name__ == "__main__":
    # Initialize session storage
    logger.info("应用启动完成，已禁用文件服务器")

    # Connect to the MCP servers using the global client
    logger.info("正在连接到MCP服务器...")
    
    if global_mcp_client:
        # Connect to city tier server
        try:
            city_result = global_mcp_client.connect(["python", "mcp_citytier_stdio.py"], "citytier_server")
            global_city_server_status = city_result
            logger.info(f"城市分级服务器连接结果: {city_result}")
        except Exception as e:
            global_city_server_status = f"❌ 连接城市分级服务器失败: {str(e)}"
            logger.error(f"连接城市分级服务器失败: {e}")
        
        # Connect to invoice server
        try:
            invoice_result = global_mcp_client.connect(["python", "mcp_document_stdio.py"], "document_server")
            global_invoice_server_status = invoice_result
            logger.info(f"单据识别服务器连接结果: {invoice_result}")
        except Exception as e:
            global_invoice_server_status = f"❌ 连接单据识别服务器失败: {str(e)}"
            logger.error(f"连接单据识别服务器失败: {e}")
        
        # Connect to datetime server
        try:
            datetime_result = global_mcp_client.connect(["python", "mcp_datetime_stdio.py"], "datetime_server")
            global_datetime_server_status = datetime_result
            logger.info(f"日期时间服务器连接结果: {datetime_result}")
        except Exception as e:
            global_datetime_server_status = f"❌ 连接日期时间服务器失败: {str(e)}"
            logger.error(f"连接日期时间服务器失败: {e}")
        
        logger.info(f"已连接的服务器: {global_mcp_client.connected_servers}")
    else:
        logger.error("无法初始化MCP客户端")
        global_city_server_status = "❌ 无法初始化MCP客户端"
        global_invoice_server_status = "❌ 无法初始化MCP客户端"
        global_datetime_server_status = "❌ 无法初始化MCP客户端"
    
    app = AuditAgentApp()
    app.launch()