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

CompeteMAS v0.2.0 adopts a modular design that achieves clear separation between **core framework** and **user-defined content**:

```
CompeteMAS/
├── 🏗️ Core Framework Package
│   ├── core/                     # Core business logic
│   │   ├── models.py            # Data model definitions
│   │   ├── storage.py           # DuckDB storage system
│   │   ├── judge.py             # Code evaluation system
│   │   ├── competition.py       # Competition core logic
│   │   └── agent_interface.py   # Agent interface abstraction
│   ├── REST API Service
│   │   └── server.py            # Flask API server
│   ├── utils/                   # Utility modules
│   │   ├── problem_loader.py    # USACO problem loader
│   │   └── conversation_logger.py # Conversation logging
│   └── main.py                  # Framework main entry
├── 🛠️ User Custom Scripts
│   ├── agents/                  # Custom agent implementations
│   │   └── single_agent.py     # LLM agent class
│   ├── prompts/                 # Custom prompt templates
│   │   └── prompt_manager.py    # Prompt system
│   └── run_competition.py       # Competition run main script
├── 📋 Examples and Config Templates
│   └── sample_configs/          # Example configuration files
├── Configuration directory
├── 📊 Data storage directory
└── logs/                        # Log directory
```

### Modular Design Advantages

#### 1. Clear Separation of Responsibilities
- **Core Framework** (`competemas/`) - Stable business logic and infrastructure
- **User Scripts** (`scripts/`) - Customizable agents, prompts, and run scripts
- **Example Configurations** (`examples/`) - Configuration templates and documentation

#### 2. Agent Interface Design
Created `AgentInterface` abstract interface for loose coupling:

```python
# competemas/core/agent_interface.py
class AgentInterface(ABC):
    @abstractmethod
    async def process(self, state: Dict) -> Dict:
        """Process competition state, generate next action"""
        pass
```

#### 3. Performance Optimization
- **Storage Optimization**: DuckDB database size reduced from 972MB to 2.3MB (99.8% savings)
- **Dynamic Loading**: Test cases loaded on-demand from file system, first access only +10-50ms
- **Modular Architecture**: Supports parallel development, easy to maintain and extend

## 🎯 Usage

### Quick Start

#### 1. Start API Server
   ```bash
# Use new framework entry
python -m competemas.main --host 0.0.0.0 --port 5000

# Or run directly
cd competemas
python main.py --debug
   ```

#### 2. Configure Participants
Edit `examples/sample_configs/competitors_config.json`:
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

#### 3. Run Competition
   ```bash
# Use user custom script
python scripts/run_competition.py \
    --competition-config examples/sample_configs/competition_config.json \
    --competitors-config examples/sample_configs/competitors_config.json \
    --problem-ids examples/sample_configs/problem_ids.json
```

### Custom Agent Development

Implement your agent in `agents/single_agent/single_agent.py`:

```python
from competemas.core.agent_interface import AgentInterface

class MyCustomAgent(AgentInterface):
    async def process(self, state: Dict) -> Dict:
        # Implement your agent logic
        return {"action": "VIEW_PROBLEMS"}
```

### API Usage

The system provides comprehensive REST API:

```bash
# List all competitions
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

### Project Structure Details

#### Core Framework (`competemas/`)
- **`core/`**: Core business logic
  - `models.py`: Data models and type definitions
  - `storage.py`: DuckDB storage system with high-performance queries
  - `judge.py`: Code evaluation and execution system
  - `competition.py`: Competition lifecycle management
  - `agent_interface.py`: Agent abstraction interface

- **`api/`**: REST API interfaces
  - `server.py`: Flask API server providing complete RESTful interfaces

- **`utils/`**: Utility functions
  - `problem_loader.py`: USACO problem dynamic loading
  - `conversation_logger.py`: Conversation logging

#### User Custom (`scripts/`)
- **`agents/`**: Agent implementations
  - `single_agent.py`: Universal agent supporting multiple LLM providers

- **`prompts/`**: Prompt management
  - `prompt_manager.py`: Prompt templates and parsing system

- **`run_competition.py`**: Competition execution script

#### Configuration and Examples (`examples/`)
- **`sample_configs/`**: Configuration file templates
  - Competition configuration, participant configuration, problem lists, etc.

## 📊 Competition System

### Agent Response Format
竞赛系统向智能体返回结构化数据：

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
  "competitor_state": {            # Current participant state
      "name": str,                 # Participant name
      "remaining_tokens": int,     # Remaining tokens
        "solved_problems": List[str], # Solved problems list
      "is_running": bool,          # Whether still running
        "termination_reason": Optional[str], # Termination reason (if any)
      "score": int,                # Current score
      "score": int           # Final score
      },
  "problems": List[Dict],          # All problems list
  "rankings": List[Dict],          # Current rankings
  "last_action_result": {          # Last action result
      "status": str,               # "success" or "error"
      "data": Dict,                # Action return data
      "message": str               # Error message (if any)
      },
  "other_competitors_status": [    # Other competitors status
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
3. **submission_SOLUTION**: Submit code solution
4. **TERMINATE**: End participation

## 🔄 Migration Guide

If you have code based on the old structure (src/ directory), please migrate following these steps:

### 1. Update Import Paths
```python
# Old import method
from src.competemas.core.agents import GenericAPIAgent

# New import method  
from agents import GenericAPIAgent
```

### 2. Move Custom Code
- Custom agents → `agents/`
- Custom prompts → `scripts/prompts/`
- Run scripts → `scripts/`

### 3. Update Configuration Files
- Copy configuration templates: `examples/sample_configs/`
- Adjust configuration parameters as needed

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
