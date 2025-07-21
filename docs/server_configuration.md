# CompeteMAS 服务器配置指南

## 概述

CompeteMAS 服务器现在支持灵活的配置系统，允许用户通过配置文件、环境变量和命令行参数来自定义服务器行为。

## 配置层次结构

配置按以下优先级应用（从高到低）：

1. **命令行参数** - 最高优先级
2. **环境变量** - 中等优先级  
3. **配置文件** - 基础配置
4. **默认值** - 最低优先级

## 配置文件

### 默认配置文件位置
```
config/server_config.json
```

### 配置文件结构

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

## 环境变量

所有配置项都可以通过环境变量覆盖，环境变量命名规则为：

```
COMPETEMAS_<SECTION>_<KEY>
```

### 示例环境变量

```bash
# 日志配置
export COMPETEMAS_LOG_LEVEL=DEBUG
export COMPETEMAS_LOG_DIR=/custom/logs

# 在线评测配置
export COMPETEMAS_OJ_ENDPOINT=http://custom-oj:9000/api

# 速率限制配置
export COMPETEMAS_RATE_LIMIT_INTERVAL=0.1

# 数据库配置
export COMPETEMAS_DB_PATH=/custom/data/competemas.db
export COMPETEMAS_DB_BACKUP_JSON=false

# 数据源配置
export COMPETEMAS_PROBLEM_DATA_DIR=/custom/problems
export COMPETEMAS_TEXTBOOK_DATA_DIR=/custom/textbooks
```

## 命令行参数

### 基本用法

```bash
# 使用默认配置启动
competition_server

# 指定配置文件
competition_server --config /path/to/custom_config.json

# 覆盖服务器设置
competition_server --host 127.0.0.1 --port 8080 --debug
```

### 所有可用参数

```bash
competition_server [OPTIONS]

服务器配置:
  --config PATH              配置文件路径 (默认: config/server_config.json)
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

数据源配置:
  --problem-data-dir PATH   覆盖问题数据目录
  --textbook-data-dir PATH  覆盖教材数据目录
```

## 配置项详解

### 日志配置 (logging)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| level | string | "INFO" | 日志级别 |
| directory | string | "logs/competition_system" | 日志目录 |
| enable_colors | boolean | true | 是否启用彩色日志 |

### 在线评测配置 (online_judge)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| endpoint | string | "http://localhost:9000/..." | 在线评测服务端点 |

### 速率限制配置 (rate_limiting)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| min_interval | float | 0.05 | 最小请求间隔（秒） |

### 数据库配置 (database)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| path | string | "data/competemas.duckdb" | 数据库文件路径 |
| backup_json | boolean | true | 是否备份为JSON格式 |

### 数据源配置 (data_sources)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| problem_data_dir | string | "dataset/datasets/usaco_2025" | 问题数据目录 |
| textbook_data_dir | string | "dataset/textbooks" | 教材数据目录 |

## 使用示例

### 开发环境配置

```bash
# 开发环境启动
competition_server \
  --debug \
  --log-level DEBUG \
  --log-dir logs/dev \
  --oj-endpoint http://localhost:9000/api \
  --rate-limit-interval 0.01
```

### 生产环境配置

```bash
# 生产环境启动
competition_server \
  --host 0.0.0.0 \
  --port 5000 \
  --log-level INFO \
  --log-dir /var/log/competemas \
  --oj-endpoint https://oj.production.com/api
```

### Docker环境配置

```bash
# 使用环境变量配置
docker run -d \
  -e COMPETEMAS_LOG_LEVEL=INFO \
  -e COMPETEMAS_DB_PATH=/data/competemas.db \
  -e COMPETEMAS_PROBLEM_DATA_DIR=/problems \
  -e COMPETEMAS_OJ_ENDPOINT=http://oj-service:9000/api \
  -p 5000:5000 \
  competemas/server
```

## 配置验证

启动服务器时，系统会显示加载的配置信息：

```
2024-01-01 12:00:00 INFO main: Starting CompeteMAS API server on 0.0.0.0:5000
2024-01-01 12:00:00 INFO main: Configuration loaded from: config/server_config.json
2024-01-01 12:00:00 INFO server: Configured rate limiter with interval: 0.05s
2024-01-01 12:00:00 INFO server: Server configuration applied successfully
```

## 故障排除

### 常见问题

1. **配置文件不存在**
   - 系统会使用默认配置
   - 检查配置文件路径是否正确

2. **环境变量格式错误**
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