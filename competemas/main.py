"""
Main entry point for CompeteMAS framework.

This module provides command-line interface and programmatic access to
start the CompeteMAS API server and manage competitions.
"""

import argparse
import sys
from .api.server import run_api
from .utils.logger_config import setup_logging, get_logger

# Setup logging
import os
from datetime import datetime

# 确保logs目录存在
os.makedirs('logs/competition_system', exist_ok=True)

# 根据当前时间创建日志文件名
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f"logs/competition_system/competition_system_{timestamp}.log"

setup_logging(level="INFO", log_file=log_filename)
logger = get_logger("main")

def main():
    """Main entry point for CompeteMAS CLI"""
    parser = argparse.ArgumentParser(description='CompeteMAS - Multi-Agent System Competition Framework')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind the API server')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind the API server')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    logger.info(f"Starting CompeteMAS API server on {args.host}:{args.port}")
    if args.debug:
        logger.debug("Debug mode enabled")
    
    try:
        run_api(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        logger.info("\nShutting down CompeteMAS API server...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error starting API server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main() 