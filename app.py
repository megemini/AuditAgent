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

def start_mcp_servers():
    """启动MCP服务器"""
    import subprocess
    import time
    
    # 启动城市分级服务器
    try:
        city_server_process = subprocess.Popen(
            ["python", "mcp_citytier_stdio.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info(f"城市分级服务器已启动，PID: {city_server_process.pid}")
        time.sleep(2)  # 等待服务器启动
    except Exception as e:
        logger.error(f"启动城市分级服务器失败: {e}")
    
    # 启动发票识别服务器
    try:
        invoice_server_process = subprocess.Popen(
            ["python", "mcp_invoice_stdio.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info(f"发票识别服务器已启动，PID: {invoice_server_process.pid}")
        time.sleep(2)  # 等待服务器启动
    except Exception as e:
        logger.error(f"启动发票识别服务器失败: {e}")
    
    return city_server_process, invoice_server_process

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

def init_session():
    session_id = str(uuid4())
    session_store[session_id] = {
        "client": None,
        "model": None,
        "reimbursement_rules": [],
        "mcp_client": FastMCPStdioClientWrapper()
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
        
        return "✅ 连接成功！API 配置有效。"
    except Exception as e:
        return f"❌ 连接失败: {str(e)}"

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
    mcp_client = session_data.get("mcp_client")
    
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
                            "text": f"你是一个财务报销专家，请基于以下财务报销规则回答用户的问题，并处理上传的PDF文件。\n\n财务报销规则：\n{rules_context}\n\n用户问题：{question}\n\n请注意：用户已上传了一个PDF文件，文件内容如下：\n\n{pdf_text}\n\n如果PDF中包含发票信息，请使用 recognize_single_invoice 工具来识别发票信息。请将PDF中的发票内容完整提取出来。\n\n可用的文件访问方式：\n- 文件服务器URL: {file_server_url} (推荐)\n- 本地Gradio URL: {local_file_url}\n\n请使用 recognize_single_invoice 工具，该工具接受以下参数：\n- image_url: 图片的URL地址\n- image_data: base64编码的图片数据\n\n建议优先使用 image_url 参数，值为: {file_server_url}"
                        })
                        
                    except Exception as e:
                        logger.error(f"Error processing PDF: {e}")
                        message_content.append({
                            "type": "text",
                            "text": f"你是一个财务报销专家，请基于以下财务报销规则回答用户的问题。\n\n财务报销规则：\n{rules_context}\n\n用户问题：{question}\n\n请注意：用户上传了一个PDF文件，但在处理文件时出错：{str(e)}"
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
                        "text": f"你是一个财务报销专家，请基于以下财务报销规则回答用户的问题，并处理上传的图片。\n\n财务报销规则：\n{rules_context}\n\n用户问题：{question}\n\n请注意：用户已上传了一张图片，请使用 recognize_single_invoice 工具来识别图片中的发票信息。请将图片中的发票内容完整提取出来。\n\n可用的图片访问方式：\n- 文件服务器URL: {file_server_url} (推荐)\n- 本地Gradio URL: {local_file_url}\n- Base64数据: 已准备好\n\n请使用 recognize_single_invoice 工具，该工具接受以下参数：\n- image_url: 图片的URL地址\n- image_data: base64编码的图片数据\n\n建议优先使用 image_url 参数，值为: {file_server_url}"
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
                        
                        # Ensure only OCR tool supported parameters are passed (image_url and image_data)
                        valid_args = {}
                        if "image_url" in tool_args:
                            valid_args["image_url"] = tool_args["image_url"]
                        if "image_data" in tool_args:
                            valid_args["image_data"] = tool_args["image_data"]
                        
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

def connect_city_server_with_session(command, session_id: str):
    """Connect to city tier MCP server"""
    import subprocess
    import time
    
    session_data = session_store.get(session_id, {})
    mcp_client = session_data.get("mcp_client")
    
    if not mcp_client:
        return "❌ MCP客户端未初始化"
    
    try:
        # 首先检查是否已经连接到服务器
        if "citytier_server" in mcp_client.connected_servers:
            return "✅ 城市分级服务器已连接"
        
        # 如果未连接，尝试连接
        command_list = command.split()
        result = mcp_client.connect(command_list, "citytier_server")
        
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
                result = mcp_client.connect(command_list, "citytier_server")
            except Exception as start_e:
                logger.error(f"启动城市分级服务器失败: {start_e}")
                return f"❌ 连接和启动城市分级服务器都失败: {str(e)}; 启动失败: {str(start_e)}"
        
        return result
    except Exception as e:
        return f"❌ 连接城市分级服务器失败: {str(e)}"

def connect_invoice_server_with_session(command, session_id: str):
    """Connect to invoice OCR MCP server"""
    import subprocess
    import time
    
    session_data = session_store.get(session_id, {})
    mcp_client = session_data.get("mcp_client")
    
    if not mcp_client:
        return "❌ MCP客户端未初始化"
    
    try:
        # 首先检查是否已经连接到服务器
        if "invoice_server" in mcp_client.connected_servers:
            return "✅ 发票识别服务器已连接"
        
        # 如果未连接，尝试连接
        command_list = command.split()
        result = mcp_client.connect(command_list, "invoice_server")
        
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
                result = mcp_client.connect(command_list, "invoice_server")
            except Exception as start_e:
                logger.error(f"启动发票识别服务器失败: {start_e}")
                return f"❌ 连接和启动发票识别服务器都失败: {str(e)}; 启动失败: {str(start_e)}"
        
        return result
    except Exception as e:
        return f"❌ 连接发票识别服务器失败: {str(e)}"

def test_city_server_with_session(command, session_id: str):
    """Test connection to city tier MCP server"""
    session_data = session_store.get(session_id, {})
    mcp_client = session_data.get("mcp_client")
    
    if not mcp_client:
        return "❌ MCP客户端未初始化"
    
    try:
        # 首先检查是否已经连接到服务器
        if "citytier_server" in mcp_client.connected_servers:
            return "✅ 城市分级服务器已连接"
        
        # 如果未连接，尝试测试连接
        command_list = command.split()
        result = mcp_client.test_connection(command_list, "citytier_server")
        return result
    except Exception as e:
        return f"❌ 测试城市分级服务器连接失败: {str(e)}"

def test_invoice_server_with_session(command, session_id: str):
    """Test connection to invoice OCR MCP server"""
    session_data = session_store.get(session_id, {})
    mcp_client = session_data.get("mcp_client")
    
    if not mcp_client:
        return "❌ MCP客户端未初始化"
    
    try:
        # 首先检查是否已经连接到服务器
        if "invoice_server" in mcp_client.connected_servers:
            return "✅ 发票识别服务器已连接"
        
        # 如果未连接，尝试测试连接
        command_list = command.split()
        result = mcp_client.test_connection(command_list, "invoice_server")
        return result
    except Exception as e:
        return f"❌ 测试发票识别LLM服务器连接失败: {str(e)}"

def get_mcp_server_status(session_id: str):
    """Get the status of connected MCP servers"""
    session_data = session_store.get(session_id, {})
    mcp_client = session_data.get("mcp_client")
    
    if not mcp_client:
        return {
            "citytier": "❌ 未初始化",
            "invoice": "❌ 未初始化",
            "tools": []
        }
    
    citytier_status = "✅ 已连接" if "citytier_server" in mcp_client.connected_servers else "❌ 未连接"
    invoice_status = "✅ 已连接" if "invoice_server" in mcp_client.connected_servers else "❌ 未连接"
    
    all_tools = mcp_client.get_all_tools()
    tools_info = []
    for tool in all_tools:
        tools_info.append({
            "name": tool["function"]["name"],
            "description": tool["function"]["description"],
            "server": mcp_client.get_server_for_tool(tool["function"]["name"])
        })
    
    return {
        "citytier": citytier_status,
        "invoice": invoice_status,
        "tools": tools_info
    }

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
                
                process_docs_btn = gr.Button("处理文档", variant="primary")
                
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
    
    def setup_mcp_server_tab(self, session_id):
        with gr.Row():
            with gr.Column():
                gr.Markdown("## MCP服务器管理")
                gr.Markdown("在此步骤中，您可以连接和管理MCP（Model Context Protocol）服务器，包括城市分级查询和发票识别LLM服务器。")
                
                # City Tier Server Configuration
                gr.Markdown("### 🏙️ 城市分级查询服务器")
                city_server_command = gr.Textbox(
                    label="服务器命令",
                    placeholder="python mcp_citytier_stdio.py",
                    value="python mcp_citytier_stdio.py"
                )
                
                with gr.Row():
                    city_test_btn = gr.Button("测试连接", variant="secondary")
                    city_connect_btn = gr.Button("连接服务器", variant="primary")
                
                city_status = gr.Textbox(
                    label="连接状态",
                    interactive=False
                )
                
                # Invoice Server Configuration
                gr.Markdown("### 📄 发票识别LLM服务器")
                gr.Markdown("""
                **架构说明：**
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
                    value="python mcp_invoice_stdio.py"
                )
                    
                with gr.Row():
                    invoice_test_btn = gr.Button("测试连接", variant="secondary")
                    invoice_connect_btn = gr.Button("连接服务器", variant="primary")
                
                invoice_status = gr.Textbox(
                    label="连接状态",
                    interactive=False
                )
                
        # Set up event handlers for MCP server management
        city_test_btn.click(
            fn=test_city_server_with_session,
            inputs=[city_server_command, session_id],
            outputs=city_status
        )
        
        city_connect_btn.click(
            fn=connect_city_server_with_session,
            inputs=[city_server_command, session_id],
            outputs=city_status
        )
        
        invoice_test_btn.click(
            fn=test_invoice_server_with_session,
            inputs=[invoice_server_command, session_id],
            outputs=invoice_status
        )
        
        invoice_connect_btn.click(
            fn=connect_invoice_server_with_session,
            inputs=[invoice_server_command, session_id],
            outputs=invoice_status
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
            fn=load_example_invoice,
            outputs=file_upload
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
    
    # Start MCP servers
    logger.info("正在启动MCP服务器...")
    city_server_process, invoice_server_process = start_mcp_servers()
    logger.info("MCP服务器启动完成")
    
    app = AuditAgentApp()
    app.launch()