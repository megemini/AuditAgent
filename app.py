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
from contextlib import AsyncExitStack

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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('audit_agent.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

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

def start_file_server(port=8889):
    """启动一个简单的HTTP文件服务器来提供上传文件的访问"""
    import threading
    import http.server
    import socketserver
    
    class FileHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=os.path.join(os.getcwd(), "upload_files"), **kwargs)
        
        def end_headers(self):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', '*')
            super().end_headers()
    
    def run_server():
        try:
            with socketserver.TCPServer(("", port), FileHandler) as httpd:
                logger.info(f"文件服务器启动在端口 {port}")
                httpd.serve_forever()
        except Exception as e:
            logger.error(f"文件服务器启动失败: {e}")
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    return f"http://localhost:{port}"


class FastMCPStdioClientWrapper:
    def __init__(self):
        self.sessions: Dict[str, Client] = {}  # 存储多个服务器连接
        self.exit_stacks: Dict[str, AsyncExitStack] = {}  # 存储多个服务器的exit_stack
        self.tools: Dict[str, List[Dict[str, Any]]] = {}  # 存储每个服务器的工具
        self.connected_servers: List[str] = []  # 已连接的服务器列表

    # ------------------------- 连接 -------------------------
    def connect(self, server_command: List[str], server_name: str) -> str:
        """同步封装，方便 Gradio 直接调用"""
        return loop.run_until_complete(self._connect(server_command, server_name))

    async def _connect(self, server_command: List[str], server_name: str) -> str:
        # 关闭该服务器的旧连接
        if server_name in self.exit_stacks:
            await self.exit_stacks[server_name].aclose()
        
        self.exit_stacks[server_name] = AsyncExitStack()

        try:
            # 使用 PythonStdioTransport 创建 Client
            if len(server_command) >= 2 and server_command[0] == "python":
                script_path = server_command[1]
                transport = PythonStdioTransport(script_path)
            else:
                # 如果不是标准的 python 命令，使用通用的方式
                from fastmcp.client.transports import StdioTransport
                transport = StdioTransport(command=server_command[0], args=server_command[1:])

            # 创建 Client 并进入上下文
            client = Client(transport)
            self.sessions[server_name] = await self.exit_stacks[server_name].enter_async_context(client)

            # 拉取工具
            tools_resp = await self.sessions[server_name].list_tools()
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
            
            # 添加到已连接服务器列表
            if server_name not in self.connected_servers:
                self.connected_servers.append(server_name)
            
            return f"✅ Connected to {server_name}. Available tools: {', '.join(t['function']['name'] for t in self.tools[server_name])}"
            
        except Exception as e:
            # 清理失败的连接
            if server_name in self.exit_stacks:
                try:
                    await self.exit_stacks[server_name].aclose()
                except:
                    pass
                del self.exit_stacks[server_name]
            
            if server_name in self.sessions:
                del self.sessions[server_name]
            
            if server_name in self.tools:
                del self.tools[server_name]
            
            if server_name in self.connected_servers:
                self.connected_servers.remove(server_name)
            
            logger.error(f"Failed to connect to {server_name} with command {server_command}: {str(e)}")
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
    """Answer user's question based on reimbursement rules using session client"""
    if not question.strip():
        return "", history
    
    session_data = session_store.get(session_id, {})
    client = session_data.get("client")
    model = session_data.get("model")
    reimbursement_rules = session_data.get("reimbursement_rules", [])
    mcp_client = global_mcp_client
    
    if not reimbursement_rules:
        response = "❌ 请先在 Step 2 中上传文档并提取财务报销规则。"
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": response})
        return "", history
    
    if not client or not model:
        response = "❌ 请先在 Step 1 中配置 OpenAI API 设置。"
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": response})
        return "", history
    
    try:
        # Create context with rules
        rules_context = json.dumps(reimbursement_rules, ensure_ascii=False, indent=2)
        
        # Prepare messages for API call
        messages = []
        
        # Create a default prompt that will be used if file processing fails or no file is uploaded
        prompt = f"""
        你是一个财务报销专家，请基于以下财务报销规则回答用户的问题。
        
        财务报销规则：
        {rules_context}
        
        用户问题：{question}
        
        请提供准确、详细的回答，并引用相关的规则。
        
        会话ID: {session_id}
        """
        
        # Handle file upload if present
        if file_upload:
            # Run cleanup before processing new file
            cleanup_upload_files()
            
            message_content = []
            
            # Process the uploaded file
            try:
                # Generate unique filename
                unique_filename = f"{uuid.uuid4()}_{os.path.basename(file_upload.name)}"
                
                # Ensure upload_files directory exists
                upload_dir = os.path.join(os.getcwd(), "upload_files")
                os.makedirs(upload_dir, exist_ok=True)
                
                # Save file to upload_files directory
                saved_file_path = os.path.join(upload_dir, unique_filename)
                
                # Copy uploaded file to upload_files directory
                shutil.copy2(file_upload.name, saved_file_path)
                
                # Generate accessible URL for OCR server
                file_server_url = f"http://localhost:8889/{unique_filename}"
                
                # Also generate local URL as backup
                local_file_url = f"http://localhost:7861/upload_files/{unique_filename}"
                
                # Check file type and process accordingly
                file_ext = os.path.splitext(file_upload.name)[1].lower()
                
                if file_ext == '.pdf':
                    # Process PDF file
                    pdf_text = ""
                    try:
                        # Extract text from PDF using PyMuPDF
                        pdf_document = fitz.open(saved_file_path)
                        for page_num in range(len(pdf_document)):
                            page = pdf_document.load_page(page_num)
                            pdf_text += page.get_text() + "\n"
                        pdf_document.close()
                        
                        # Add text content with PDF processing instructions
                        message_content.append({
                            "type": "text",
                            "text": f"你是一个财务报销专家，请基于以下财务报销规则回答用户的问题，并处理上传的PDF文件。\n\n财务报销规则：\n{rules_context}\n\n用户问题：{question}\n\n请注意：用户已上传了一个PDF文件，文件内容如下：\n\n{pdf_text}\n\n如果PDF中包含发票信息，请使用 recognize_single_invoice 工具来识别发票信息。请将PDF中的发票内容完整提取出来。\n\n可用的文件访问方式：\n- 文件服务器URL: {file_server_url} (推荐)\n- 本地Gradio URL: {local_file_url}\n\n请使用 recognize_single_invoice 工具，该工具接受以下参数：\n- image_url: 图片的URL地址\n- image_data: base64编码的图片数据\n\n建议优先使用 image_url 参数，值为: {file_server_url}\n\n会话ID: {session_id}"
                        })
                        
                    except Exception as e:
                        logger.error(f"Error processing PDF: {e}")
                        message_content.append({
                            "type": "text",
                            "text": f"你是一个财务报销专家，请基于以下财务报销规则回答用户的问题。\n\n财务报销规则：\n{rules_context}\n\n用户问题：{question}\n\n请注意：用户上传了一个PDF文件，但在处理文件时出错：{str(e)}\n\n会话ID: {session_id}"
                        })
                else:
                    # Process image file
                    # Read image file and convert to base64
                    with open(saved_file_path, "rb") as img_file:
                        img_data = img_file.read()
                        img_base64 = base64.b64encode(img_data).decode('utf-8')
                    
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
                    data_url = f"data:{mime_type};base64,{img_base64}"
                    
                    # Add text content with image processing instructions
                    message_content.append({
                        "type": "text",
                        "text": f"你是一个财务报销专家，请基于以下财务报销规则回答用户的问题，并处理上传的图片。\n\n财务报销规则：\n{rules_context}\n\n用户问题：{question}\n\n请注意：用户已上传了一张图片，请使用 recognize_single_invoice 工具来识别图片中的发票信息。请将图片中的发票内容完整提取出来。\n\n可用的图片访问方式：\n- 文件服务器URL: {file_server_url} (推荐)\n- 本地Gradio URL: {local_file_url}\n- Base64数据: 已准备好\n\n请使用 recognize_single_invoice 工具，该工具接受以下参数：\n- image_url: 图片的URL地址\n- image_data: base64编码的图片数据\n\n建议优先使用 image_url 参数，值为: {file_server_url}\n\n会话ID: {session_id}"
                    })
                    
                    # Add image content
                    message_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": data_url
                        }
                    })
                
                messages.append({"role": "user", "content": message_content})
                
            except Exception as e:
                logger.error(f"Error processing file: {e}")
                # Fall back to text-only if file processing fails
                prompt = f"""
                你是一个财务报销专家，请基于以下财务报销规则回答用户的问题。
                
                财务报销规则：
                {rules_context}
                
                用户问题：{question}
                
                请提供准确、详细的回答，并引用相关的规则。
                
                会话ID: {session_id}
                """
                messages.append({"role": "user", "content": prompt})
        else:
            # No image, use standard text prompt
            prompt = f"""
            你是一个财务报销专家，请基于以下财务报销规则回答用户的问题。
            
            财务报销规则：
            {rules_context}
            
            用户问题：{question}
            
            请提供准确、详细的回答，并引用相关的规则。
            
            会话ID: {session_id}
            """
            messages.append({"role": "user", "content": prompt})
        
        # Get MCP tools if available
        mcp_tools = []
        if mcp_client and mcp_client.connected_servers:
            mcp_tools = mcp_client.get_all_tools()
        
        # Make the API call with or without tools
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            tools=mcp_tools if mcp_tools else None,
            tool_choice="auto" if mcp_tools else None,
            extra_body={
                "enable_thinking": False
            }
        )
        
        assistant_msg = response.choices[0].message
        
        # If there are tool calls, handle them
        if assistant_msg.tool_calls and mcp_client:
            # Add the initial response to history
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": assistant_msg.content or ""})
            
            # Process each tool call
            for call in assistant_msg.tool_calls:
                tool_name = call.function.name
                tool_args = json.loads(call.function.arguments)
                
                # Add tool call message to history
                history.append({
                    "role": "assistant",
                    "content": f"使用工具: {tool_name}",
                    "metadata": {"title": f"Tool: {tool_name}", "status": "pending"}
                })
                
                # Execute the tool
                try:
                    # Special handling for invoice recognition tool
                    if tool_name == "recognize_single_invoice":
                        logger.info(f"处理发票识别工具参数: {tool_args}")
                        
                        # Add session_id to the tool arguments
                        tool_args["session_id"] = session_id
                        logger.info(f"添加会话ID: {session_id}")
                        
                        # Get OpenAI configuration from session
                        session_data = session_store.get(session_id, {})
                        if session_data:
                            # Add OpenAI configuration directly to tool arguments
                            if "client" in session_data and "model" in session_data:
                                # Try to get API key and base URL from environment variables
                                api_key = os.environ.get(f"OPENAI_API_KEY_{session_id}")
                                base_url = os.environ.get(f"OPENAI_BASE_URL_{session_id}")
                                model = os.environ.get(f"OPENAI_MODEL_{session_id}")
                                
                                if api_key and base_url and model:
                                    tool_args["api_key"] = api_key
                                    tool_args["base_url"] = base_url
                                    tool_args["model"] = model
                                    logger.info("已添加OpenAI配置参数到工具调用")
                        
                        # Check if there's an image_url parameter
                        if "image_url" in tool_args:
                            image_url = tool_args["image_url"]
                            logger.info(f"处理图片URL: {image_url}")
                            
                            # If it's a local URL, try to convert to an accessible URL
                            if image_url.startswith("http://localhost:7861/upload_files/"):
                                filename = image_url.split("/")[-1]
                                local_file_path = os.path.join(os.getcwd(), "upload_files", filename)
                                
                                if os.path.exists(local_file_path):
                                    # Use file server URL to ensure OCR server can access it
                                    file_server_url = f"http://localhost:8889/{filename}"
                                    tool_args["image_url"] = file_server_url
                                    logger.info(f"更新图片URL为文件服务器URL: {file_server_url}")
                                    
                                    # Also provide base64 data as backup (OCR tool supports this parameter)
                                    try:
                                        with open(local_file_path, "rb") as img_file:
                                            img_data = img_file.read()
                                            img_base64 = base64.b64encode(img_data).decode('utf-8')
                                            tool_args["image_data"] = img_base64
                                            logger.info("已添加base64图片数据作为备用")
                                    except Exception as e:
                                        logger.warning(f"无法生成base64数据: {e}")
                                else:
                                    logger.error(f"本地文件不存在: {local_file_path}")
                            elif image_url.startswith("http://localhost:8889/"):
                                # Already a file server URL, no conversion needed
                                logger.info(f"使用文件服务器URL: {image_url}")
                        
                        # Ensure only OCR tool supported parameters are passed
                        valid_args = {}
                        if "image_url" in tool_args:
                            valid_args["image_url"] = tool_args["image_url"]
                        if "image_data" in tool_args:
                            valid_args["image_data"] = tool_args["image_data"]
                        # Always include session_id for invoice recognition tool
                        valid_args["session_id"] = session_id
                        # Include OpenAI configuration if available
                        if "api_key" in tool_args:
                            valid_args["api_key"] = tool_args["api_key"]
                        if "base_url" in tool_args:
                            valid_args["base_url"] = tool_args["base_url"]
                        if "model" in tool_args:
                            valid_args["model"] = tool_args["model"]
                        
                        tool_args = valid_args
                        logger.info(f"最终传递给OCR工具的参数: {list(tool_args.keys())}")
                    
                    # Get the target server for the tool
                    target_server = mcp_client.get_server_for_tool(tool_name)
                    if target_server and target_server in mcp_client.sessions:
                        tool_result = loop.run_until_complete(
                            mcp_client.sessions[target_server].call_tool(tool_name, tool_args)
                        )
                        
                        # Process tool result
                        if hasattr(tool_result, 'content'):
                            result_content = tool_result.content
                        elif isinstance(tool_result, dict):
                            result_content = tool_result
                        else:
                            result_content = str(tool_result)
                        
                        # Add tool result to history
                        history.append({
                            "role": "assistant",
                            "content": f"工具结果: {tool_name}",
                            "metadata": {"title": f"Result: {tool_name}", "status": "done"}
                        })
                        
                        if isinstance(result_content, dict):
                            result_content = json.dumps(result_content, ensure_ascii=False, indent=2)
                        elif isinstance(result_content, list):
                            result_content = "\n".join(map(str, result_content))
                        
                        history.append({
                            "role": "assistant",
                            "content": f"```\n{result_content}\n```",
                            "metadata": {"title": "Raw Output"}
                        })
                        
                        # Make a follow-up call to the LLM with the tool results
                        follow_up_messages = [
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": assistant_msg.content or "", "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {"name": tool_name, "arguments": call.function.arguments}
                                }
                            ]},
                            {"role": "tool", "tool_call_id": call.id, "content": str(result_content)}
                        ]
                        
                        follow_response = client.chat.completions.create(
                            model=model,
                            messages=follow_up_messages,
                            temperature=0.3,
                            extra_body={
                                "enable_thinking": False
                            }
                        )
                        
                        # Add the final response to history
                        if follow_response.choices[0].message.content:
                            history.append({
                                "role": "assistant",
                                "content": follow_response.choices[0].message.content
                            })
                        
                    else:
                        history.append({
                            "role": "assistant",
                            "content": f"❌ 工具 '{tool_name}' 未找到对应的服务器连接"
                        })
                        
                except Exception as e:
                    history.append({
                        "role": "assistant",
                        "content": f"❌ 执行工具 '{tool_name}' 时出错: {str(e)}"
                    })
            
            return "", history
        else:
            # No tool calls, just return the response
            answer = assistant_msg.content
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": answer})
            
            return "", history
        
    except Exception as e:
        error_response = f"❌ 回答问题时出错: {str(e)}"
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": error_response})
        return "", history

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
        return example_path, "审核一下此张发票"
    else:
        logger.error(f"Example invoice not found at {example_path}")
        return None, "审核一下此张发票"

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
    """Connect to invoice OCR MCP server"""
    import subprocess
    import time
    global global_invoice_server_status
    
    if not global_mcp_client:
        global_invoice_server_status = "❌ MCP客户端未初始化"
        return global_invoice_server_status
    
    try:
        # 首先检查是否已经连接到服务器
        if "invoice_server" in global_mcp_client.connected_servers:
            global_invoice_server_status = "✅ 发票识别服务器已连接"
            return global_invoice_server_status
        
        # 如果未连接，尝试连接
        command_list = command.split()
        result = global_mcp_client.connect(command_list, "invoice_server")
        
        # 如果连接失败，尝试启动服务器
        if "❌" in result:
            logger.info("发票识别服务器连接失败，尝试启动服务器...")
            try:
                # 启动服务器
                server_process = subprocess.Popen(
                    command_list,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                logger.info(f"发票识别服务器已启动，PID: {server_process.pid}")
                time.sleep(3)  # 等待服务器启动
                
                # 再次尝试连接
                result = global_mcp_client.connect(command_list, "invoice_server")
            except Exception as start_e:
                logger.error(f"启动发票识别服务器失败: {start_e}")
                global_invoice_server_status = f"❌ 连接和启动发票识别服务器都失败: {str(e)}; 启动失败: {str(start_e)}"
                return global_invoice_server_status
        
        global_invoice_server_status = result
        return global_invoice_server_status
    except Exception as e:
        global_invoice_server_status = f"❌ 连接发票识别服务器失败: {str(e)}"
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
        with gr.Row():
            with gr.Column():
                gr.Markdown("## OpenAI API 设置")
                
                api_key_input = gr.Textbox(
                    label="API Key",
                    placeholder="请输入您的 OpenAI API Key",
                    type="password"
                )
                
                base_url_input = gr.Textbox(
                    label="Base URL",
                    placeholder="请输入 OpenAI API 的 Base URL (例如: https://api.openai.com/v1)",
                    value="https://api-inference.modelscope.cn/v1"
                )
                
                model_input = gr.Textbox(
                    label="Model",
                    placeholder="请输入模型名称 (例如: gpt-3.5-turbo)",
                    value="Qwen/Qwen3-235B-A22B"
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
                gr.Markdown("### 📄 发票识别LLM服务器")
                gr.Markdown("""
                **功能说明：**
                - 📋 **多格式支持**: 处理图片文件（JPG、PNG等）和PDF文档
                - 🔍 **先进OCR技术**: 使用PaddleOCR进行准确的文本提取
                - 🤖 **AI驱动分析**: 利用大模型进行智能字段提取
                - 🔒 **隐私保护**: 所有处理都在本地进行，确保敏感发票数据安全
                
                **技术架构：**
                1. **文档处理**:
                   - 🖼️ 图片：使用PaddleOCR进行OCR处理
                   - 📑 PDF：使用PyMuPDF直接提取文本
                2. **信息提取**:
                   - 🤖 使用大模型进行智能字段解析
                   - ✅ 高级验证和纠正算法
                """)
                    
                invoice_server_command = gr.Textbox(
                    label="服务器命令",
                    placeholder="python mcp_invoice_stdio.py",
                    value="python mcp_invoice_stdio.py",
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
            
            with gr.Column(scale=2):
                gr.Markdown("## 对话记录")
                
                chatbot = gr.Chatbot(
                    label="对话记录",
                    height=500,
                    type="messages"
                )
        
        # Set up event handlers for chat functionality
        ask_btn.click(
            fn=answer_question_with_session,
            inputs=[question_input, chatbot, session_id, file_upload],
            outputs=[question_input, chatbot]
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
    # Clean up old upload files
    cleanup_upload_files()
    
    # Ensure upload_files directory exists
    os.makedirs(os.path.join(os.getcwd(), "upload_files"), exist_ok=True)
    
    # Start file server
    file_server_base_url = start_file_server(8889)
    logger.info(f"文件服务器已启动: {file_server_base_url}")

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
            invoice_result = global_mcp_client.connect(["python", "mcp_invoice_stdio.py"], "invoice_server")
            global_invoice_server_status = invoice_result
            logger.info(f"发票识别服务器连接结果: {invoice_result}")
        except Exception as e:
            global_invoice_server_status = f"❌ 连接发票识别服务器失败: {str(e)}"
            logger.error(f"连接发票识别服务器失败: {e}")
        
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