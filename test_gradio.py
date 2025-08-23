import asyncio
import os
import json
from typing import List, Dict, Any, Union
from contextlib import AsyncExitStack

import gradio as gr
from gradio.components.chatbot import ChatMessage
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI
from dotenv import load_dotenv

# ==================== API 配置 ====================
# 请在此处配置您的 API 信息
API_KEY = "ms-b51aa344-4aca-4c29-814b-316e14fe1920" # os.getenv("OPENAI_API_KEY")  # 您的 API 密钥
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api-inference.modelscope.cn/v1")    # API 基础 URL
MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "Qwen/Qwen3-235B-A22B")             # 使用的模型名称

load_dotenv()

loop = asyncio.get_event_loop()

class MCPClientWrapper:
    def __init__(self):
        self.session = None
        self.exit_stack = None
        self.openai_client = OpenAI(
            api_key=API_KEY,
            base_url=BASE_URL
        )
        self.tools = []
    
    async def connect(self, server_path: str) -> str:
        return await self._connect(server_path)
    
    async def _connect(self, server_path: str) -> str:
        if self.exit_stack:
            await self.exit_stack.aclose()
        
        self.exit_stack = AsyncExitStack()
        
        is_python = server_path.endswith('.py')
        command = "python" if is_python else "node"
        
        server_params = StdioServerParameters(
            command=command,
            args=[server_path],
            env={"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        )
        
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()
        
        response = await self.session.list_tools()
        self.tools = [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema,
            },
        } for tool in response.tools]
        
        tool_names = [tool["function"]["name"] for tool in self.tools]
        return f"Connected to MCP server. Available tools: {', '.join(tool_names)}"
    
    def process_message(self, message: str, history: List[Union[Dict[str, Any], ChatMessage]]) -> tuple:
        if not self.session:
            return history + [
                {"role": "user", "content": message}, 
                {"role": "assistant", "content": "Please connect to an MCP server first."}
            ], gr.Textbox(value="")
        
        new_messages = loop.run_until_complete(self._process_query(message, history))
        return history + [{"role": "user", "content": message}] + new_messages, gr.Textbox(value="")
    
    async def _process_query(self, message: str, history: List[Union[Dict[str, Any], ChatMessage]]):
        openai_messages = []
        for msg in history:
            if isinstance(msg, ChatMessage):
                role, content = msg.role, msg.content
            else:
                role, content = msg.get("role"), msg.get("content")
            
            if role in ["user", "assistant", "system"]:
                openai_messages.append({"role": role, "content": content})
        
        openai_messages.append({"role": "user", "content": message})
        
        response = self.openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=openai_messages,
            tools=self.tools if self.tools else None,
            tool_choice="auto" if self.tools else None,
            extra_body={
                "enable_thinking": False
            }
        )

        result_messages = []
        assistant_msg = response.choices[0].message

        if assistant_msg.content:
            result_messages.append({
                "role": "assistant",
                "content": assistant_msg.content
            })

        if assistant_msg.tool_calls:
            for call in assistant_msg.tool_calls:
                tool_name = call.function.name
                tool_args = json.loads(call.function.arguments)
                
                result_messages.append({
                    "role": "assistant",
                    "content": f"I'll use the {tool_name} tool to help answer your question.",
                    "metadata": {
                        "title": f"Using tool: {tool_name}",
                        "log": f"Parameters: {json.dumps(tool_args, ensure_ascii=True)}",
                        "status": "pending",
                        "id": f"tool_call_{tool_name}"
                    }
                })
                
                result_messages.append({
                    "role": "assistant",
                    "content": "```json\n" + json.dumps(tool_args, indent=2, ensure_ascii=True) + "\n```",
                    "metadata": {
                        "parent_id": f"tool_call_{tool_name}",
                        "id": f"params_{tool_name}",
                        "title": "Tool Parameters"
                    }
                })
                
                result = await self.session.call_tool(tool_name, tool_args)
                
                if result_messages and "metadata" in result_messages[-2]:
                    result_messages[-2]["metadata"]["status"] = "done"
                
                result_messages.append({
                    "role": "assistant",
                    "content": "Here are the results from the tool:",
                    "metadata": {
                        "title": f"Tool Result for {tool_name}",
                        "status": "done",
                        "id": f"result_{tool_name}"
                    }
                })
                
                result_content = result.content
                if isinstance(result_content, list):
                    result_content = "\n".join(str(item) for item in result_content)
                
                try:
                    result_json = json.loads(result_content)
                    if isinstance(result_json, dict) and "type" in result_json:
                        if result_json["type"] == "image" and "url" in result_json:
                            result_messages.append({
                                "role": "assistant",
                                "content": {"path": result_json["url"], "alt_text": result_json.get("message", "Generated image")},
                                "metadata": {
                                    "parent_id": f"result_{tool_name}",
                                    "id": f"image_{tool_name}",
                                    "title": "Generated Image"
                                }
                            })
                        else:
                            result_messages.append({
                                "role": "assistant",
                                "content": "```\n" + result_content + "\n```",
                                "metadata": {
                                    "parent_id": f"result_{tool_name}",
                                    "id": f"raw_result_{tool_name}",
                                    "title": "Raw Output"
                                }
                            })
                except:
                    result_messages.append({
                        "role": "assistant",
                        "content": "```\n" + result_content + "\n```",
                        "metadata": {
                            "parent_id": f"result_{tool_name}",
                            "id": f"raw_result_{tool_name}",
                            "title": "Raw Output"
                        }
                    })
                
                # Add tool result to messages for second LLM call
                openai_messages.extend([
                    {
                        "role": "assistant",
                        "content": assistant_msg.content or "",
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": call.function.arguments},
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": call.id, "content": result_content},
                ])
                
                # Second LLM call
                next_response = self.openai_client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=openai_messages,
                    tools=self.tools if self.tools else None,
                    tool_choice="auto" if self.tools else None
                )
                
                if next_response.choices[0].message.content:
                    result_messages.append({
                        "role": "assistant",
                        "content": next_response.choices[0].message.content
                    })

        return result_messages

client = MCPClientWrapper()

def gradio_interface():
    with gr.Blocks(title="MCP Weather Client") as demo:
        gr.Markdown("# MCP Weather Assistant")
        gr.Markdown("Connect to your MCP weather server and chat with the assistant")
        
        with gr.Row(equal_height=True):
            with gr.Column(scale=4):
                server_path = gr.Textbox(
                    label="Server Script Path",
                    placeholder="Enter path to server script (e.g., weather.py)",
                    value="invoice-ocr-mcp"
                )
            with gr.Column(scale=1):
                connect_btn = gr.Button("Connect")
        
        status = gr.Textbox(label="Connection Status", interactive=False)
        
        chatbot = gr.Chatbot(
            value=[], 
            height=500,
            type="messages",
            show_copy_button=True,
            avatar_images=("👤", "🤖")
        )
        
        with gr.Row(equal_height=True):
            msg = gr.Textbox(
                label="Your Question",
                placeholder="Ask about weather or alerts (e.g., What's the weather in New York?)",
                scale=4
            )
            clear_btn = gr.Button("Clear Chat", scale=1)
        
        connect_btn.click(client.connect, inputs=server_path, outputs=status, api_name="connect")
        msg.submit(client.process_message, [msg, chatbot], [chatbot, msg])
        clear_btn.click(lambda: [], None, chatbot)
        
    return demo

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.get_event_loop_policy().set_child_watcher(asyncio.SafeChildWatcher())
    except Exception as e:
        print(f"Failed to set SafeChildWatcher: {e}")
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not found in environment. Please set it in your .env file.")
    
    interface = gradio_interface()
    interface.launch(debug=True)
