# CompeteMAS API Server

A comprehensive Flask-based REST API server for managing competitive programming competitions with AI agents.

## Overview

The CompeteMAS API server provides a complete backend solution for:
- Competition management and participant tracking
- Problem library integration with USACO problems
- AI agent integration with token management
- Code submission evaluation and ranking
- Textbook search and hint generation
- Real-time participant status monitoring

## Features

### 🏆 Competition Management
- Create competitions with custom problems and rules
- Manage participants with API configurations
- Track competition rankings and statistics
- Support for active/inactive competition filtering

### 🤖 AI Agent Integration
- Standardized agent API endpoints for LLM requests
- Automatic token tracking and multiplier application
- Streaming and non-streaming response support
- Participant token management and limits

### 📚 Problem Library
- USACO problem integration with multiple difficulty levels
- Similar problem search using BM25 algorithm
- Problem metadata and test case management
- Sample case and constraint information

### 💡 Intelligent Hints
- Multi-level hint system (Level 1-3)
- Textbook knowledge integration
- Similar problem recommendations
- Token-based hint cost system

### 📝 Code Evaluation
- Automated code submission evaluation
- Test case execution and scoring
- Penalty calculation for failed attempts
- Real-time submission status tracking

## API Endpoints

### Competitions

#### `POST /api/competitions/create`
Create a new competition with specified problems.

**Request Body:**
```json
{
    "title": "Competition Title",
    "description": "Competition Description",
    "problem_ids": ["problem_1", "problem_2"],
    "max_tokens_per_participant": 100000,
    "rules": {...}
}
```

#### `GET /api/competitions/get/<competition_id>`
Get competition details by ID.

**Query Parameters:**
- `include_details`: Include problems, participants, and rankings (default: false)

#### `GET /api/competitions/list`
List all competitions.

**Query Parameters:**
- `active_only`: Return only active competitions (default: false)

### Participants

#### `POST /api/participants/create/<competition_id>`
Create a new participant in a competition.

**Request Body:**
```json
{
    "name": "Participant Name",
    "api_base_url": "http://api.example.com/",
    "api_key": "sk-...",
    "limit_tokens": 100000,
    "lambda_value": 100
}
```

#### `GET /api/participants/get/<competition_id>/<participant_id>`
Get participant details.

**Query Parameters:**
- `include_submissions`: Include submission history (default: false)

#### `GET /api/participants/list/<competition_id>`
List all participants in a competition.

#### `POST /api/participants/terminate/<competition_id>/<participant_id>`
Terminate a participant.

**Request Body:**
```json
{
    "reason": "manual_termination"
}
```

#### `GET /api/participants/status/<competition_id>/<participant_id>`
Get participant termination status and statistics.

#### `GET /api/participants/terminated/<competition_id>`
List terminated participants in a competition.

### Problems

#### `GET /api/problems/get/<competition_id>/<problem_id>`
Get problem details by ID.

#### `GET /api/problems/list/<competition_id>`
List all problems in a competition.

#### `GET /api/problems/similar`
Find similar problems using BM25 similarity search.

**Query Parameters:**
- `problem_id`: Target problem ID
- `num_problems`: Number of similar problems (default: 2)
- `competition_id`: Competition ID to exclude from search

### Submissions

#### `POST /api/submissions/create/<competition_id>/<participant_id>/<problem_id>`
Create and evaluate a code submission.

**Request Body:**
```json
{
    "code": "Source code to submit",
    "language": "cpp"
}
```

#### `GET /api/submissions/list/<competition_id>`
List submissions with optional filtering.

**Query Parameters:**
- `participant_id`: Filter by participant (optional)
- `problem_id`: Filter by problem (optional)
- `include_code`: Include source code (default: false)

#### `GET /api/submissions/get/<submission_id>`
Get submission details by ID.

**Query Parameters:**
- `include_code`: Include source code (default: false)

### Rankings

#### `GET /api/rankings/get/<competition_id>`
Get competition rankings sorted by score.

### Problem Library

#### `GET /api/problem-library`
List available problems in the problem library.

**Query Parameters:**
- `level`: Filter by problem level (bronze, silver, gold, platinum)

### Textbook Search

#### `GET /api/textbook/search`
Search textbook content for relevant information.

**Query Parameters:**
- `query`: Search query string
- `max_results`: Maximum results (default: 5)

### Hints

#### `POST /api/hints/get/<competition_id>/<participant_id>/<problem_id>`
Get hint for a specific problem.

**Request Body:**
```json
{
    "hint_level": 1
}
```

**Hint Levels:**
- Level 1: Basic hint with textbook knowledge (500 tokens)
- Level 2: Detailed hint with similar problems (1000 tokens)
- Level 3: Comprehensive hint combining both (1500 tokens)

### Agent API

#### `POST /api/agent/call/<competition_id>/<participant_id>`
Standardized agent API endpoint for LLM requests.

**Request Body:**
```json
{
    "json": {
        "model": "gpt-3.5-turbo",
        "messages": [...]
    },
    "api_path": "/v1/chat/completions",
    "timeout": 30.0
}
```

#### `POST /api/stream_agent/call/<competition_id>/<participant_id>`
Streaming agent API endpoint for LLM requests.

### System

#### `GET /api/system/oj-status`
Check online judge connection status.

## Response Format

### Success Response
```json
{
    "status": "success",
    "message": "Success message",
    "data": {...}
}
```

### Error Response
```json
{
    "status": "error",
    "message": "Error description"
}
```

## Setup and Installation

### Prerequisites
- Python 3.8+
- Flask
- DuckDB
- Required dependencies (see requirements.txt)

### Running the Server

```bash
# Development mode
python -m competemas.api.server

# Production mode
python -c "from competemas.api.server import run_api; run_api(debug=False)"
```

### Configuration

The server uses the following components:
- **DuckDBStorage**: Database backend for data persistence
- **USACOProblemLoader**: Problem library integration
- **TextbookLoader**: Textbook content for hints
- **Judge**: Online judge integration for code evaluation

## Error Handling

The API includes comprehensive error handling:
- Input validation for all endpoints
- Database error handling
- External API error management
- Detailed error messages with line numbers for debugging

## Token Management

The system includes sophisticated token management:
- Per-participant token limits
- Automatic token deduction for API calls
- Hint cost calculation
- Token multiplier support for different operations

## Security Features

- API key management for participants
- Input sanitization and validation
- Error message sanitization
- Rate limiting considerations

## Development

### Adding New Endpoints

1. Define the route with appropriate HTTP method
2. Add comprehensive docstring with request/response format
3. Implement error handling
4. Use standardized response functions (`success_response`, `error_response`)

### Testing

The API can be tested using:
- Unit tests in `tests/` directory
- Integration tests for full workflow
- Manual testing with tools like curl or Postman

## Contributing

When contributing to the API:
1. Follow the existing code style and patterns
2. Add comprehensive docstrings for new functions
3. Include error handling for all endpoints
4. Update this README for new features
5. Add appropriate tests

## License

[Add your license information here] 