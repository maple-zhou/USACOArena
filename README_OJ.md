# Serverless Online Judge (Rust)

## Overview
这是一套面向竞赛与练习场景的轻量级在线判题服务，采用 Rust + Axum 构建，内置进程隔离与资源控制，可在本地或容器环境中快速部署，为 C++17、Java 21 与 Python 3.12 程序提供编译与执行能力，并支持自定义判题脚本（`testlib.h`）。

## Features
- 🛡️ **Secure Compilation**：通过 `secure-g++.sh` 拦截 `#pragma GCC optimize/target` 以及危险的 `__attribute__` 配置，并应用默认安全编译参数 `-O2 -std=c++17 -DONLINE_JUDGE`（可扩展但会阻止 `-Ofast`、`-march=native` 等风险选项）。
- 🔍 **Built-in Checkers**：提供 `strict_diff` 与 `noip_strict` 判题模式，自动区分 Presentation Error。
- 🧩 **Custom C++ Checkers**：支持携带基于 `testlib.h` 的自定义判题器，统一使用安全编译脚本并在隔离目录内运行。
- ⏱️ **Resource Governance**：所有子进程都通过统一的 `run_command` 执行，继承 `timeout`、ASLR 禁用、`/usr/bin/time -v` 统计与 16 MB 输出上限（超出时附加 `... (output truncated) ...` 标记并返回 `output_limit_exceeded`）。
- 📈 **Detailed Logging**：编译、执行、判题流程均输出结构化日志，包含语言、用时、内存与自定义判题器的运行指标。

## Getting Started
1. 安装 Rust（stable）、Python 3 与系统编译器（`g++`, `javac`, `python3.12`）。
2. 运行 `./start.sh` 以 release 配置构建并启动服务（监听 `0.0.0.0:10086`）。
3. 使用 `curl` 或集成测试脚本调用 `/compile-and-execute` 完成验证。

## API Reference
### 请求格式
`POST /compile-and-execute`

```jsonc
{
  "compile": {
    "language": "cpp",           // cpp | java21 | py12
    "source_code": "...",        // 用户源码
    "compiler_options": ["-DDEBUG"] // 可选，字符串数组，留空/缺省使用安全默认值
  },
  "execute": {
    "stdin": "",
    "timeout_ms": 2000,
    "file_io_name": null           // 可选，提供时会读写 <name>.in / <name>.out
  },
  "test_case": {
    "checker_type": "custom_cpp", // strict_diff | noip_strict | custom_cpp
    "expected_output": "5\n",
    "checker_source_code": "#include \"testlib.h\"\n..." // custom_cpp 时必填
  }
}
```

### 自定义判题器示例
```bash
curl -X POST http://127.0.0.1:10086/compile-and-execute \
  -H 'Content-Type: application/json' \
  -d @- <<'JSON'
{
  "compile": {
    "language": "cpp",
    "source_code": "#include <iostream>\nint main(){long long a,b;std::cin>>a>>b;std::cout<<a+b<<'\n';}"
  },
  "execute": {
    "stdin": "2 3\n",
    "timeout_ms": 2000
  },
  "test_case": {
    "checker_type": "custom_cpp",
    "expected_output": "5\n",
    "checker_source_code": "#include \"testlib.h\"\nint main(int argc,char** argv){registerTestlibCmd(argc, argv);long long a=inf.readLong();long long b=inf.readLong();long long expect=ans.readLong();long long actual=ouf.readLong();if(actual!=expect) quitf(_wa, \"expected %lld got %lld\", expect, actual);quitf(_ok, \"sum matches\");}"
  }
}
JSON
```

### 响应结构
```jsonc
{
  "compile": {
    "stdout": "",
    "stderr": "",
    "wall_time": "0.17",
    "memory_usage": "63488",
    "stdout_truncated": false,
    "stderr_truncated": false,
    "exit_code": 0,
    "exit_signal": null
  },
  "execute": {
    "stdout": "5\n",
    "stderr": "",
    "stdout_truncated": false,
    "stderr_truncated": false,
    "wall_time": "0.00",
    "memory_usage": "7808",
    "exit_code": 0,
    "exit_signal": null,
    "verdict": "accepted",
    "file_output": null,
    "full_output_url": null
  }
}
```

`verdict` 可能取值：`accepted`、`wrong_answer`、`presentation_error`、`output_limit_exceeded`、`time_limit_exceeded`、`runtime_error`。
当输出超过 16 MB 时，`stdout_truncated` 或 `stderr_truncated` 会置为 `true`，并在内容尾部追加 `... (output truncated) ...`。

## Testing
1. 启动服务：`./start.sh`。
2. 另开终端执行 `cargo test --test api_test`，该集成测试会命中主要判题路径。
3. 需要手工验证时，可复用 `manual_*.json` 中的示例 `curl` 请求（包含自定义判题、输出超限与 pragma 拦截场景）。

## Development Notes
- 所有公共结构体/函数均附带 Rust doc comment，查阅源码即可获得字段说明。
- 子进程统一在 `run_command` 中调度，若需扩展语言或沙箱逻辑，请复用该入口以继承超时、输出限制与 ASLR 设置。
- 默认输出上限可通过 `run_command::MAX_OUTPUT_BYTES` 调整。
