"""
Main entry point for CompeteMAS framework.

This module provides command-line interface and programmatic access to
start the CompeteMAS API server and manage competitions.
"""

import argparse
import sys
from .api.server import run_api


def main():
    """Main entry point for CompeteMAS CLI"""
    parser = argparse.ArgumentParser(description='CompeteMAS - Multi-Agent System Competition Framework')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind the API server')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind the API server')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    print(f"Starting CompeteMAS API server on {args.host}:{args.port}")
    if args.debug:
        print("Debug mode enabled")
    
    try:
        run_api(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        print("\nShutting down CompeteMAS API server...")
        sys.exit(0)
    except Exception as e:
        print(f"Error starting API server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 