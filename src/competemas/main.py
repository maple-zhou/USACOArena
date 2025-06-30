import argparse
import os
import logging
import threading
import time
from .api.server import app as api_app
from .utils.problem_loader import USACOProblemLoader

os.makedirs("logs", exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/competition_system.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("competition_system")


def run_api_server(args):
    """Run the API server"""
    logger.info(f"Starting API server on port {args.port}...")
    api_app.run(host=args.host, port=args.port, debug=args.debug)


def main():
    """Main entry point for the competition system"""
    parser = argparse.ArgumentParser(description="USACO Competition System")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="API server host")
    parser.add_argument("--port", type=int, default=5000, help="API server port")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--usaco-data-path", type=str, help="Path to USACO problem library data", default='data/datasets/usaco_2025')
    args = parser.parse_args()
    
    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    # # Initialize data storage
    # data_storage = DataStorage()
    
    # Check USACO problem library status
    usaco_loader = USACOProblemLoader(args.usaco_data_path)
    problem_count = len(usaco_loader.get_problem_ids())
    if problem_count > 0:
        logger.info(f"USACO problem library loaded successfully: {problem_count} problems found")
        logger.info(f"USACO data path: {usaco_loader.data_path}")
        # List some example problems
        problem_ids = usaco_loader.get_problem_ids()[:5]  # Get up to 5 problems
        logger.info(f"Sample problem IDs: {problem_ids}")
    else:
        logger.warning(f"USACO problem library empty or not found at {usaco_loader.data_path}")
        logger.warning("Please check that the USACO dataset is correctly installed")
        logger.warning("Expected location: data/datasets/usaco_2025_dict.json")
    
    # Start API server in a separate thread
    api_thread = threading.Thread(target=run_api_server, args=(args,))
    api_thread.daemon = True
    api_thread.start()
    
    # Wait a moment for the API server to start
    time.sleep(2)
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down competition system...")


if __name__ == "__main__":
    main() 