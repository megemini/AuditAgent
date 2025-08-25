import gradio as gr
import openai
import os
import json
from typing import List, Dict, Any
import tempfile
import fitz  # PyMuPDF
from docx import Document
from uuid import uuid4

# 会话存储（模拟）
session_store = {}

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

def answer_question_with_session(question, history, session_id: str):
    """Answer user's question based on reimbursement rules using session client"""
    if not question.strip():
        return "", history
    
    session_data = session_store.get(session_id, {})
    client = session_data.get("client")
    model = session_data.get("model")
    reimbursement_rules = session_data.get("reimbursement_rules", [])
    
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
        
        # Create prompt for answering questions
        prompt = f"""
        你是一个财务报销专家，请基于以下财务报销规则回答用户的问题。
        
        财务报销规则：
        {rules_context}
        
        用户问题：{question}
        
        请提供准确、详细的回答，并引用相关的规则。
        """
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            extra_body={
                "enable_thinking": False
            }
        )
        
        answer = response.choices[0].message.content
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
                
                # Step 3: Agent Tab
                with gr.TabItem("Step 3: 智能体"):
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
                    placeholder="请输入 OpenAI API 的 Base URL (例如: https://api.openai.com/v1)"
                )
                
                model_input = gr.Textbox(
                    label="Model",
                    placeholder="请输入模型名称 (例如: gpt-3.5-turbo)"
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
    
    def setup_agent_tab(self, session_id):
        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("## 智能问答")
                
                question_input = gr.Textbox(
                    label="请输入您的问题",
                    placeholder="例如: 差旅费的报销标准是什么？"
                )
                
                ask_btn = gr.Button("提问", variant="primary")
                
                clear_chat_btn = gr.Button("清空对话")
            
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
            inputs=[question_input, chatbot, session_id],
            outputs=[question_input, chatbot]
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
    app = AuditAgentApp()
    app.launch()