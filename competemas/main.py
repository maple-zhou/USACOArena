"""
Main entry point for CompeteMAS framework.

This module provides command-line interface and programmatic access to
start the CompeteMAS API server and manage competitions.
"""

import argparse
import sys
import os
from datetime import datetime
from .api.server import run_api
from .utils.logger_config import setup_logging, get_logger
from .utils.config_manager import get_config

def setup_logging_from_config(config):
    """Setup logging based on configuration"""
    log_config = config.get_section("log")
    server_config = config.get_section("server")
    
    # Create log directory
    log_dir = log_config.get("dir", "logs/server_logs")
    port = server_config.get("port", 5000)  # 从server配置获取端口
    os.makedirs(log_dir, exist_ok=True)
    
    # Generate log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_dir, f"server_{port}_{timestamp}.log")
    
    # Setup logging
    setup_logging(
        level=log_config.get("level", "INFO"),
        log_file=log_filename,
        enable_colors=log_config.get("enable_colors", True)
    )

def main():
    """Main entry point for CompeteMAS CLI"""
    parser = argparse.ArgumentParser(description='CompeteMAS - Multi-Agent System Competition Framework')
    
    # Server configuration
    parser.add_argument('--config', default='config/server_config.json',
                       help='Path to server configuration file')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind the API server')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind the API server')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    # Logging configuration
    parser.add_argument('--log-level', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                       help='Override log level')
    parser.add_argument('--log-dir', help='Override log directory')
    
    # Online Judge configuration
    parser.add_argument('--oj-endpoint', help='Override online judge endpoint')
    
    # Rate limiting configuration
    parser.add_argument('--rate-limit-interval', type=float, 
                       help='Override rate limit interval (seconds)')
    
    # Database configuration
    parser.add_argument('--db-path', help='Override database path')
    
    # Data sources configuration
    parser.add_argument('--problem-data-dir', help='Override problem data directory')
    parser.add_argument('--textbook-data-dir', help='Override textbook data directory')
    
    args = parser.parse_args()
    
    # Load configuration
    config = get_config(args.config)
    
    # Override configuration with command line arguments
    if args.host:
        config.set("server.host", args.host)
    if args.port:
        config.set("server.port", args.port)
    if args.log_level:
        config.set("log.level", args.log_level)
    if args.log_dir:
        config.set("log.dir", args.log_dir)
    if args.oj_endpoint:
        config.set("oj.endpoint", args.oj_endpoint)
    if args.rate_limit_interval:
        config.set("rate_limit.min_interval", args.rate_limit_interval)
    if args.db_path:
        config.set("db.path", args.db_path)
    if args.problem_data_dir:
        config.set("data.problem_data_dir", args.problem_data_dir)
    if args.textbook_data_dir:
        config.set("data.textbook_data_dir", args.textbook_data_dir)
    
    # Setup logging
    setup_logging_from_config(config)
    logger = get_logger("main")
    
    logger.info(f"Starting CompeteMAS API server on {args.host}:{args.port}")
    logger.info(f"Configuration loaded from: {config.config_path}")
    
    if args.debug:
        logger.debug("Debug mode enabled")
        config.set("log.level", "DEBUG")
    
    try:
        run_api(host=args.host, port=args.port, debug=args.debug, config=config)
    except KeyboardInterrupt:
        logger.info("\nShutting down CompeteMAS API server...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error starting API server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main() 