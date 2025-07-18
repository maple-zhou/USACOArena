#!/bin/bash

# 竞赛运行循环脚本
# 用法: ./run_competition_loop.sh <运行次数>

# 检查参数
if [ $# -eq 0 ]; then
    echo "用法: $0 <运行次数>"
    echo "示例: $0 5"
    exit 1
fi

# 获取运行次数
N=$1

# 检查参数是否为数字
if ! [[ "$N" =~ ^[0-9]+$ ]]; then
    echo "错误: 运行次数必须是正整数"
    exit 1
fi

echo "开始运行竞赛循环，总共运行 $N 次"
echo "=================================="

# 创建日志目录
mkdir -p logs/competition_loops
timestamp=$(date +"%Y%m%d_%H%M%S")
log_file="logs/competition_loops/loop_${timestamp}.log"

# 记录开始时间
echo "竞赛循环开始时间: $(date)" | tee -a "$log_file"

for ((i=1; i<=N; i++)); do
    echo ""
    echo "=================================="
    echo "第 $i 轮运行 (共 $N 轮)"
    echo "开始时间: $(date)"
    echo "==================================" | tee -a "$log_file"
    echo "第 $i 轮运行开始时间: $(date)" | tee -a "$log_file"
    
    # 启动competemas服务器
    echo "启动competemas服务器..."
    echo "启动competemas服务器..." | tee -a "$log_file"
    
    # 直接启动服务器（后台运行）
    source .venv/bin/activate
    competemas > "logs/competition_loops/server_round_${i}.log" 2>&1 &
    server_pid=$!
    
    echo "服务器进程ID: $server_pid"
    echo "服务器进程ID: $server_pid" | tee -a "$log_file"
    
    # 等待服务器启动
    echo "等待服务器启动..."
    echo "等待服务器启动..." | tee -a "$log_file"
    
    # 检查服务器是否启动（最多等待60秒）
    server_started=false
    for ((wait_time=0; wait_time<60; wait_time++)); do
        if curl -s http://localhost:5000/api/system/oj-status > /dev/null 2>&1; then
            server_started=true
            break
        fi
        echo "等待服务器启动... ($((wait_time+1))/60)"
        sleep 1
    done
    
    if [ "$server_started" = false ]; then
        echo "错误: 服务器启动超时"
        echo "错误: 服务器启动超时" | tee -a "$log_file"
        # 清理进程
        if [ ! -z "$server_pid" ]; then
            kill $server_pid 2>/dev/null
        fi
        continue
    fi
    
    echo "服务器已启动，开始运行competemas_run..."
    echo "服务器已启动，开始运行competemas_run..." | tee -a "$log_file"
    
    # 启动competemas_run客户端（前台运行）
    echo "运行competemas_run客户端..."
    echo "运行competemas_run客户端..." | tee -a "$log_file"
    
    source .venv/bin/activate
    competemas_run > "logs/competition_loops/client_round_${i}.log" 2>&1
    client_exit_code=$?
    
    echo "客户端运行完成，退出代码: $client_exit_code"
    echo "客户端运行完成，退出代码: $client_exit_code" | tee -a "$log_file"
    
    echo "客户端运行完成，关闭服务器..."
    echo "客户端运行完成，关闭服务器..." | tee -a "$log_file"
    
    # 关闭服务器
    if [ ! -z "$server_pid" ]; then
        echo "关闭服务器进程 $server_pid..."
        echo "关闭服务器进程 $server_pid..." | tee -a "$log_file"
        
        # 尝试优雅关闭
        kill $server_pid 2>/dev/null
        sleep 2
        
        # 如果还在运行，强制关闭
        if kill -0 $server_pid 2>/dev/null; then
            echo "强制关闭服务器进程..."
            echo "强制关闭服务器进程..." | tee -a "$log_file"
            kill -9 $server_pid 2>/dev/null
        fi
    fi
    
    # 等待服务器完全关闭
    sleep 3
    
    echo "第 $i 轮运行完成"
    echo "结束时间: $(date)"
    echo "第 $i 轮运行结束时间: $(date)" | tee -a "$log_file"
    
    # 如果不是最后一轮，等待一下再开始下一轮
    if [ $i -lt $N ]; then
        echo "等待5秒后开始下一轮..."
        echo "等待5秒后开始下一轮..." | tee -a "$log_file"
        sleep 5
    fi
done

echo ""
echo "=================================="
echo "所有 $N 轮运行完成！"
echo "结束时间: $(date)"
echo "日志文件: $log_file"
echo "==================================" | tee -a "$log_file"
echo "所有 $N 轮运行完成！结束时间: $(date)" | tee -a "$log_file" 