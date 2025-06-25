# CompeteMAS (Competition Multi-Agent System)

This repository contains the supplementary code for NeurIPS 2025 paper under review: "CompeteMAS: Cost-Aware Evaluation of Agentic Coding Capabilities of Multi-Agent Systems", and is for review only.


## Installation

> We recommand to use [uv](https://docs.astral.sh/uv/) to manage the environment.

1. Create and activate a virtual environment:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```

3. Prepare USACO data:

   Download the USACO data from the [link](https://drive.google.com/file/d/1z5ODOJMqyer1QxzYtEUZ2hbAx-7nU8Vi/view?usp=share_link) provided by [USACO Bench](https://github.com/princeton-nlp/USACO).

   Then unzip the zip file, modify the name of the extracted folder from `data_copy` to `data`, and place it in the root directory of this repository.


## Prepare the Online Judge Emulator

1. Clone the repository (can be placed in any directory)
   ```bash
   git clone https://github.com/cpinitiative/online-judge-rust.git
   ```

2. Install dependencies

   ```bash
   cargo install cargo-lambda  # install cargo-lambda
   cargo lambda --help  # verify the success of installing cargo-lambda
   sudo snap install zig --classic --beta  # install zig
   zig version  # verify the success of installing zig
   ```

   If rust and cargo are not installed (generally installed by defult):

   ```bash
   curl https://sh.rustup.rs -sSf | sh
   rustc --version
   cargo --version
   ```

3. Put up OJ Emuator

   ```bash
   cd online-judge-rust
   cargo lambda build
   docker build --platform linux/amd64 -t oj-rust .
   docker run --platform linux/amd64 -p 9000:8080 oj-rust
   ```

   Then the OJ Emulator will be waiting at port 9000. You can use the following command to test its health:

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


## Usage

### Basic Workflow

1. Start the system:
   ```bash
   source .venv/bin/activate
   python main.py
   ```

2. Configure the competition:
   - Configure LLM API in `config/competitors_config.json`, especially `model_id`, `api_base` and `api_key`.
   - If you want to add or delete competitors, just add or delete elements in the list of competitors.

3. Run the competition:
   ```bash
   source .venv/bin/activate
   python run_competition.py
   ```


## System Components

### Core Components

- **Competition Management** (`competition.py`): Handles competition lifecycle and rules
- **Multi-Agent Framework** (`agents.py`): Manages LLM agent interactions
- **Problem Management** (`problem_loader.py`): Handles problem loading and distribution
- **Evaluation System** (`judge.py`): Evaluates submitted solutions
- **API Server** (`api.py`): Provides RESTful interface

### Supporting Components

- **Storage Layer** (`storage.py`): Manages data persistence
- **Configuration Management** (`config/`): Handles system configuration
- **Logging System** (`conversation_logger.py`): Tracks system events

### Project Structure
```
CompeteMAS/
├── config/            # Configuration files
├── agents.py          # Multi-agent framework
├── api.py             # API server
├── competition.py     # Competition management
├── judge.py           # Evaluation system
├── main.py            # System entry point
├── problem_loader.py  # Problem management
├── storage.py         # Data persistence
└── requirements.txt   # Dependencies
```


## For Reviewers

We warmly welcome reviewers to explore and experiment with our system! Here are some suggestions for your review:

### Model Configuration
- You can try different LLM models by configuring them in `config/competitors_config.json`
- Key parameters to set:
  - model_id: the model_name for API call
  - api_base/api_key: set to your API configuration
- Token mapping relationships should be supplemented in `competition.py` line 73 to reflect different pricing models. You can refer to [Artificial Analysis](https://artificialanalysis.ai/) for model price factors.

### Competition Parameters
- Feel free to adjust competition parameters to test different scenarios.
- You can also adjust `config/problem_ids.json` to import different problems to observe how agents perform on different types of challenges. All problem IDs are available in `config/all_problems.json`.
- Have fun experimenting! 😊

### Custom MAS Development
- You can modify the prompts and agent behaviors in `prompts.py` and `agents.py` to test different strategies.
- Agents and competition are connected through the function `Agent.process`.
- The competition system returns a dictionary to agents with the following structure:
  ```python
  {
      "competition_id": str,      # Current competition ID
      "competition_details": {    # Competition details
          "id": str,
          "title": str,
          "description": str,
          "problem_ids": List[str],
          "rules": Dict
      },
      "competitor_state": {       # Current competitor state
          "name": str,           # Competitor name
          "remaining_tokens": int, # Remaining tokens
          "solved_problems": List[str], # List of solved problems
          "is_running": bool,    # Whether still running
          "termination_reason": Optional[str], # Termination reason if any
          "score": int,          # Current score
          "final_score": int     # Final score
      },
      "problems": List[Dict],    # List of all problems
      "rankings": List[Dict],    # Current rankings
      "last_action_result": {    # Result of the last action
          "status": str,         # "success" or "error"
          "data": Dict,          # Action return data
          "message": str         # Error message if any
      },
      "other_competitors_status": [  # Status of other competitors
          {
              "name": str,
              "is_terminated": bool,
              "termination_reason": Optional[str]
          }
      ]
  }
  ```


## Acknowledgments

- Thanks to all contributors
- Inspired by various programming competition platforms
- Built with modern Python best practices 
