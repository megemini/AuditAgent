# 发票OCR识别错误修复说明

## 问题描述

在使用发票OCR识别功能时，出现以下错误：

1. **文件访问错误**：
```
发票识别失败: 404 Client Error: Not Found for url: http://localhost:7860/upload_files/cefacc6b-e137-4aea-9074-deb5b09aa593_trip_02.jpg
```

2. **参数错误**：
```
Error calling tool 'recognize_single_invoice': 1 validation error for call[recognize_single_invoice]
image_path
  Unexpected keyword argument [type=unexpected_keyword_argument]
```

## 问题原因

根据 [Gradio文件上传MCP文档](https://www.gradio.app/guides/file-upload-mcp) 和 OCR工具源码分析，存在以下问题：

1. **跨服务器文件访问问题**：
   - Gradio应用运行在端口 7860
   - OCR服务器运行在端口 8081
   - OCR服务器无法访问 `http://localhost:7860/upload_files/` 路径下的文件

2. **MCP服务器隔离**：
   - 不同的MCP服务器运行在不同的进程中
   - 它们无法直接访问彼此的文件系统

3. **OCR工具参数限制**：
   - `recognize_single_invoice` 工具只接受两个参数：
     - `image_url: str` - 图像的URL
     - `image_data: str` - base64编码的图像数据
   - 不支持 `image_path` 等其他参数

## 解决方案

### 1. 添加独立文件服务器

在 `app.py` 中添加了一个独立的HTTP文件服务器：

```python
def start_file_server(port=8888):
    """启动一个简单的HTTP文件服务器来提供上传文件的访问"""
    # 在端口8888启动文件服务器，专门服务upload_files目录
```

### 2. 多种文件访问方式

修改了图片处理逻辑，提供多种文件访问方式：

- **文件服务器URL**: `http://localhost:8888/filename.jpg` (推荐)
- **本地文件路径**: `/path/to/upload_files/filename.jpg`
- **Base64数据**: 直接嵌入图片数据
- **Gradio URL**: `http://localhost:7860/upload_files/filename.jpg` (备用)

### 3. 智能参数处理

在工具调用时，自动处理图片参数，确保只传递OCR工具支持的参数：

```python
# 特殊处理发票识别工具的图片参数
if name == "recognize_single_invoice":
    # 自动转换为可访问的URL
    args["image_url"] = file_server_url      # 主要方式
    args["image_data"] = img_base64          # 备用方式

    # 确保只传递OCR工具支持的参数（image_url 和 image_data）
    valid_args = {}
    if "image_url" in args:
        valid_args["image_url"] = args["image_url"]
    if "image_data" in args:
        valid_args["image_data"] = args["image_data"]
    args = valid_args
```

## 修改的文件

### app.py 主要修改：

1. **导入新模块**：
   ```python
   import threading
   import http.server
   import socketserver
   ```

2. **添加文件服务器函数**：
   - `start_file_server(port=8888)`

3. **修改图片处理逻辑**：
   - 生成多种格式的图片访问方式
   - 优先使用文件服务器URL

4. **增强工具调用处理**：
   - 自动转换图片URL为可访问格式
   - 提供多种备用参数

5. **应用启动时启动文件服务器**：
   ```python
   file_server_base_url = start_file_server(8888)
   ```

## 使用说明

### 启动应用

```bash
python app.py
```

应用启动后会自动：
1. 创建 `upload_files` 目录
2. 启动文件服务器在端口 8888
3. 启动Gradio应用在端口 7860

### 测试文件服务器

运行测试脚本：

```bash
python test_file_server.py
```

### 测试OCR工具参数

运行OCR参数测试脚本：

```bash
python test_ocr_params.py
```

这个脚本会验证：
- OCR服务器连接状态
- 文件服务器访问能力
- OCR工具参数的正确性

### 端口使用

- **7860**: Gradio主应用
- **8080**: 城市分级查询MCP服务器
- **8081**: 发票OCR识别MCP服务器
- **8888**: 文件服务器 (新增)

## 验证修复

1. **上传图片**：在Gradio界面上传发票图片
2. **查看日志**：检查是否生成了正确的文件服务器URL
3. **OCR识别**：确认OCR服务器能够访问图片文件
4. **结果检查**：验证发票识别结果是否正常返回

## 注意事项

1. **防火墙设置**：确保端口8888没有被防火墙阻止
2. **文件权限**：确保upload_files目录有正确的读写权限
3. **网络访问**：如果OCR服务器在不同机器上，需要使用实际IP地址而不是localhost

## 故障排除

如果仍然出现问题：

1. **检查端口占用**：
   ```bash
   netstat -an | grep 8888
   ```

2. **手动测试文件访问**：
   ```bash
   curl http://localhost:8888/your-image-file.jpg
   ```

3. **查看应用日志**：检查文件服务器启动和图片处理的日志信息

4. **运行测试脚本**：使用 `test_file_server.py` 验证配置
