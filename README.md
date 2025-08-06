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
- **📈 High Performance**: Optimized storage system with DuckDB backend

## 📋 Prerequisites

- **Python 3.10+**
- **uv** (recommended package manager)
- **Rust & Cargo** (for online judge)
- **Docker** (for containerized deployment)

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone https://github.com/maple-zhou/CodingBench.git
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

## 🎯 Usage

### Quick Start

Here are three different ways to run a competition:

#### Method 1: Manual Control (Two Terminals)
```bash
# Terminal 1: Start the API server
python -m competemas.main --port 5000 --debug

# Terminal 2: Run a competition
python scripts/run_competition.py \
    --competition-title "Test Competition" \
    --max-tokens-per-participant 50000 \
    --port 5000
```

#### Method 2: Shell Commands (Single Terminal)
```bash
# Start server in background
competition_server --port 5000 &

# Run competition
competition_run --competition-title "Test Competition" --max-tokens-per-participant 50000

# Stop server when done
pkill -f competition_server
```

#### Method 3: Automated Loop (Multiple Rounds)
```bash
# Run 5 competitions automatically
./run_competition_loop.sh 5 \
    --server-args "--port 5000 --debug" \
    --client-args "--competition-title 'Test Competition' --max-tokens-per-participant 50000"
```

### Configuration

#### 1. Configure Participants
Edit `config/competitors_config.json`:

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

#### 2. Available Options

**Server Options:**
- `--config`: Path to server configuration file (default: `config/server_config.json`)
- `--host`: Host to bind the API server (default: `0.0.0.0`)
- `--port`: Port to bind the API server (default: `5000`)
- `--debug`: Enable debug mode
- `--log-level`: Override log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- `--log-dir`: Override log directory
- `--oj-endpoint`: Override online judge endpoint
- `--db-path`: Override database path

**Competition Options:**
- `--competition-config`: Path to competition configuration (default: `config/competition_config.json`)
- `--competitors-config`: Path to competitors configuration (default: `config/competitors_config.json`)
- `--problem-ids`: Path to problem IDs configuration (default: `config/problems.json`)
- `--api-base`: API base URL (default: `http://localhost:5000`)
- `--port`: API server port (default: `5000`)
- `--competition-title`: Competition title
- `--competition-description`: Competition description
- `--max-tokens-per-participant`: Maximum tokens per participant
- `--log-level`: Log level
- `--log-dir`: Log directory

### Custom Agent Development

Implement your agent by extending the base Agent class:

```python
from competemas.models.agent import Agent

class MyCustomAgent(Agent):
    async def generate_response(self, messages: List[Dict], **kwargs) -> Tuple[str, Dict]:
        # Implement your agent logic
        return "response", {"tokens": 100}
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

# Get participant information
curl http://localhost:5000/api/competitions/{competition_id}/participants/{participant_id}

# Get problems list
curl http://localhost:5000/api/competitions/{competition_id}/problems

# Get submissions for a participant
curl http://localhost:5000/api/competitions/{competition_id}/participants/{participant_id}/submissions
```

**Note**: Replace `{competition_id}` and `{participant_id}` with actual IDs from your competition.

### Monitor Results

```bash
# Check competition status via API
curl http://localhost:5000/api/competitions

# View rankings
curl http://localhost:5000/api/competitions/{competition_id}/rankings

# Convert results to CSV
./convert_all_json_to_csv.sh
```

The competition will automatically:
- Create participants based on your configuration
- Run the competition with the specified problems
- Track token usage and scores
- Generate detailed logs and results
- Save results to JSON and CSV files

### Shell Script Automation

For automated and repeated competition runs, you can use the provided shell scripts:

#### 1. Single Competition Run
```bash
# Start server (in background)
competition_server --port 5000 &

# Run competition
competition_run --competitors-config config/1v3.json --problem-ids config/problems.json

# Stop server
pkill -f competition_server
```

#### 2. Automated Competition Loop
```bash
# Run 5 competitions with default settings
./run_competition_loop.sh 5

# Run with custom server arguments
./run_competition_loop.sh 3 --server-args "--port 5000 --debug"

# Run with custom client arguments
./run_competition_loop.sh 5 --client-args "--competitors-config config/1v3.json --problem-ids config/problems.json"

# Run with both custom server and client arguments
./run_competition_loop.sh 10 \
    --server-args "--port 5000 --debug" \
    --client-args "--competitors-config config/1v3.json --problem-ids config/problems.json --max-tokens-per-participant 50000"
```

**Shell script features:**
- **Automated server management**: Starts and stops server automatically
- **Multiple rounds**: Run competitions in a loop
- **Comprehensive logging**: Detailed logs for each round
- **Error handling**: Automatic cleanup on failures
- **Port management**: Automatic port detection and cleanup
- **CSV conversion**: Automatically converts results to CSV format

#### 3. Batch Result Conversion
```bash
# Convert all JSON results to CSV
./convert_all_json_to_csv.sh

# This script will:
# - Find all JSON files in logs/run_logs/
# - Convert them to CSV format
# - Skip already converted files
# - Provide detailed conversion statistics
```

#### 4. Available Shell Commands

**Server Management:**
```bash
# Start server with default settings
competition_server

# Start server with custom port
competition_server --port 8080

# Start server with debug mode
competition_server --debug --log-level DEBUG

# Start server with custom config
competition_server --config config/server_config.json
```

**Competition Execution:**
```bash
# Run competition with default settings
competition_run

# Run with custom configuration
competition_run --competitors-config config/1v3.json --problem-ids config/problems.json

# Run with token limits
competition_run --max-tokens-per-participant 100000

# Run with custom competition title
competition_run --competition-title "My Custom Competition"
```

**Result Processing:**
```bash
# Convert single JSON file to CSV
python json_to_csv_converter.py results.json results.csv

# Convert all results in batch
./convert_all_json_to_csv.sh
```

## 🏗️ Architecture

CompeteMAS adopts a modular design that achieves clear separation between **core framework** and **user-defined content**:

```
CompeteMAS/
├── 🏗️ Core Framework Package (competemas/)
│   ├── models/                   # Data model definitions
│   │   ├── models.py            # Core data models
│   │   └── agent.py             # Agent base class
│   ├── engine/                  # Core business logic
│   │   ├── storage.py           # DuckDB storage system
│   │   └── judge.py             # Code evaluation system
│   ├── server/                  # REST API Service
│   │   └── server.py            # Flask API server
│   ├── utils/                   # Utility modules
│   │   ├── problem_loader.py    # USACO problem loader
│   │   ├── textbook_loader.py   # Textbook content loader
│   │   ├── strategy_loader.py   # Strategy content loader
│   │   ├── usacoguide_loader.py # USACO guide loader
│   │   └── logger_config.py     # Logging configuration
│   └── main.py                  # Framework main entry
├── 🛠️ User Custom Scripts (scripts/)
│   ├── run_competition.py       # Competition run main script
│   ├── competition_organizer.py # Competition organization logic
│   └── competitors.py           # Competitor management
├── 🤖 Agent Implementations (agents/)
│   └── single_agent/            # Single agent implementation
│       ├── single_agent.py      # Generic API agent
│       └── prompts/             # Prompt templates
│           └── prompt_manager.py # Prompt management system
├── ⚙️ Configuration (config/)
│   ├── competition_config.json  # Competition configuration
│   ├── competitors_config.json  # Participants configuration
│   ├── problems.json           # Problem lists
│   └── server_config.json      # Server configuration
├── 📊 Data storage (data/)
├── 📝 Logs (logs/)
└── 🧪 Tests (tests/)
```

### Modular Design Advantages

#### 1. Clear Separation of Responsibilities
- **Core Framework** (`competemas/`) - Stable business logic and infrastructure
- **User Scripts** (`scripts/`) - Customizable competition execution and management
- **Agent Implementations** (`agents/`) - LLM agent implementations
- **Configuration** (`config/`) - Configuration files and templates

#### 2. Agent Interface Design
The system uses a flexible agent interface for loose coupling:

```python
# competemas/models/agent.py
class Agent(ABC):
    @abstractmethod
    async def generate_response(self, messages: List[Dict], **kwargs) -> Tuple[str, Dict]:
        """Generate response from LLM"""
        pass
```

#### 3. Performance Optimization
- **Storage Optimization**: DuckDB database for high-performance analytics
- **Dynamic Loading**: Test cases loaded on-demand from file system
- **Modular Architecture**: Supports parallel development, easy to maintain and extend

### Project Structure Details

#### Core Framework (`competemas/`)
- **`models/`**: Data models and agent interfaces
  - `models.py`: Core data models (Competition, Participant, Problem, etc.)
  - `agent.py`: Agent base class and interfaces

- **`engine/`**: Core business logic
  - `storage.py`: DuckDB storage system with high-performance queries
  - `judge.py`: Code evaluation and execution system

- **`server/`**: REST API interfaces
  - `server.py`: Flask API server providing complete RESTful interfaces

- **`utils/`**: Utility functions
  - `problem_loader.py`: USACO problem dynamic loading
  - `textbook_loader.py`: Textbook content loading and search
  - `strategy_loader.py`: Strategy content loading
  - `usacoguide_loader.py`: USACO guide content loading
  - `logger_config.py`: Logging configuration

#### User Scripts (`scripts/`)
- **`run_competition.py`**: Main competition execution script
- **`competition_organizer.py`**: Competition organization and management
- **`competitors.py`**: Competitor class and management

#### Agent Implementations (`agents/`)
- **`single_agent/`**: Single agent implementation
  - `single_agent.py`: Generic API agent supporting multiple LLM providers
  - `prompts/prompt_manager.py`: Prompt templates and parsing system

#### Configuration (`config/`)
- **`competition_config.json`**: Competition configuration
- **`competitors_config.json`**: Participants configuration
- **`problems.json`**: Problem lists
- **`server_config.json`**: Server configuration

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
  "competitor_state": {            # Current participant state
      "name": str,                 # Participant name
      "remaining_tokens": int,     # Remaining tokens
      "solved_problems": List[str], # Solved problems list
      "is_running": bool,          # Whether still running
      "termination_reason": Optional[str], # Termination reason (if any)
      "score": int                 # Current score
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

### Hint System
The system provides multi-level hints:
- **Level 0**: Strategy hints (competitive programming strategies)
- **Level 1**: Problem-relevant textbook content
- **Level 2**: Knowledge-relevant textbook content
- **Level 3**: Similar problems with solutions
- **Level 4**: Knowledge-specific example problems

## 🔬 For Reviewers

We warmly welcome reviewers to explore and experiment with our system!

### Model Configuration
- Configure different LLM models in `config/competitors_config.json`
- Key parameters: `model_id`, `api_base_url`, `api_key`
- Adjust token pricing in `agents/single_agent/single_agent.py`
- Refer to [Artificial Analysis](https://artificialanalysis.ai/) for model pricing information

### Competition Parameters
- Adjust competition parameters in `config/competition_config.json`
- Modify `config/problems.json` to test different problem sets
- All available problems are listed in `config/all_problems_ids.json`

### Custom MAS Development
- Modify prompts in `agents/single_agent/prompts/prompt_manager.py`
- Adjust agent behavior in `agents/single_agent/single_agent.py`
- Agents connect through the `Agent.generate_response` function
- Welcome to try different strategies and approaches! 😊

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

---

**CompeteMAS v0.2.0** - A modular, efficient, and extensible multi-agent competition framework 🎉
