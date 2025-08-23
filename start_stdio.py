#!/usr/bin/env python3
"""
启动stdio版本的智能助手系统
自动连接MCP服务器
"""

import asyncio
import time
import logging
import os
from app_stdio import client, gradio_app, CITY_SERVER_COMMAND, INVOICE_OCR_SERVER_COMMAND, start_file_server

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def auto_connect_servers():
    """自动连接MCP服务器"""
    logger.info("开始自动连接MCP服务器...")
    
    # 连接城市分级查询服务器
    try:
        result = client.connect(CITY_SERVER_COMMAND, "city_server_stdio")
        logger.info(f"城市分级查询服务器连接结果: {result}")
    except Exception as e:
        logger.error(f"连接城市分级查询服务器失败: {e}")
    
    # 等待一下再连接下一个服务器
    time.sleep(1)
    
    # 连接发票OCR识别服务器
    try:
        result = client.connect(INVOICE_OCR_SERVER_COMMAND, "ocr_server_stdio")
        logger.info(f"发票OCR识别服务器连接结果: {result}")
    except Exception as e:
        logger.error(f"连接发票OCR识别服务器失败: {e}")
    
    # 显示连接状态
    connected_servers = client.connected_servers
    if connected_servers:
        logger.info(f"✅ 已连接的服务器: {', '.join(connected_servers)}")
        
        # 显示可用工具
        all_tools = client.get_all_tools()
        if all_tools:
            tool_names = [tool['function']['name'] for tool in all_tools]
            logger.info(f"🔧 可用工具: {', '.join(tool_names)}")
        else:
            logger.warning("⚠️  没有可用的工具")
    else:
        logger.warning("❌ 没有连接到任何服务器")

def main():
    """主函数"""
    print("🚀 启动智能助手系统 - stdio版本")
    print("=" * 50)

    # 确保 upload_files 目录存在
    os.makedirs(os.path.join(os.getcwd(), "upload_files"), exist_ok=True)

    # 启动文件服务器
    file_server_base_url = start_file_server(8889)
    logger.info(f"文件服务器已启动: {file_server_base_url}")

    # 等待文件服务器启动
    time.sleep(2)

    # 自动连接服务器
    auto_connect_servers()

    print("\n" + "=" * 50)
    print("🌐 启动Gradio应用...")
    print("📍 应用地址: http://localhost:7861")
    print("📁 文件服务器: http://localhost:8889")
    print("💡 提示: 如果服务器连接失败，可以在设置页面手动连接")
    print("=" * 50)

    # 启动Gradio应用
    demo = gradio_app()
    demo.launch(
        debug=True,
        server_port=7861,
        allowed_paths=["upload_files"],
        share=False,
        inbrowser=True  # 自动打开浏览器
    )

if __name__ == "__main__":
    main()
