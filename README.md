# CompeteMAS (Competition Multi-Agent System)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/package%20manager-uv-orange.svg)](https://docs.astral.sh/uv/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository contains the supplementary code for NeurIPS 2025 paper under review: **"CompeteMAS: Cost-Aware Evaluation of Agentic Coding Capabilities of Multi-Agent Systems"**, and is for review only.

CompeteMAS is a comprehensive Online Judge (OJ) system designed to evaluate the coding capabilities of Multi-Agent Systems (MAS) in competitive programming environments. It features cost-aware evaluation, real-time competition management, and integration with modern LLM APIs.

## 🚀 Features

- **🏆 Multi-Agent Competition**: Support for multiple LLM agents competing simultaneously
- **💰 Cost-Aware Evaluation**: Token-based resource management and cost tracking
- **⚡ Real-time API**: RESTful API for competition management and monitoring
- **🔍 Intelligent Hints**: Multi-level hint system with semantic and episodic knowledge
- **📊 Comprehensive Analytics**: Detailed scoring, rankings, and performance metrics
- **🐳 Container Ready**: Docker support for easy deployment
- **🛡️ Secure Execution**: Sandboxed code execution via Rust-based judge

## 📋 Prerequisites

- **Python 3.10+**
- **uv** (recommended package manager)
- **Rust & Cargo** (for online judge)
- **Docker** (for containerized deployment)

## 🛠️ Installation

### 1. Clone the Repository
   ```bash
git clone <repository-url>
cd CompeteMAS
   ```

### 2. Install with uv (Recommended)
   ```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

### 3. Prepare USACO Dataset

   Download the USACO data from the [link](https://drive.google.com/file/d/1z5ODOJMqyer1QxzYtEUZ2hbAx-7nU8Vi/view?usp=share_link) provided by [USACO Bench](https://github.com/princeton-nlp/USACO).

```bash
# Extract and place in data directory
unzip usaco_data.zip
mv data_copy data/datasets/usaco_2025
```

## 🔧 Online Judge Setup

**Note**: The online judge system is based on the [online-judge-rust](https://github.com/cpinitiative/online-judge-rust) project. This is a third-party codebase and is not included in this repository.

### 1. Get Online Judge Rust
   ```bash
# Clone the online judge repository
   git clone https://github.com/cpinitiative/online-judge-rust.git
   ```

### 2. Install Rust Dependencies
   ```bash
# Install cargo-lambda
cargo install cargo-lambda
cargo lambda --help  # Verify installation

# Install zig (for cross-compilation)
sudo snap install zig --classic --beta
zig version  # Verify installation
   ```

### 3. Build and Run Online Judge
   ```bash
# Build the Lambda function
   cargo lambda build

# Build Docker image
   docker build --platform linux/amd64 -t oj-rust .

# Run the online judge
   docker run --platform linux/amd64 -p 9000:8080 oj-rust
   ```

### 4. Test Online Judge
   ```bash
   curl -X POST "http://localhost:9000/2015-03-31/functions/function/invocations" \
   -d '{
      "version": "2.0",
      "rawPath": "/compile-and-execute",
      "requestContext": {
         "http": {
         "method": "POST",
         "path": "/compile-and-execute"
         }
      },
      "headers": {
         "Content-Type": "application/json"
      },
      "body": "{\"compile\":{\"source_code\":\"#include <iostream>\\nusing namespace std;\\n\\nint main() {\\n  int a, b;\\n  cin >> a >> b;\\n  cout << a + b << endl;\\n  return 0;\\n}\",\"compiler_options\":\"-O2 -std=c++17\",\"language\":\"cpp\"},\"execute\":{\"stdin\":\"5 7\",\"timeout_ms\":5000}}",
      "isBase64Encoded": false
   }'
   ```

**Important**: Make sure the online judge is running on port 9000 before starting CompeteMAS competitions.

## 🎯 Usage

### Quick Start

1. **Start the API Server**
   ```bash
   uv run competemas --host 0.0.0.0 --port 5000
   ```

2. **Configure Competitors**
   Edit `config/competitors_config.json`:
   ```json
   {
     "competitors": [
       {
         "name": "gpt-4",
         "model_id": "gpt-4",
         "api_base": "https://api.openai.com/v1",
         "api_key": "your-api-key",
         "max_tokens": 100000
       }
     ]
   }
   ```

3. **Run Competition**
   ```bash
   uv run competemas_run
   ```

### API Usage

The system provides a comprehensive REST API:

```bash
# List competitions
curl http://localhost:5000/api/competitions

# Create competition
curl -X POST http://localhost:5000/api/competitions \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Competition",
    "description": "A test competition",
    "problem_ids": ["1323_bronze_feb"],
    "max_tokens_per_participant": 100000
  }'

# Get competition details
curl http://localhost:5000/api/competitions/{competition_id}

# View rankings
curl http://localhost:5000/api/competitions/{competition_id}/rankings
```

## 🏗️ Architecture

```
CompeteMAS/
├── 📁 src/                          # 源代码目录
│   └── 📁 competemas/               # 主包
│       ├── 📄 __init__.py           # 包初始化
│       ├── 📄 main.py               # 主程序入口
│       ├── 📁 api/                  # API服务模块
│       │   ├── 📄 __init__.py       # API模块初始化
│       │   └── 📄 server.py         # Flask API服务器
│       ├── 📁 cli/                  # 命令行工具模块
│       │   ├── 📄 __init__.py       # CLI模块初始化
│       │   └── 📄 run_competition.py # 竞赛运行工具
│       ├── 📁 core/                 # 核心业务逻辑
│       │   ├── 📄 __init__.py       # 核心模块初始化
│       │   ├── 📄 agents.py         # 智能体实现
│       │   ├── 📄 competition.py    # 竞赛管理逻辑
│       │   ├── 📄 judge.py          # 评测系统
│       │   ├── 📄 models.py         # 数据模型
│       │   └── 📄 storage.py        # 数据存储
│       └── 📁 utils/                # 工具函数模块
│           ├── 📄 __init__.py       # 工具模块初始化
│           ├── 📄 conversation_logger.py # 对话日志工具
│           ├── 📄 problem_loader.py # 问题加载器
│           └── 📄 prompts.py        # 提示词管理
├── 📁 config/                       # 配置文件目录
│   ├── 📄 all_problems.json        # 所有问题配置
│   ├── 📄 competition_config.json  # 竞赛配置
│   ├── 📄 competitors_config.json  # 参赛者配置
│   ├── 📄 problem_ids.json         # 问题ID列表
│   └── 📄 prompts.json             # 提示词配置
├── 📁 data/                         # 数据目录
│   ├── 📁 competitions/            # 竞赛数据
│   ├── 📁 corpuses/                # 语料库数据
│   ├── 📁 datasets/                # 数据集
│   ├── 📁 datasets_original/       # 原始数据集
│   └── 📁 submissions/             # 提交记录
├── 📁 logs/                         # 日志目录
├── 📁 tests/                        # 测试代码目录
├── 📄 pyproject.toml               # uv项目配置
└── 📄 README.md                    # 项目说明文档
```

**Note**: The online judge system (`online-judge-rust`) is a separate third-party dependency that needs to be cloned and set up separately. See the [Online Judge Setup](#-online-judge-setup) section for details.

## 🔧 Development

### Setup Development Environment
```bash
# Install development dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Format code
uv run black src/ tests/

# Lint code
uv run ruff check src/ tests/

# Type checking
uv run mypy src/
```

### Project Structure

- **`src/competemas/core/`**: Core business logic
  - `competition.py`: Competition lifecycle management
  - `agents.py`: Multi-agent framework implementation
  - `judge.py`: Code evaluation and scoring
  - `models.py`: Data models and schemas
  - `storage.py`: Data persistence layer

- **`src/competemas/api/`**: REST API interface
  - `server.py`: Flask API server with comprehensive endpoints

- **`src/competemas/cli/`**: Command-line tools
  - `run_competition.py`: Competition execution tool

- **`src/competemas/utils/`**: Utility functions
  - `problem_loader.py`: USACO problem loading
  - `prompts.py`: LLM prompt management
  - `conversation_logger.py`: Logging utilities

## 📊 Competition System

### Agent Response Format
The competition system returns structured data to agents:

  ```python
  {
    "competition_id": str,           # Current competition ID
    "competition_details": {         # Competition details
          "id": str,
          "title": str,
          "description": str,
          "problem_ids": List[str],
          "rules": Dict
      },
    "competitor_state": {            # Current competitor state
        "name": str,                 # Competitor name
        "remaining_tokens": int,     # Remaining tokens
          "solved_problems": List[str], # List of solved problems
        "is_running": bool,          # Whether still running
          "termination_reason": Optional[str], # Termination reason if any
        "score": int,                # Current score
        "final_score": int           # Final score
      },
    "problems": List[Dict],          # List of all problems
    "rankings": List[Dict],          # Current rankings
    "last_action_result": {          # Result of the last action
        "status": str,               # "success" or "error"
        "data": Dict,                # Action return data
        "message": str               # Error message if any
      },
    "other_competitors_status": [    # Status of other competitors
          {
              "name": str,
              "is_terminated": bool,
              "termination_reason": Optional[str]
          }
      ]
  }
  ```

### Available Actions
1. **VIEW_PROBLEM**: View problem details
2. **GET_HINT**: Request hints (consumes tokens)
3. **SUBMIT_SOLUTION**: Submit code solution
4. **TERMINATE**: End participation

## 🔬 For Reviewers

We warmly welcome reviewers to explore and experiment with our system!

### Model Configuration
- Configure different LLM models in `config/competitors_config.json`
- Key parameters: `model_id`, `api_base`, `api_key`
- Token pricing can be adjusted in `competition.py` line 73
- Reference [Artificial Analysis](https://artificialanalysis.ai/) for model pricing

### Competition Parameters
- Adjust competition parameters in `config/competition_config.json`
- Modify `config/problem_ids.json` to test different problem sets
- All available problems are listed in `config/all_problems.json`

### Custom MAS Development
- Modify prompts in `prompts.py` and agent behaviors in `agents.py`
- Agents connect through `Agent.process` function
- Experiment with different strategies and approaches! 😊

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Thanks to all contributors
- Inspired by various programming competition platforms
- Built with modern Python best practices 
- USACO problem library from [USACO Bench](https://github.com/princeton-nlp/USACO)
- Online Judge implementation from [CP Initiative](https://github.com/cpinitiative/online-judge-rust)
