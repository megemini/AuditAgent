import gradio as gr
import asyncio
import json
import threading
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import anyio
from contextlib import AsyncExitStack
import sys

class MCPServerManager:
    def __init__(self):
        self.session = None
        self.exit_stack = AsyncExitStack()
        # 使用当前线程的事件循环，如果不存在则创建一个新的
        try:
            self.loop = asyncio.get_event_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            # 设置子进程观察器
            if sys.platform == 'win32':
                asyncio.set_event_loop(self.loop)
            else:
                # 在Unix系统上设置子进程观察器
                try:
                    asyncio.get_child_watcher()
                except (NotImplementedError, AttributeError):
                    # 如果不支持子进程观察器，使用线程安全的方式
                    pass
        self.is_connected = False
        
    def connect(self, server_path, args=None):
        """连接到MCP服务器"""
        # 如果已经有连接，先断开
        if self.is_connected:
            self.disconnect()
        
        # 解析参数
        server_params = StdioServerParameters(
            command=server_path,
            args=args.split() if args else []
        )
        
        # 在新的线程中运行异步连接
        try:
            # 检查事件循环是否在当前线程中运行
            if self.loop.is_running():
                # 如果事件循环正在运行，使用线程池执行
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_in_thread, self._connect, server_params)
                    result = future.result(timeout=30)  # 30秒超时
            else:
                # 如果事件循环没有运行，直接执行
                result = self.loop.run_until_complete(self._connect(server_params))
            
            self.is_connected = True
            return result
        except Exception as e:
            return f"连接失败: {str(e)}"
    
    def _run_in_thread(self, coro, *args):
        """在线程中运行协程"""
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(coro(*args))
            return result
        finally:
            loop.close()

    
    async def _connect(self, server_params):
        """异步连接MCP服务器"""
        try:
            # 创建stdio客户端连接
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            
            # 创建会话
            self.session = await self.exit_stack.enter_async_context(
                ClientSession(stdio_transport[0], stdio_transport[1])
            )
            
            # 初始化会话
            await self.session.initialize()
            
            return f"成功连接到MCP服务器: {server_params.command}"
            
        except Exception as e:
            await self.exit_stack.aclose()
            raise e
    
    def disconnect(self):
        """断开MCP服务器连接"""
        try:
            if self.session:
                if self.loop.is_running():
                    # 如果事件循环正在运行，使用线程池执行
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(self._run_in_thread, self._disconnect)
                        future.result(timeout=10)  # 10秒超时
                else:
                    # 如果事件循环没有运行，直接执行
                    self.loop.run_until_complete(self._disconnect())
            self.is_connected = False
            return "已断开MCP服务器连接"
        except Exception as e:
            return f"断开连接失败: {str(e)}"
    
    async def _disconnect(self):
        """异步断开连接"""
        await self.exit_stack.aclose()
        self.session = None
    
    def send_request(self, method, params_json):
        """发送请求到MCP服务器"""
        if not self.is_connected or not self.session:
            return "错误: 未连接到MCP服务器"
        
        try:
            # 解析参数
            params = json.loads(params_json) if params_json else {}
            
            # 根据方法选择对应的协程
            if method == "list_resources":
                coro = self._list_resources()
            elif method == "read_resource":
                coro = self._read_resource(params)
            elif method == "list_tools":
                coro = self._list_tools()
            elif method == "call_tool":
                coro = self._call_tool(params)
            elif method == "list_prompts":
                coro = self._list_prompts()
            elif method == "get_prompt":
                coro = self._get_prompt(params)
            else:
                return f"未知方法: {method}"
            
            # 执行协程
            if self.loop.is_running():
                # 如果事件循环正在运行，使用线程池执行
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(self._run_in_thread, lambda: coro)
                    result = future.result(timeout=30)  # 30秒超时
            else:
                # 如果事件循环没有运行，直接执行
                result = self.loop.run_until_complete(coro)
                
            return f"请求: {method}\n\n响应: {json.dumps(result, indent=2, ensure_ascii=False)}"
            
        except json.JSONDecodeError:
            return "错误: 参数必须是有效的JSON格式"
        except Exception as e:
            return f"请求失败: {str(e)}"
    
    async def _list_resources(self):
        """列出资源"""
        resources = []
        async for resource in self.session.list_resources():
            resources.append(resource)
        return resources
    
    async def _read_resource(self, params):
        """读取资源"""
        uri = params.get("uri", "")
        if not uri:
            return "错误: 需要提供uri参数"
        
        result = await self.session.read_resource(uri)
        return {
            "uri": uri,
            "contents": result.contents,
            "mimeType": getattr(result, 'mimeType', 'text/plain')
        }
    
    async def _list_tools(self):
        """列出工具"""
        tools = []
        async for tool in self.session.list_tools():
            tools.append(tool)
        return tools
    
    async def _call_tool(self, params):
        """调用工具"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        if not name:
            return "错误: 需要提供name参数"
        
        result = await self.session.call_tool(name, arguments)
        return {
            "name": name,
            "content": result.content,
            "isError": result.isError
        }
    
    async def _list_prompts(self):
        """列出提示"""
        prompts = []
        async for prompt in self.session.list_prompts():
            prompts.append(prompt)
        return prompts
    
    async def _get_prompt(self, params):
        """获取提示"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        
        if not name:
            return "错误: 需要提供name参数"
        
        result = await self.session.get_prompt(name, arguments)
        return {
            "name": name,
            "description": result.description,
            "messages": result.messages
        }

# 创建MCP服务器管理器实例
mcp_manager = MCPServerManager()

# Gradio界面函数
def start_mcp_server(server_path, args):
    """启动MCP服务器"""
    if not server_path:
        return "请提供服务器路径"
    
    result = mcp_manager.connect(server_path, args)
    return result

def stop_mcp_server():
    """停止MCP服务器"""
    result = mcp_manager.disconnect()
    return result

def send_mcp_request(method, params_json):
    """发送请求到MCP服务器"""
    return mcp_manager.send_request(method, params_json)

def get_server_status():
    """获取服务器状态"""
    return "已连接" if mcp_manager.is_connected else "未连接"

# 创建Gradio界面
with gr.Blocks(title="MCP服务器客户端") as demo:
    gr.Markdown("# MCP服务器标准输入输出接口")
    gr.Markdown("使用官方MCP库连接Stdio服务器")
    
    with gr.Row():
        status = gr.Textbox(label="连接状态", value=get_server_status, every=1)
    
    with gr.Tab("服务器管理"):
        gr.Markdown("## 启动和停止MCP服务器")
        
        with gr.Row():
            server_path = gr.Textbox(
                label="服务器路径",
                placeholder="输入MCP服务器的可执行文件路径",
                value="python"  # 默认值
            )
            server_args = gr.Textbox(
                label="参数",
                placeholder="可选的命令行参数",
                value="-m mcp.server"  # 示例参数
            )
        
        with gr.Row():
            start_btn = gr.Button("启动服务器", variant="primary")
            stop_btn = gr.Button("停止服务器", variant="stop")
        
        server_output = gr.Textbox(label="服务器状态", lines=3, interactive=False)
    
    with gr.Tab("发送请求"):
        gr.Markdown("## 向MCP服务器发送请求")
        
        with gr.Row():
            method = gr.Dropdown(
                label="方法名",
                choices=[
                    "list_resources", 
                    "read_resource", 
                    "list_tools", 
                    "call_tool",
                    "list_prompts",
                    "get_prompt"
                ],
                value="list_resources"
            )
        
        params = gr.Textbox(
            label="参数 (JSON格式)",
            placeholder='{"uri": "file:///example.txt"} 或 {"name": "tool_name", "arguments": {}}',
            value='{}',
            lines=3
        )
        
        send_btn = gr.Button("发送请求", variant="primary")
        request_output = gr.Textbox(label="响应", lines=10, interactive=False)
    
    with gr.Tab("示例"):
        gr.Markdown("## 示例请求")
        
        examples = gr.Examples(
            examples=[
                ["list_resources", '{}'],
                ["read_resource", '{"uri": "file:///example.txt"}'],
                ["list_tools", '{}'],
                ["call_tool", '{"name": "example_tool", "arguments": {"param1": "value1"}}'],
                ["list_prompts", '{}'],
                ["get_prompt", '{"name": "example_prompt", "arguments": {}}']
            ],
            inputs=[method, params],
            label="点击填充示例请求"
        )
    
    with gr.Tab("帮助"):
        gr.Markdown("""
        ## MCP服务器使用指南
        
        ### 支持的请求方法：
        - **list_resources**: 列出所有可用资源
        - **read_resource**: 读取特定资源内容
        - **list_tools**: 列出所有可用工具
        - **call_tool**: 调用特定工具
        - **list_prompts**: 列出所有可用提示
        - **get_prompt**: 获取特定提示
        
        ### 参数格式：
        参数必须是有效的JSON格式，例如：
        ```json
        {"uri": "file:///example.txt"}
        ```
        或
        ```json
        {"name": "tool_name", "arguments": {"param1": "value1"}}
        ```
        
        ### 常见MCP服务器：
        - 文件系统服务器: `python -m mcp.server.filesystem`
        - 时钟服务器: `python -m mcp.server.clock`
        - 随机数服务器: `python -m mcp.server.random`
        """)
    
    # 连接事件处理
    start_btn.click(
        fn=start_mcp_server,
        inputs=[server_path, server_args],
        outputs=server_output
    )
    
    stop_btn.click(
        fn=stop_mcp_server,
        outputs=server_output
    )
    
    send_btn.click(
        fn=send_mcp_request,
        inputs=[method, params],
        outputs=request_output
    )

# 清理资源
import atexit
@atexit.register
def cleanup():
    if mcp_manager.is_connected:
        mcp_manager.disconnect()
    if mcp_manager.loop and not mcp_manager.loop.is_closed():
        mcp_manager.loop.close()

# 启动应用
if __name__ == "__main__":
    try:
        demo.launch(server_name="0.0.0.0", server_port=7860)
    finally:
        cleanup()