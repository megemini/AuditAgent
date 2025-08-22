"""
pip install fastmcp gradio openai python-dotenv
"""

# ==================== API 配置 ====================
# 请在此处配置您的 API 信息
# API_KEY = "292a9a1fd77e793cc795e91c02a18dd52b93ab5b"  # 您的 API 密钥
# BASE_URL = "https://aistudio.baidu.com/llm/lmapi/v3"    # API 基础 URL
# MODEL_NAME = "ernie-4.5-turbo-128k-preview"             # 使用的模型名称


API_KEY = "ms-b51aa344-4aca-4c29-814b-316e14fe1920"  # 您的 API 密钥
BASE_URL = "https://api-inference.modelscope.cn/v1"    # API 基础 URL
MODEL_NAME = "Qwen/Qwen3-235B-A22B"             # 使用的模型名称

# ==================== MCP 服务器配置 ====================
# 城市分级查询服务器配置
CITY_SERVER_URL = "http://0.0.0.0:8080/sse"

# 发票OCR识别系统服务器配置
INVOICE_OCR_SERVER_URL = "http://0.0.0.0:8081/sse"


# ==================== 导入模块 ====================
import asyncio
import json
import os
import logging
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Union

import gradio as gr
from gradio.components.chatbot import ChatMessage
from openai import AsyncOpenAI
from dotenv import load_dotenv

from fastmcp.client import Client     # 或 SSEClient/StdioClient

load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ai_interaction.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


class FastMCPClientWrapper:
    def __init__(self):
        self.sessions: Dict[str, Client] = {}  # 存储多个服务器连接
        self.exit_stacks: Dict[str, AsyncExitStack] = {}  # 存储多个服务器的exit_stack
        self.openai_client = AsyncOpenAI(
            api_key=API_KEY,
            base_url=BASE_URL
        )
        self.tools: Dict[str, List[Dict[str, Any]]] = {}  # 存储每个服务器的工具
        self.active_server: str | None = None  # 当前活跃的服务器

    # ------------------------- 连接 -------------------------
    def connect(self, server_url: str, server_name: str) -> str:
        """同步封装，方便 Gradio 直接调用"""
        return loop.run_until_complete(self._connect(server_url, server_name))

    async def _connect(self, server_url: str, server_name: str) -> str:
        # 关闭该服务器的旧连接
        if server_name in self.exit_stacks:
            await self.exit_stacks[server_name].aclose()
        
        self.exit_stacks[server_name] = AsyncExitStack()

        # ✅ 关键：fastmcp 的 Client 直接支持 SSE
        self.sessions[server_name] = await self.exit_stacks[server_name].enter_async_context(
            Client(server_url)   # 如果是本地 stdio，可换成 StdioClient(...)
        )

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
        
        # 设置为活跃服务器
        self.active_server = server_name
        
        return f"Connected to {server_name}. Available tools: {', '.join(t['function']['name'] for t in self.tools[server_name])}"
    
    def switch_server(self, server_name: str) -> str:
        """切换活跃服务器"""
        if server_name in self.sessions:
            self.active_server = server_name
            available_tools = ', '.join(t['function']['name'] for t in self.tools[server_name])
            return f"Switched to {server_name}. Available tools: {available_tools}"
        else:
            return f"Server {server_name} not connected. Please connect first."

    # ------------------------- 对话 -------------------------
    def process_message(self, message: str, history: List[Union[Dict[str, Any], ChatMessage]], image_file=None):
        if not self.active_server or self.active_server not in self.sessions:
            return (
                history
                + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": "Please connect to a server first."},
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
            message_content.append({"type": "text", "text": message})
            
            # 添加图片内容
            if hasattr(image_file, 'name'):
                # 读取图片文件并转换为base64
                import base64
                try:
                    with open(image_file.name, 'rb') as f:
                        image_data = base64.b64encode(f.read()).decode('utf-8')
                    
                    # 获取文件扩展名
                    file_extension = image_file.name.split('.')[-1].lower()
                    mime_type = f"image/{file_extension}"
                    
                    message_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}"
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
        logger.info(f"发送的工具: {json.dumps(self.tools[self.active_server], ensure_ascii=False, indent=2) if self.active_server and self.active_server in self.tools else '无'}")
        
        resp = await self.openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=openai_msgs,
            tools=self.tools[self.active_server] if self.active_server and self.active_server in self.tools else None,
            tool_choice="auto" if self.active_server and self.active_server in self.tools else None,
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
        
        # logger.info('------------', resp)

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
                
                tool_result = await self.sessions[self.active_server].call_tool(name, args)
                results[-2]["metadata"]["status"] = "done"
                
                # 记录工具结果
                tool_result_data = {
                    'content': tool_result.content,
                    'isError': tool_result.is_error
                }
                logger.info(f"工具结果: {json.dumps(tool_result_data, ensure_ascii=False, indent=2, default=str)}")

                results.append(
                    {
                        "role": "assistant",
                        "content": "Tool result:",
                        "metadata": {"title": f"Result: {name}", "status": "done"},
                    }
                )

                content = tool_result.content
                if isinstance(content, list):
                    content = "\n".join(map(str, content))
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
                    tools=self.tools[self.active_server] if self.active_server and self.active_server in self.tools else None,
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
client = FastMCPClientWrapper()


def gradio_app():
    with gr.Blocks(title="智能助手系统") as demo:
        gr.Markdown("# 智能助手系统")
        gr.Markdown("支持城市分级查询和发票OCR识别功能")

        # 服务器连接区域
        with gr.Row(equal_height=True):
            with gr.Column(scale=1):
                gr.Markdown("### 城市分级查询服务器")
                city_server_url = gr.Textbox(
                    label="City Server URL",
                    placeholder="http://0.0.0.0:8080/sse",
                    value=CITY_SERVER_URL,
                )
                city_connect_btn = gr.Button("Connect City Server")
            
            with gr.Column(scale=1):
                gr.Markdown("### 发票OCR识别服务器")
                ocr_server_url = gr.Textbox(
                    label="OCR Server URL",
                    placeholder="http://0.0.0.0:8081/sse",
                    value=INVOICE_OCR_SERVER_URL,
                )
                ocr_connect_btn = gr.Button("Connect OCR Server")

        # 服务器状态和切换区域
        with gr.Row(equal_height=True):
            city_status = gr.Textbox(label="City Server Status", interactive=False)
            ocr_status = gr.Textbox(label="OCR Server Status", interactive=False)
            switch_to_city = gr.Button("Switch to City Server")
            switch_to_ocr = gr.Button("Switch to OCR Server")

        # 当前活跃服务器状态
        current_server = gr.Textbox(label="Current Active Server", interactive=False, value="None")

        # 聊天界面
        chatbot = gr.Chatbot(
            value=[],
            height=500,
            type="messages",
            show_copy_button=True,
            avatar_images=("👤", "🤖"),
        )

        # 输入区域
        with gr.Row(equal_height=True):
            with gr.Column(scale=3):
                msg = gr.Textbox(label="Your question", placeholder="输入您的问题...", value="")
            with gr.Column(scale=1):
                image_upload = gr.File(
                    label="Upload Image (for OCR)",
                    file_types=["image"],
                    type="filepath"
                )
            with gr.Column(scale=1):
                submit_btn = gr.Button("Send")
                clear_btn = gr.Button("Clear")

        # 事件绑定
        def connect_city_server(url):
            return client.connect(url, "city_server")
        
        def connect_ocr_server(url):
            return client.connect(url, "ocr_server")
        
        city_connect_btn.click(connect_city_server, inputs=city_server_url, outputs=city_status)
        ocr_connect_btn.click(connect_ocr_server, inputs=ocr_server_url, outputs=ocr_status)
        
        switch_to_city.click(client.switch_server, inputs=gr.Textbox(value="city_server", visible=False), outputs=current_server)
        switch_to_ocr.click(client.switch_server, inputs=gr.Textbox(value="ocr_server", visible=False), outputs=current_server)
        
        msg.submit(client.process_message, [msg, chatbot, image_upload], [chatbot, msg, image_upload])
        submit_btn.click(client.process_message, [msg, chatbot, image_upload], [chatbot, msg, image_upload])
        clear_btn.click(lambda: [], None, chatbot)

    return demo


if __name__ == "__main__":
    demo = gradio_app()
    demo.launch(debug=True)