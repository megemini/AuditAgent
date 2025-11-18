---
domain: multi-modal
tags:
- financial reimbursement
- intelligent audit
- invoice recognition
- large language model
- MCP
datasets:
  evaluation:
  test:
  train:
models:
license: Apache License 2.0
---

#### Clone with HTTP
```bash
 git clone https://github.com/megemini/AuditAgent.git
```

**🌐 Language / 语言**: [English](README_EN.md) | [中文](README.md)

# Financial Reimbursement Intelligent Agent (AuditAgent)

![step1](doc/step1.png)

## 📋 Project Overview

The Financial Reimbursement Intelligent Agent is an AI-powered assistant based on large language models, designed to help enterprise employees quickly understand financial reimbursement policies, audit reimbursement materials, and improve reimbursement efficiency. The system integrates various advanced technologies including natural language processing, optical character recognition (OCR), Model Context Protocol (MCP), and more, providing comprehensive financial reimbursement services to users.

### 🎯 Core Features

1. **Intelligent Rule Extraction**: Automatically extract financial reimbursement rules from various document formats (PDF, Word, TXT)
2. **Intelligent Invoice Recognition**: Use advanced OCR technology and large language models to recognize invoice information
3. **Intelligent Audit Process**: Validate and audit invoices based on extracted rules with step-by-step verification
4. **Multi-tool Collaboration**: Integrate multiple MCP servers providing professional functions such as city tier queries, date-time calculations
5. **Streaming Interaction**: Support real-time streaming output for a smooth user experience

## 🏗️ System Architecture

### Overall Architecture

```
┌─────────────────────────────────────────────────────────────┐
│            Financial Reimbursement Intelligent Agent        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Settings   │  │ Knowledge   │  │  MCP Server │         │
│  │  (Step 1)   │  │  Base       │  │ Management  │         │
│  │             │  │  (Step 2)   │  │  (Step 3)   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                Intelligent Q&A                     │   │
│  │                   (Step 4)                          │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server Layer                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │City Tier    │  │Invoice OCR  │  │Date-Time   │         │
│  │Server       │  │Server       │  │Server      │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                Large Language Model Layer                   │
├─────────────────────────────────────────────────────────────┤
│                OpenAI API / Local LLM                       │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

- **Frontend Interface**: Gradio - Provides intuitive web user interface
- **Large Language Model**: Supports OpenAI API compatible models (e.g., Qwen series)
- **MCP Protocol**: FastMCP - Implements tool calling and server communication
- **OCR Technology**: PaddleOCR - Used for invoice text extraction
- **Document Processing**: PyMuPDF (PDF), python-docx (Word)
- **Async Processing**: asyncio - Supports efficient asynchronous operations
- **File Service**: Built-in HTTP file server

### Core Components

#### 1. Main Application (app.py)
- Provides complete Gradio user interface
- Implements session management and state persistence
- Integrates all MCP server clients
- Handles file upload and rule extraction
- Implements streaming intelligent Q&A functionality

#### 2. MCP Server Layer

**City Tier Server (mcp_citytier_stdio.py)**
- Based on latest city tier classification data
- Supports single city query, batch queries
- Provides tier-based city list functionality
- Covers first to fifth tier city data

**Invoice Recognition Server (mcp_invoice_stdio.py)**
- Integrates PaddleOCR for text extraction
- Uses large language models for intelligent field parsing
- Supports multiple invoice formats and types
- Provides high-precision invoice information recognition

**Date-Time Server (mcp_datetime_stdio.py)**
- Provides comprehensive date-time functionality
- Supports multi-timezone queries
- Implements date calculation and formatting
- Supports date difference calculation

#### 3. Invoice Processing Core (invoice_core_llm.py)
- Implements LLM-based invoice information extraction
- Integrates OCR technology and AI analysis
- Provides structured invoice field output
- Supports multi-language invoice processing

## 🚀 Core Features

### 1. Intelligent Rule Extraction
- **Multi-format Support**: Supports TXT, PDF, DOCX, DOC and other document formats
- **Automatic Parsing**: Uses large language models to automatically identify and extract reimbursement rules
- **Structured Output**: Converts rules to JSON format for easy subsequent processing
- **Built-in Examples**: Provides complete financial reimbursement rule examples

### 2. Intelligent Invoice Recognition
- **Multi-format Processing**: Supports image files (JPG, PNG, etc.) and PDF documents
- **High-precision OCR**: Uses PaddleOCR for accurate text extraction
- **AI-driven Analysis**: Utilizes large models for intelligent field extraction and validation
- **Privacy Protection**: All processing is done locally to ensure data security

### 3. Intelligent Audit Process
- **Step-by-step Validation**: Systematically validates each reimbursement rule one by one
- **Multi-tool Collaboration**: Calls appropriate MCP tools as needed
- **Real-time Feedback**: Provides immediate results after validating each rule
- **Comprehensive Report**: Generates detailed audit reports and improvement suggestions

### 4. Streaming Interactive Experience
- **Real-time Output**: Supports streaming output for instant user feedback
- **Status Indicators**: Clearly shows AI thinking, tool calling and other states
- **Error Handling**: Comprehensive error handling and user prompts
- **Session Persistence**: Supports multi-turn conversations and context maintenance

## 📝 User Guide

### System Requirements

- Python 3.10+
- Operating System: Windows/Linux/macOS
- Memory: Recommended 8GB or more
- Network Connection: Required for accessing large language model APIs

### Installation Steps

1. **Clone the Project**
```bash
git clone https://github.com/megemini/AuditAgent.git
cd AuditAgent
```

2. **Create Virtual Environment**
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
```

### Usage Process

#### Step 1: Settings
1. Configure OpenAI API key
2. Set API base URL
3. Select the model to use
4. Test connection to ensure configuration is correct

#### Step 2: Knowledge Base
1. Upload financial reimbursement rule documents (supports TXT, PDF, DOCX formats)
2. Or use built-in example documents
3. System automatically extracts rules and converts them to JSON format
4. View extracted rules to confirm accuracy

#### Step 3: MCP Server Management
1. Connect to city tier query server
2. Connect to invoice OCR LLM server
3. Connect to date-time server
4. Confirm all server connection statuses are normal

#### Step 4: Intelligent Q&A
1. Enter financial reimbursement related questions
2. Optionally upload invoice images or PDF files
3. System performs intelligent analysis and audit based on rules
4. Receive detailed audit reports and suggestions

### Usage Examples

#### Example 1: Querying Reimbursement Standards
```
User: What are the accommodation standards for travel expenses?

System: According to financial reimbursement rules, travel expense accommodation standards vary by city tier:
- First-tier cities: 600 RMB/night
- Second-tier cities: 500 RMB/night
- Other regions: 400 RMB/night uniformly
```

#### Example 2: Invoice Audit
```
User: [Uploads hotel invoice image from Beijing]
User: Please audit this invoice

System: I will conduct a detailed audit of this invoice...

Step 1: Invoice Recognition
→ Using recognize_single_invoice tool to identify invoice information
→ Extracted information: Amount 580 RMB, Date 2025-08-20, City Beijing

Step 2: Rule-by-Rule Validation
Validating Rule 1: Travel Expense Accommodation Standard
→ Need to query city tier → Calling query_city_tier tool
→ Validation result: ✅ Compliant
→ Detailed explanation: Beijing is a first-tier city, accommodation standard is 600 RMB/night, invoice amount 580 RMB does not exceed standard

Step 3: Summary Audit Results
📋 Invoice Audit Report
📊 Rule Validation Results:
- ✅ Compliant with Rule 1: Travel Expense Accommodation Standard
📈 Audit Statistics:
- Total rules: 1
- Compliant rules: 1
- Non-compliant rules: 0
🎯 Final Conclusion: Invoice audit passed
```

## 🔧 Advanced Features

### 1. MCP Tool Calling System

The system integrates multiple MCP servers, providing rich tool calling capabilities:

**City Tier Tools**
- `query_city_tier`: Query single city tier
- `query_multiple_cities`: Batch query multiple city tiers
- `get_tier_cities`: Get city list by tier

**Invoice Recognition Tools**
- `recognize_single_invoice`: Recognize single invoice
- `recognize_multiple_invoices`: Batch recognize multiple invoices
- `get_invoice_template_info`: Get supported invoice template information

**Date-Time Tools**
- `get_current_date`: Get current date
- `get_current_time`: Get current time
- `get_current_datetime`: Get current date-time
- `get_datetime_by_timezone`: Get date-time for specified timezone
- `calculate_date_difference`: Calculate date difference
- `add_days_to_date`: Add/subtract days from date

### 2. Streaming Output Mechanism

The system implements advanced streaming output mechanism, providing the following features:

- **Real-time Status Display**: Shows AI thinking, tool calling and other states
- **Step-by-step Results**: Displays rule validation results progressively
- **Error Handling**: Comprehensive error prompts and recovery mechanisms
- **Session Management**: Supports multi-turn conversations and context maintenance

### 3. File Processing System

- **Multi-format Support**: Supports TXT, PDF, DOCX, DOC, JPG, PNG and other formats
- **Automatic Cleanup**: Automatically cleans up files not uploaded on the current day
- **Secure Access**: Built-in file server ensures secure file access
- **Temporary Files**: Intelligent temporary file management

### 4. Session Management System

- **Session Isolation**: Each user session is independent, data does not interfere
- **State Persistence**: Maintains API configuration, extracted rules and other session states
- **Secure Storage**: Sensitive information like API keys is stored securely
- **Automatic Cleanup**: Intelligent session lifecycle management

## 🔒 Security and Privacy

### Data Security
- **Local Processing**: All file processing is done locally
- **Temporary Files**: Uploaded files are automatically cleaned up regularly
- **Access Control**: Built-in file server provides secure file access
- **Session Isolation**: User data is strictly isolated

### API Security
- **Key Management**: API keys are stored securely and not exposed to frontend
- **Session Binding**: API configuration is bound to sessions, preventing cross-session access
- **Encrypted Transmission**: All API calls use HTTPS encrypted transmission

### Privacy Protection
- **No Data Retention**: No user data is retained after processing
- **Anonymous Processing**: No personal user information is collected
- **Local Deployment Option**: Supports complete localization deployment

## 🌟 Advantages and Value

### Technical Advantages
1. **Advanced Architecture**: Modular architecture based on MCP protocol, easy to extend
2. **Multi-modal Processing**: Supports text, images, PDF and other formats
3. **Intelligent Integration**: Seamless integration of large language models and professional tools
4. **Streaming Interaction**: Provides smooth real-time user experience

### Business Value
1. **Improved Efficiency**: Automated reimbursement audit, significantly improves processing speed
2. **Cost Reduction**: Reduces manual audit costs and error rates
3. **Standardization**: Ensures consistency and standardization of reimbursement audits
4. **Compliance**: Rule-based audit ensures compliance requirements

### User Experience
1. **Easy to Use**: Intuitive four-step operation process
2. **Real-time Feedback**: Instant audit results and status display
3. **Intelligent Prompts**: Intelligent error prompts and operation guidance
4. **Multi-turn Dialogue**: Supports continuous Q&A and interaction

## 🏢 Local Deployment Information

This intelligent agent can be completely deployed locally and connected to local large language models, ensuring data security and privacy protection. For convenience of demonstration and quick experience, the current version has been modified to adapt to remote server configuration.

### Local Deployment Advantages
- **Data Security**: All data processing is done locally, sensitive financial information does not leave the enterprise network
- **Privacy Protection**: No need to transmit data to external servers, fully complying with data protection regulatory requirements
- **Offline Operation**: Supports complete offline operation without relying on external network connections
- **Customization**: Can be deeply customized and optimized according to specific enterprise needs
- **Cost Control**: Lower long-term usage costs, no need to pay API call fees

### Local Deployment Requirements
- Local large language model services (such as Ollama, LocalAI, etc.)
- Sufficient hardware resources (GPU recommended for model inference)
- Local file storage and processing capabilities
- Enterprise internal network environment

**Demo Note**: The current demo version uses remote server configuration for quick experience. In actual production environments, local deployment is recommended to ensure data security and compliance.

---

**Disclaimer**: The financial reimbursement rules and audit functions provided by this project are for reference and learning purposes only and do not constitute any legal or financial advice. Actual financial reimbursement systems should be customized according to specific company situations, industry characteristics and local laws and regulations. Before using this system, please consult professional financial and legal advisors.