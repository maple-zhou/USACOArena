# CompeteMAS Server Configuration Guide

## Overview

The CompeteMAS server now supports a flexible configuration system that allows users to customize server behavior through configuration files, environment variables, and command line arguments.

## Configuration Hierarchy

Configuration is applied in the following priority order (from high to low):

1. **Command line arguments** - Highest priority
2. **Environment variables** - Medium priority  
3. **Configuration files** - Base configuration
4. **Default values** - Lowest priority

## Configuration Files

### Default Configuration File Location
```
config/server_config.json
```

### Configuration File Structure

```json
{
  "logging": {
    "level": "INFO",
    "directory": "logs/competition_system",
    "enable_colors": true
  },
  "online_judge": {
    "endpoint": "http://localhost:9000/2015-03-31/functions/function/invocations"
  },
  "rate_limiting": {
    "min_interval": 0.05
  },
  "database": {
    "path": "data/competemas.duckdb",
    "backup_json": true
  },
  "data_sources": {
    "problem_data_dir": "dataset/datasets/usaco_2025",
    "textbook_data_dir": "dataset/textbooks"
  }
}
```

## Environment Variables

All configuration items can be overridden through environment variables. The environment variable naming rule is:

```
COMPETEMAS_<SECTION>_<KEY>
```

### Example Environment Variables

```bash
# Logging configuration
export COMPETEMAS_LOG_LEVEL=DEBUG
export COMPETEMAS_LOG_DIR=/custom/logs

# Online judge configuration
export COMPETEMAS_OJ_ENDPOINT=http://custom-oj:9000/api

# Rate limiting configuration
export COMPETEMAS_RATE_LIMIT_INTERVAL=0.1

# Database configuration
export COMPETEMAS_DB_PATH=/custom/data/competemas.db
export COMPETEMAS_DB_BACKUP_JSON=false

# Data source configuration
export COMPETEMAS_PROBLEM_DATA_DIR=/custom/problems
export COMPETEMAS_TEXTBOOK_DATA_DIR=/custom/textbooks
```

## Command Line Arguments

### Basic Usage

```bash
# Start with default configuration
competition_server

# Specify configuration file
competition_server --config /path/to/custom_config.json

# Override server settings
competition_server --host 127.0.0.1 --port 8080 --debug
```

### All Available Arguments

```bash
competition_server [OPTIONS]

Server configuration:
  --config PATH              Configuration file path (default: config/server_config.json)
  --host HOST                服务器绑定地址 (默认: 0.0.0.0)
  --port PORT                服务器端口 (默认: 5000)
  --debug                    启用调试模式

日志配置:
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                            覆盖日志级别
  --log-dir PATH            覆盖日志目录

在线评测配置:
  --oj-endpoint URL         覆盖在线评测端点

速率限制配置:
  --rate-limit-interval SECONDS
                            覆盖速率限制间隔

数据库配置:
  --db-path PATH            覆盖数据库路径

Data source configuration:
  --problem-data-dir PATH   Override problem data directory
  --textbook-data-dir PATH  Override textbook data directory
```

## Configuration Details

### Logging Configuration (logging)

| Configuration Item | Type | Default Value | Description |
|-------------------|------|---------------|-------------|
| level | string | "INFO" | Log level |
| directory | string | "logs/competition_system" | Log directory |
| enable_colors | boolean | true | Whether to enable colored logs |

### Online Judge Configuration (online_judge)

| Configuration Item | Type | Default Value | Description |
|-------------------|------|---------------|-------------|
| endpoint | string | "http://localhost:9000/..." | Online judge service endpoint |

### Rate Limiting Configuration (rate_limiting)

| Configuration Item | Type | Default Value | Description |
|-------------------|------|---------------|-------------|
| min_interval | float | 0.05 | Minimum request interval (seconds) |

### Database Configuration (database)

| Configuration Item | Type | Default Value | Description |
|-------------------|------|---------------|-------------|
| path | string | "data/competemas.duckdb" | Database file path |
| backup_json | boolean | true | Whether to backup as JSON format |

### Data Source Configuration (data_sources)

| Configuration Item | Type | Default Value | Description |
|-------------------|------|---------------|-------------|
| problem_data_dir | string | "dataset/datasets/usaco_2025" | Problem data directory |
| textbook_data_dir | string | "dataset/textbooks" | Textbook data directory |

## Usage Examples

### Development Environment Configuration

```bash
# Development environment startup
competition_server \
  --debug \
  --log-level DEBUG \
  --log-dir logs/dev \
  --oj-endpoint http://localhost:9000/api \
  --rate-limit-interval 0.01
```

### Production Environment Configuration

```bash
# Production environment startup
competition_server \
  --host 0.0.0.0 \
  --port 5000 \
  --log-level INFO \
  --log-dir /var/log/competemas \
  --oj-endpoint https://oj.production.com/api
```

### Docker Environment Configuration

```bash
# Configure using environment variables
docker run -d \
  -e COMPETEMAS_LOG_LEVEL=INFO \
  -e COMPETEMAS_DB_PATH=/data/competemas.db \
  -e COMPETEMAS_PROBLEM_DATA_DIR=/problems \
  -e COMPETEMAS_OJ_ENDPOINT=http://oj-service:9000/api \
  -p 5000:5000 \
  competemas/server
```

## Configuration Verification

When starting the server, the system will display loaded configuration information:

```
2024-01-01 12:00:00 INFO main: Starting CompeteMAS API server on 0.0.0.0:5000
2024-01-01 12:00:00 INFO main: Configuration loaded from: config/server_config.json
2024-01-01 12:00:00 INFO server: Configured rate limiter with interval: 0.05s
2024-01-01 12:00:00 INFO server: Server configuration applied successfully
```

## Troubleshooting

### Common Issues

1. **Configuration file does not exist**
   - System will use default configuration
   - Check if configuration file path is correct

2. **Environment variable format error**
   - 布尔值使用: true/false, 1/0, yes/no
   - 数组使用逗号分隔: "value1,value2,value3"

3. **权限问题**
   - 确保对日志目录和数据库目录有写权限

### 调试配置

```bash
# 启用调试模式查看详细配置信息
competition_server --debug --log-level DEBUG
```

## 迁移指南

### 从旧版本迁移

1. 创建新的配置文件 `config/server_config.json`
2. 将硬编码的配置项迁移到配置文件
3. 使用环境变量或命令行参数覆盖特定配置
4. 测试配置是否正确应用

### 配置备份

建议定期备份配置文件：

```bash
cp config/server_config.json config/server_config.json.backup
```