import asyncio
import os
import sys
from pathlib import Path
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

async def main():
    # 使用 StdioServerParameters 对象
    server_params = StdioServerParameters(
        command="python",
        args=[os.path.abspath("invoice_ocr_mcp/src/invoice_ocr_mcp/server.py")]
    )
    
    # 使用正确的方式调用 stdio_client
    async with stdio_client(server_params) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            
            # 识别单张发票
            result = await session.call_tool(
                "recognize_single_invoice",
                {
                    "image_data": "base64_encoded_image_data",
                    "output_format": "standard"
                }
            )
            print("识别结果:", result)

if __name__ == "__main__":
    asyncio.run(main())