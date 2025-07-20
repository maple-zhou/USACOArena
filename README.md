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
- **🛡️ Secure Execution**: Sandboxed code execution via Rust-based judge
- **🏗️ Modular Architecture**: Clean separation of core framework and user customizations
- **📈 High Performance**: Optimized storage system with 99.8% space savings

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
mv data_copy dataset/datasets/usaco_2025
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

## 🏗️ Architecture

CompeteMAS v0.2.0 采用模块化设计，实现了**核心框架**与**用户自定义内容**的清晰分离：

```
CompeteMAS/
├── 🏗️ 核心框架包
│   ├── core/                     # 核心业务逻辑
│   │   ├── models.py            # 数据模型定义
│   │   ├── storage.py           # DuckDB存储系统
│   │   ├── judge.py             # 代码评判系统
│   │   ├── competition.py       # 竞赛核心逻辑
│   │   └── agent_interface.py   # 智能体接口抽象
│   ├── REST API服务
│   │   └── server.py            # Flask API服务器
│   ├── utils/                   # 工具模块
│   │   ├── problem_loader.py    # USACO问题加载器
│   │   └── conversation_logger.py # 对话日志记录
│   └── main.py                  # 框架主入口
├── 🛠️ 用户自定义脚本
│   ├── agents/                  # 自定义智能体实现
│   │   └── single_agent.py     # LLM智能体类
│   ├── prompts/                 # 自定义提示词模板
│   │   └── prompt_manager.py    # 提示词系统
│   └── run_competition.py       # 竞赛运行主脚本
├── 📋 示例和配置模板
│   └── sample_configs/          # 示例配置文件
├── 配置文件目录
├── 📊 数据存储目录
└── logs/                        # 日志目录
```

### 模块化设计优势

#### 1. 清晰的职责分离
- **核心框架** (`competemas/`) - 稳定的业务逻辑和基础设施
- **用户脚本** (`scripts/`) - 可自定义的智能体、提示词和运行脚本
- **示例配置** (`examples/`) - 配置模板和文档

#### 2. 智能体接口设计
创建了`AgentInterface`抽象接口，实现松耦合：

```python
# competemas/core/agent_interface.py
class AgentInterface(ABC):
    @abstractmethod
    async def process(self, state: Dict) -> Dict:
        """处理竞赛状态，生成下一步行动"""
        pass
```

#### 3. 性能优化
- **存储优化**：DuckDB数据库大小从972MB降至2.3MB (99.8%节省)
- **动态加载**：测试用例按需从文件系统加载，首次访问仅+10-50ms
- **模块化架构**：支持并行开发，易于维护和扩展

## 🎯 Usage

### Quick Start

#### 1. 启动API服务器
   ```bash
# 使用新的框架入口
python -m competemas.main --host 0.0.0.0 --port 5000

# 或者直接运行
cd competemas
python main.py --debug
   ```

#### 2. 配置参赛者
编辑 `examples/sample_configs/competitors_config.json`:
```json
{
  "competitors": [
    {
      "name": "gpt-4",
      "type": "generic",
      "model_id": "gpt-4",
      "api_base_url": "https://api.openai.com/v1",
      "api_key": "your-api-key"
    }
  ]
}
```

#### 3. 运行竞赛
   ```bash
# 使用用户自定义脚本
python scripts/run_competition.py \
    --competition-config examples/sample_configs/competition_config.json \
    --competitors-config examples/sample_configs/competitors_config.json \
    --problem-ids examples/sample_configs/problem_ids.json
```

### 自定义智能体开发

在`agents/single_agent/single_agent.py`中实现您的智能体：

```python
from competemas.core.agent_interface import AgentInterface

class MyCustomAgent(AgentInterface):
    async def process(self, state: Dict) -> Dict:
        # 实现您的智能体逻辑
        return {"action": "VIEW_PROBLEMS"}
```

### API Usage

系统提供全面的REST API：

```bash
# 列出所有竞赛
curl http://localhost:5000/api/competitions

# 创建竞赛
curl -X POST http://localhost:5000/api/competitions \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Competition",
    "description": "A test competition",
    "problem_ids": ["1323_bronze_feb"],
    "max_tokens_per_participant": 100000
  }'

# 获取竞赛详情
curl http://localhost:5000/api/competitions/{competition_id}

# 查看排名
curl http://localhost:5000/api/competitions/{competition_id}/rankings
```

## 🔧 Development

### Setup Development Environment
```bash
# Install development dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Format code
uv run black competemas/ scripts/ tests/

# Lint code
uv run ruff check competemas/ scripts/ tests/

# Type checking
uv run mypy competemas/
```

### 项目结构详解

#### 核心框架 (`competemas/`)
- **`core/`**: 核心业务逻辑
  - `models.py`: 数据模型和类型定义
  - `storage.py`: DuckDB存储系统，支持高性能查询
  - `judge.py`: 代码评判和执行系统
  - `competition.py`: 竞赛生命周期管理
  - `agent_interface.py`: 智能体抽象接口

- **`api/`**: REST API接口
  - `server.py`: Flask API服务器，提供完整的RESTful接口

- **`utils/`**: 工具函数
  - `problem_loader.py`: USACO问题动态加载
  - `conversation_logger.py`: 对话日志记录

#### 用户自定义 (`scripts/`)
- **`agents/`**: 智能体实现
  - `single_agent.py`: 支持多种LLM提供商的通用智能体

- **`prompts/`**: 提示词管理
  - `prompt_manager.py`: 提示词模板和解析系统

- **`run_competition.py`**: 竞赛执行脚本

#### 配置和示例 (`examples/`)
- **`sample_configs/`**: 配置文件模板
  - 竞赛配置、参赛者配置、问题列表等

## 📊 Competition System

### Agent Response Format
竞赛系统向智能体返回结构化数据：

  ```python
  {
  "competition_id": str,           # 当前竞赛ID
  "competition_details": {         # 竞赛详情
          "id": str,
          "title": str,
          "description": str,
          "problem_ids": List[str],
          "rules": Dict
      },
  "competitor_state": {            # 当前参赛者状态
      "name": str,                 # 参赛者名称
      "remaining_tokens": int,     # 剩余令牌数
        "solved_problems": List[str], # 已解决问题列表
      "is_running": bool,          # 是否仍在运行
        "termination_reason": Optional[str], # 终止原因（如果有）
      "score": int,                # 当前得分
      "score": int           # 最终得分
      },
  "problems": List[Dict],          # 所有问题列表
  "rankings": List[Dict],          # 当前排名
  "last_action_result": {          # 上次操作结果
      "status": str,               # "success" 或 "error"
      "data": Dict,                # 操作返回数据
      "message": str               # 错误消息（如果有）
      },
  "other_competitors_status": [    # 其他参赛者状态
          {
              "name": str,
              "is_terminated": bool,
              "termination_reason": Optional[str]
          }
      ]
  }
  ```

### Available Actions
1. **VIEW_PROBLEM**: 查看问题详情
2. **GET_HINT**: 请求提示（消耗令牌）
3. **submission_SOLUTION**: 提交代码解决方案
4. **TERMINATE**: 结束参与

## 🔄 迁移指南

如果您有基于旧结构（src/目录）的代码，请按以下步骤迁移：

### 1. 更新导入路径
```python
# 旧的导入方式
from src.competemas.core.agents import GenericAPIAgent

# 新的导入方式  
from agents import GenericAPIAgent
```

### 2. 移动自定义代码
- 自定义智能体 → `agents/`
- 自定义提示词 → `scripts/prompts/`
- 运行脚本 → `scripts/`

### 3. 更新配置文件
- 复制配置模板：`examples/sample_configs/`
- 根据需要调整配置参数

## 🔬 For Reviewers

我们热烈欢迎审稿人探索和试验我们的系统！

### Model Configuration
- 在 `examples/sample_configs/competitors_config.json` 中配置不同的LLM模型
- 关键参数: `model_id`, `api_base_url`, `api_key`
- 可在 `agents/single_agent/single_agent.py` 中调整令牌定价
- 参考 [Artificial Analysis](https://artificialanalysis.ai/) 获取模型定价信息

### Competition Parameters
- 在 `examples/sample_configs/competition_config.json` 中调整竞赛参数
- 修改 `examples/sample_configs/problem_ids.json` 测试不同问题集
- 所有可用问题列在 `config/all_problems.json` 中

### Custom MAS Development
- 在 `scripts/prompts/prompt_manager.py` 中修改提示词
- 在 `agents/single_agent/single_agent.py` 中调整智能体行为
- 智能体通过 `Agent.process` 函数连接
- 欢迎尝试不同的策略和方法！😊

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. submission a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Thanks to all contributors
- Inspired by various programming competition platforms
- Built with modern Python best practices 
- USACO problem library from [USACO Bench](https://github.com/princeton-nlp/USACO)
- Online Judge implementation from [CP Initiative](https://github.com/cpinitiative/online-judge-rust)

---

**CompeteMAS v0.2.0** - 更模块化、更高效、更易扩展的多智能体竞赛框架 🎉
