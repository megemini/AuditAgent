"""
智能助手系统 - stdio版本
使用stdio协议连接MCP服务器
pip install fastmcp gradio openai python-dotenv
"""

# ==================== API 配置 ====================
API_KEY = "ms-b51aa344-4aca-4c29-814b-316e14fe1920"  # 您的 API 密钥
BASE_URL = "https://api-inference.modelscope.cn/v1"    # API 基础 URL
MODEL_NAME = "Qwen/Qwen3-235B-A22B"             # 使用的模型名称

# ==================== MCP 服务器配置 ====================
# 城市分级查询服务器配置 (stdio)
CITY_SERVER_COMMAND = ["python", "mcp_citytier_stdio.py"]

# 发票OCR识别系统服务器配置 (stdio)
INVOICE_OCR_SERVER_COMMAND = ["python", "mcp_invoice_stdio.py"]

# ==================== 导入模块 ====================
import asyncio
import json
import os
import logging
import subprocess
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Union
import threading
import http.server
import socketserver
import base64
import uuid
import shutil

import gradio as gr
from gradio.components.chatbot import ChatMessage
from openai import AsyncOpenAI
from dotenv import load_dotenv

from fastmcp.client import Client
from fastmcp.client.transports import PythonStdioTransport

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ai_interaction_stdio.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


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
        self.openai_client = AsyncOpenAI(
            api_key=API_KEY,
            base_url=BASE_URL
        )
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
            # ✅ 关键：使用 PythonStdioTransport 创建 Client
            # 假设 server_command 是 ["python", "script.py"] 格式
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

    # ------------------------- 对话 -------------------------
    def process_message(self, message: str, history: List[Union[Dict[str, Any], ChatMessage]], image_file=None):
        if not self.connected_servers:
            return (
                history
                + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": "Please connect to at least one server first."},
                ],
                gr.Textbox(value=""),
                None,
            )
        new_msgs = loop.run_until_complete(self._process_query(message, history, image_file))
        return history + [{"role": "user", "content": message}] + new_msgs, gr.Textbox(value=""), None

    async def _process_query(self, message: str, history, image_file=None):
        openai_msgs = []
        for m in history:
            role, content = (m.role, m.content) if isinstance(m, ChatMessage) else (m["role"], m["content"])
            if role in {"user", "assistant", "system"}:
                openai_msgs.append({"role": role, "content": content})

        # 如果有图片文件，处理图片内容
        if image_file:
            message_content = []

            # 添加图片内容
            if hasattr(image_file, 'name'):
                try:
                    # 生成唯一的文件名
                    unique_filename = f"{uuid.uuid4()}_{os.path.basename(image_file.name)}"

                    # 确保 upload_files 目录存在
                    upload_dir = os.path.join(os.getcwd(), "upload_files")
                    os.makedirs(upload_dir, exist_ok=True)

                    # 保存文件到 upload_files 目录
                    saved_file_path = os.path.join(upload_dir, unique_filename)

                    # 复制上传的文件到 upload_files 目录
                    shutil.copy2(image_file.name, saved_file_path)

                    # 读取图片文件并转换为base64
                    with open(saved_file_path, "rb") as img_file:
                        img_data = img_file.read()
                        img_base64 = base64.b64encode(img_data).decode('utf-8')

                    # 获取文件扩展名来确定MIME类型
                    file_ext = os.path.splitext(image_file.name)[1].lower()
                    mime_type = {
                        '.jpg': 'image/jpeg',
                        '.jpeg': 'image/jpeg',
                        '.png': 'image/png',
                        '.gif': 'image/gif',
                        '.bmp': 'image/bmp',
                        '.webp': 'image/webp'
                    }.get(file_ext, 'image/jpeg')

                    # 创建data URL
                    data_url = f"data:{mime_type};base64,{img_base64}"

                    # 生成可被OCR服务器访问的URL（使用独立的文件服务器）
                    file_server_url = f"http://localhost:8889/{unique_filename}"

                    # 同时生成本地URL作为备用
                    local_image_url = f"http://localhost:7861/upload_files/{unique_filename}"

                    message_content.append({
                        "type": "text",
                        "text": message + f"\n\n请注意：用户已上传了一张图片，请使用 recognize_single_invoice 工具来识别图片中的发票信息。请将图片中的发票内容完整提取出来。\n\n可用的图片访问方式：\n- 文件服务器URL: {file_server_url} (推荐)\n- 本地Gradio URL: {local_image_url}\n- Base64数据: 已准备好\n\n请使用 recognize_single_invoice 工具，该工具接受以下参数：\n- image_url: 图片的URL地址\n- image_data: base64编码的图片数据\n\n建议优先使用 image_url 参数，值为: {file_server_url}"
                    })

                    message_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": data_url
                        }
                    })
                except Exception as e:
                    logger.error(f"Error processing image: {e}")
                    message_content.append({"type": "text", "text": f"[图片处理错误: {str(e)}]"})

            openai_msgs.append({"role": "user", "content": message_content})
        else:
            openai_msgs.append({"role": "user", "content": message})

        # 首次调用 LLM
        logger.info("=== 首次调用 LLM ===")
        logger.info(f"发送给 OpenAI 的消息: {json.dumps(openai_msgs, ensure_ascii=False, indent=2)}")
        logger.info(f"发送的工具: {json.dumps(self.get_all_tools(), ensure_ascii=False, indent=2) if self.get_all_tools() else '无'}")

        resp = await self.openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=openai_msgs,
            tools=self.get_all_tools() if self.get_all_tools() else None,
            tool_choice="auto" if self.get_all_tools() else None,
            extra_body={
                "enable_thinking": False
            }
        )

        # 记录 OpenAI 响应
        response_data = {
            'id': resp.id,
            'model': resp.model,
            'choices': []
        }

        for choice in resp.choices:
            choice_data = {
                'index': choice.index,
                'message': {
                    'role': choice.message.role,
                    'content': choice.message.content,
                    'tool_calls': []
                },
                'finish_reason': choice.finish_reason
            }

            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_call_data = {
                        'id': tc.id,
                        'type': tc.type,
                        'function': {
                            'name': tc.function.name,
                            'arguments': tc.function.arguments
                        }
                    }
                    choice_data['message']['tool_calls'].append(tool_call_data)

            response_data['choices'].append(choice_data)

        logger.info(f"OpenAI 响应: {json.dumps(response_data, ensure_ascii=False, indent=2)}")

        results = []
        assistant_msg = resp.choices[0].message

        if assistant_msg.content:
            results.append({"role": "assistant", "content": assistant_msg.content})

        if assistant_msg.tool_calls:
            for call in assistant_msg.tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments)

                results.append(
                    {
                        "role": "assistant",
                        "content": f"Using tool: {name}",
                        "metadata": {"title": f"Tool: {name}", "status": "pending"},
                    }
                )
                results.append(
                    {
                        "role": "assistant",
                        "content": f"```json\n{json.dumps(args, ensure_ascii=False, indent=2)}\n```",
                        "metadata": {"title": "Parameters"},
                    }
                )

                # ✅ 关键：用 fastmcp 的 call_tool
                logger.info(f"=== 调用工具 {name} ===")
                logger.info(f"工具参数: {json.dumps(args, ensure_ascii=False, indent=2)}")

                # 特殊处理发票识别工具的图片参数
                if name == "recognize_single_invoice":
                    logger.info(f"处理发票识别工具参数: {args}")

                    # 检查是否有image_url参数
                    if "image_url" in args:
                        image_url = args["image_url"]
                        logger.info(f"处理图片URL: {image_url}")

                        # 如果是本地URL，尝试转换为可访问的URL
                        if image_url.startswith("http://localhost:7861/upload_files/"):
                            filename = image_url.split("/")[-1]
                            local_file_path = os.path.join(os.getcwd(), "upload_files", filename)

                            if os.path.exists(local_file_path):
                                # 使用文件服务器URL，确保OCR服务器能访问
                                file_server_url = f"http://localhost:8889/{filename}"
                                args["image_url"] = file_server_url
                                logger.info(f"更新图片URL为文件服务器URL: {file_server_url}")

                                # 同时提供base64数据作为备用（OCR工具支持此参数）
                                try:
                                    with open(local_file_path, "rb") as img_file:
                                        img_data = img_file.read()
                                        img_base64 = base64.b64encode(img_data).decode('utf-8')
                                        args["image_data"] = img_base64
                                        logger.info("已添加base64图片数据作为备用")
                                except Exception as e:
                                    logger.warning(f"无法生成base64数据: {e}")
                            else:
                                logger.error(f"本地文件不存在: {local_file_path}")
                        elif image_url.startswith("http://localhost:8889/"):
                            # 已经是文件服务器URL，无需转换
                            logger.info(f"使用文件服务器URL: {image_url}")

                    # 确保只传递OCR工具支持的参数（image_url 和 image_data）
                    valid_args = {}
                    if "image_url" in args:
                        valid_args["image_url"] = args["image_url"]
                    if "image_data" in args:
                        valid_args["image_data"] = args["image_data"]

                    args = valid_args
                    logger.info(f"最终传递给OCR工具的参数: {list(args.keys())}")

                # 根据工具名称获取对应的服务器
                target_server = self.get_server_for_tool(name)
                if target_server and target_server in self.sessions:
                    tool_result = await self.sessions[target_server].call_tool(name, args)
                else:
                    tool_result = type('ToolResult', (), {
                        'content': f"Error: Tool '{name}' not found in any connected server.",
                        'is_error': True
                    })()
                results[-2]["metadata"]["status"] = "done"

                # 记录工具结果
                # 处理 FastMCP 工具返回的结果（可能是字典或对象）
                if hasattr(tool_result, 'content'):
                    # 对象格式
                    tool_result_content = tool_result.content
                    tool_result_is_error = getattr(tool_result, 'is_error', False)
                elif isinstance(tool_result, dict):
                    # 字典格式（FastMCP 工具通常返回字典）
                    tool_result_content = tool_result
                    tool_result_is_error = not tool_result.get('success', False)
                else:
                    # 其他格式
                    tool_result_content = str(tool_result)
                    tool_result_is_error = False

                tool_result_data = {
                    'content': tool_result_content,
                    'isError': tool_result_is_error
                }
                logger.info(f"工具结果: {json.dumps(tool_result_data, ensure_ascii=False, indent=2, default=str)}")

                results.append(
                    {
                        "role": "assistant",
                        "content": "Tool result:",
                        "metadata": {"title": f"Result: {name}", "status": "done"},
                    }
                )

                content = tool_result_content
                if isinstance(content, list):
                    content = "\n".join(map(str, content))
                elif isinstance(content, dict):
                    content = json.dumps(content, ensure_ascii=False, indent=2)
                results.append(
                    {
                        "role": "assistant",
                        "content": f"```\n{content}\n```",
                        "metadata": {"title": "Raw Output"},
                    }
                )

                # 将工具结果回写给 OpenAI 做二次推理
                openai_msgs.extend(
                    [
                        {
                            "role": "assistant",
                            "content": assistant_msg.content or "",
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {"name": name, "arguments": call.function.arguments},
                                }
                            ],
                        },
                        {"role": "tool", "tool_call_id": call.id, "content": content},
                    ]
                )

                # 二次调用
                logger.info("=== 二次调用 LLM ===")
                logger.info(f"发送给 OpenAI 的消息: {json.dumps(openai_msgs, ensure_ascii=False, indent=2)}")

                follow_resp = await self.openai_client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=openai_msgs,
                    tools=self.get_all_tools() if self.get_all_tools() else None,
                    extra_body={
                        "enable_thinking": False
                    }
                )

                # 记录 OpenAI 二次响应
                follow_response_data = {
                    'id': follow_resp.id,
                    'model': follow_resp.model,
                    'choices': []
                }

                for choice in follow_resp.choices:
                    choice_data = {
                        'index': choice.index,
                        'message': {
                            'role': choice.message.role,
                            'content': choice.message.content,
                            'tool_calls': []
                        },
                        'finish_reason': choice.finish_reason
                    }

                    if choice.message.tool_calls:
                        for tc in choice.message.tool_calls:
                            tool_call_data = {
                                'id': tc.id,
                                'type': tc.type,
                                'function': {
                                    'name': tc.function.name,
                                    'arguments': tc.function.arguments
                                }
                            }
                            choice_data['message']['tool_calls'].append(tool_call_data)

                    follow_response_data['choices'].append(choice_data)

                logger.info(f"OpenAI 二次响应: {json.dumps(follow_response_data, ensure_ascii=False, indent=2)}")

                if follow_resp.choices[0].message.content:
                    results.append(
                        {"role": "assistant", "content": follow_resp.choices[0].message.content}
                    )

        return results


# ------------------------- Gradio UI -------------------------
client = FastMCPStdioClientWrapper()


def gradio_app():
    # 自定义CSS样式
    custom_css = """
    .main-header {
        text-align: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }

    .tab-header {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 15px;
        border-left: 4px solid #667eea;
    }

    .status-bar {
        background: #f1f3f4;
        border-radius: 20px;
        padding: 8px 15px;
        margin: 10px 0;
        font-size: 12px;
        border: 1px solid #e0e0e0;
    }

    .config-section {
        background: #ffffff;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        border: 1px solid #e8eaed;
    }

    .chatbot-container {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    """

    with gr.Blocks(
        title="智能助手系统 - stdio版本",
        theme=gr.themes.Soft(
            primary_hue="purple",
            secondary_hue="blue",
            neutral_hue="slate",
            font=["sans-serif", "ui-sans-serif", "system-ui"],
            font_mono=["ui-monospace", "Consolas", "monospace"]
        ),
        css=custom_css
    ) as demo:

        # 添加静态文件路由
        demo.launch_kwargs = {"allowed_paths": [os.path.join(os.getcwd(), "upload_files")]}

        # 美化的标题区域
        gr.HTML("""
        <div class="main-header">
            <h1 style="margin: 0; font-size: 2.8em; font-weight: 800; color: #ffffff; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); letter-spacing: 1px;">🤖 智能助手系统 - stdio版本</h1>
            <p style="margin: 15px 0 0 0; font-size: 1.3em; color: #f8f9fa; font-weight: 500; text-shadow: 1px 1px 2px rgba(0,0,0,0.2);">支持城市分级查询和发票OCR识别功能 (使用stdio协议)</p>
        </div>
        """)

        with gr.Tabs():
            # 聊天Tab
            with gr.TabItem("💬 聊天助手"):
                # 美化的服务器连接状态指示器
                with gr.Row():
                    with gr.Column(scale=6):
                        gr.HTML("""
                        <div class="status-bar">
                            <span style="font-weight: 500; color: #495057;">🔌 服务器状态:</span>
                            <span id="city-status" style="margin-left: 10px; padding: 4px 8px; background: #f8d7da; color: #721c24; border-radius: 12px; font-size: 11px;">城市分级查询 ❌</span>
                            <span id="ocr-status" style="margin-left: 10px; padding: 4px 8px; background: #f8d7da; color: #721c24; border-radius: 12px; font-size: 11px;">发票OCR识别 ❌</span>
                        </div>
                        """)

                    # 隐藏的状态变量，用于JavaScript更新
                    city_status_display = gr.Textbox(visible=False, value="❌ Not connected")
                    ocr_status_display = gr.Textbox(visible=False, value="❌ Not connected")

                # 美化的聊天界面
                gr.HTML("""
                <div class="tab-header">
                    <h3 style="margin: 0; color: #495057;">💬 智能对话 (stdio协议)</h3>
                    <p style="margin: 5px 0 0 0; color: #6c757d; font-size: 14px;">与AI助手进行对话，支持文本和图片OCR识别</p>
                </div>
                """)

                chatbot = gr.Chatbot(
                    value=[],
                    height=500,
                    type="messages",
                    show_copy_button=True,
                    avatar_images=("👤", "🤖"),
                    elem_classes=["chatbot-container"]
                )

                # 美化的输入区域
                with gr.Row(equal_height=True):
                    with gr.Column(scale=3):
                        msg = gr.Textbox(
                            label="",
                            placeholder="输入您的问题或上传图片进行OCR识别...",
                            value="",
                            elem_classes=["message-input"]
                        )
                    with gr.Column(scale=1):
                        image_upload = gr.File(
                            label="📷 上传图片",
                            file_types=["image"],
                            type="filepath"
                        )
                    with gr.Column(scale=1):
                        with gr.Row():
                            submit_btn = gr.Button("📤 发送", variant="primary")
                            clear_btn = gr.Button("🗑️ 清空", variant="secondary")

                # 事件绑定
                msg.submit(client.process_message, [msg, chatbot, image_upload], [chatbot, msg, image_upload])
                submit_btn.click(client.process_message, [msg, chatbot, image_upload], [chatbot, msg, image_upload])
                clear_btn.click(lambda: [], None, chatbot)

            # 设置Tab
            with gr.TabItem("⚙️ 设置"):
                gr.HTML("""
                <div class="tab-header">
                    <h3 style="margin: 0; color: #495057;">⚙️ 系统设置 (stdio协议)</h3>
                    <p style="margin: 5px 0 0 0; color: #6c757d; font-size: 14px;">配置MCP服务器连接和API参数</p>
                </div>
                """)

                with gr.Row():
                    with gr.Column():
                        gr.HTML("""
                        <div class="config-section">
                            <h4 style="margin: 0 0 15px 0; color: #495057;">🏙️ 城市分级查询服务器配置 (stdio)</h4>
                        </div>
                        """)
                        city_server_command = gr.Textbox(
                            label="🖥️ 服务器命令",
                            placeholder="python mcp_citytier_stdio.py",
                            value="python mcp_citytier_stdio.py",
                        )
                        city_server_name = gr.Textbox(
                            label="📝 服务器名称",
                            placeholder="city_server_stdio",
                            value="city_server_stdio",
                        )
                        with gr.Row():
                            city_config_test_btn = gr.Button("🔍 测试连接", variant="secondary")
                            city_config_connect_btn = gr.Button("🔗 连接", variant="primary")
                        city_config_status = gr.Textbox(label="📊 状态", value="未配置", interactive=False)

                    with gr.Column():
                        gr.HTML("""
                        <div class="config-section">
                            <h4 style="margin: 0 0 15px 0; color: #495057;">📄 发票OCR识别服务器配置 (stdio)</h4>
                        </div>
                        """)
                        ocr_server_command = gr.Textbox(
                            label="🖥️ 服务器命令",
                            placeholder="python mcp_invoice_stdio.py",
                            value="python mcp_invoice_stdio.py",
                        )
                        ocr_server_name = gr.Textbox(
                            label="📝 服务器名称",
                            placeholder="ocr_server_stdio",
                            value="ocr_server_stdio",
                        )
                        with gr.Row():
                            ocr_config_test_btn = gr.Button("🔍 测试连接", variant="secondary")
                            ocr_config_connect_btn = gr.Button("🔗 连接", variant="primary")
                        ocr_config_status = gr.Textbox(label="📊 状态", value="未配置", interactive=False)

                with gr.Row():
                    gr.HTML("""
                    <div class="config-section">
                        <h4 style="margin: 0 0 15px 0; color: #495057;">🔑 API 配置</h4>
                    </div>
                    """)
                    api_key_input = gr.Textbox(
                        label="🔑 API Key",
                        placeholder="输入您的API密钥",
                        value=API_KEY,
                        type="password"
                    )
                    base_url_input = gr.Textbox(
                        label="🌐 Base URL",
                        placeholder="API基础URL",
                        value=BASE_URL
                    )
                    model_name_input = gr.Textbox(
                        label="🤖 Model Name",
                        placeholder="模型名称",
                        value=MODEL_NAME
                    )
                    api_save_btn = gr.Button("💾 保存API配置", variant="primary")
                    api_status = gr.Textbox(label="📊 API状态", value="未配置", interactive=False)

                # 设置tab的事件绑定
                def test_city_config(command):
                    command_list = command.split()
                    return client.test_connection(command_list, "city_server_stdio")

                def test_ocr_config(command):
                    command_list = command.split()
                    return client.test_connection(command_list, "ocr_server_stdio")

                def connect_city_server(command):
                    command_list = command.split()
                    result = client.connect(command_list, "city_server_stdio")
                    return result, result

                def connect_ocr_server(command):
                    command_list = command.split()
                    result = client.connect(command_list, "ocr_server_stdio")
                    return result, result

                def save_api_config(api_key, base_url, model_name):
                    global API_KEY, BASE_URL, MODEL_NAME
                    API_KEY = api_key
                    BASE_URL = base_url
                    MODEL_NAME = model_name
                    # 更新客户端的API配置
                    client.openai_client = AsyncOpenAI(
                        api_key=API_KEY,
                        base_url=BASE_URL
                    )
                    return "✅ API配置已保存"

                city_config_test_btn.click(test_city_config, inputs=city_server_command, outputs=city_config_status)
                city_config_connect_btn.click(connect_city_server, inputs=city_server_command, outputs=[city_config_status, city_status_display])
                ocr_config_test_btn.click(test_ocr_config, inputs=ocr_server_command, outputs=ocr_config_status)
                ocr_config_connect_btn.click(connect_ocr_server, inputs=ocr_server_command, outputs=[ocr_config_status, ocr_status_display])
                api_save_btn.click(save_api_config, inputs=[api_key_input, base_url_input, model_name_input], outputs=api_status)

    return demo


if __name__ == "__main__":
    # 确保 upload_files 目录存在
    os.makedirs(os.path.join(os.getcwd(), "upload_files"), exist_ok=True)

    # 启动文件服务器
    file_server_base_url = start_file_server(8889)
    logger.info(f"文件服务器已启动: {file_server_base_url}")

    demo = gradio_app()
    demo.launch(debug=True, server_port=7861, allowed_paths=["upload_files"])
