import os
import json
import logging
import asyncio
import copy
import argparse
from datetime import datetime, timedelta
from typing import Dict, List

from scripts.agents.custom_agents import GenericAPIAgent, StreamingGenericAPIAgent
from scripts.competition_organizer import CompetitionOrganizer
from competemas.engine.competition import Competitor


os.makedirs('logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler('logs/competition.log', mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("competition_runner")

def load_config(config_path: str) -> Dict:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in configuration file {config_path}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading configuration file {config_path}: {str(e)}")
        raise

def create_sample_problems() -> List[Dict]:
    """Create sample problems for the competition"""
    return [
        {
            "id": "sum_two_numbers",
            "title": "Sum of Two Numbers",
            "description": "Write a program that reads two integers from standard input and outputs their sum.",
            "difficulty": "bronze",
            "sample_cases": [
                {
                    "input": "5 7",
                    "output": "12"
                },
                {
                    "input": "10 -3",
                    "output": "7"
                }
            ],
            "constraints": "1 <= a, b <= 1000"
        },
        {
            "id": "fibonacci",
            "title": "Fibonacci Sequence",
            "description": "Write a program that reads an integer n from standard input and outputs the nth Fibonacci number.",
            "difficulty": "silver",
            "sample_cases": [
                {
                    "input": "5",
                    "output": "5"
                },
                {
                    "input": "10",
                    "output": "55"
                }
            ],
            "constraints": "0 <= n <= 45"
        }
    ]

def create_competitors(competitors_config: Dict, competition_config: Dict) -> List[Competitor]:
    """Create competitors based on configuration"""
    competitors = []
    
    # Create competitors based on their type
    for competitor in competitors_config["competitors"]:
        if competitor["type"] == "streaming":
            agent = StreamingGenericAPIAgent(
                name=competitor["name"],
                model_id=competitor["model_id"],
                api_base_url=competitor["api_base_url"],
                api_key=competitor["api_key"],
                prompt_config_path=competitor.get("prompt_config_path"),
                log_dir=f"logs/{competitor['name']}",
                session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
                request_format=competitor.get("request_format"),
                response_format=competitor.get("response_format"),
            )
        elif competitor["type"] == "generic":
            agent = GenericAPIAgent(
                name=competitor["name"],
                model_id=competitor["model_id"],
                api_base_url=competitor["api_base_url"],
                api_key=competitor["api_key"],
                prompt_config_path=competitor.get("prompt_config_path"),
                log_dir=f"logs/{competitor['name']}",
                session_id=datetime.now().strftime("%Y%m%d_%H%M%S"),
                request_format=competitor.get("request_format"),
                response_format=competitor.get("response_format"),
            )
        else:
            raise ValueError(f"Invalid competitor type: {competitor['type']}")
        
        # Wrap agent with Competitor class
        competitor_obj = Competitor(
            name=competitor["name"],
            agent=agent,
            max_tokens=competition_config.get("max_tokens_per_participant", 1e7)
        )
        competitors.append(competitor_obj)
        logger.info(f"Created competitor: {competitor_obj.name}")
    
    return competitors

def print_competition_results(results: Dict, competition_id: str):
    """Print competition results in a formatted way"""
    try:
        print(f"\n=== Competition Results of {competition_id} ===\n")
        
        # Sort competitors by total score
        sorted_results = sorted(
            results.items(),
            key=lambda x: x[1].get("final_score", 0),
            reverse=True
        )
        
        # Print results table
        print(f"{'Rank':<5} {'Name':<20} {'Score':<10} {'Solved':<10}")
        print("-" * 50)
        
        for rank, (name, data) in enumerate(sorted_results, 1):
            print(f"{rank:<5} {name:<20} {data.get('final_score', 0):<10} "
                  f"{len(data.get('solved_problems', [])):<10}")
        
        print("\n=== Detailed Results ===\n")
        for name, data in sorted_results:
            print(f"\n{name}:")
            print(f"  Final Score: {data.get('final_score', 0)}")
            print(f"  Solved Problems: {', '.join(data.get('solved_problems', [])) if data.get('solved_problems') else 'None'}")
            if data.get('termination_reason'):
                print(f"  Termination Reason: {data['termination_reason']}")
            if data.get('remaining_tokens'):
                print(f"  Remaining Tokens: {data['remaining_tokens']}")
            if data.get('participant_id'):
                print(f"  Participant ID: {data['participant_id']}")
    except Exception as e:
        logger.error(f"Error printing competition results: {str(e)}")
        raise

async def main():
    """Main function to run the competition"""
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Run an LLM competition')
        parser.add_argument('--competition-config', 
                          default='config/competition_config.json',
                          help='Path to competition configuration file')
        parser.add_argument('--competitors-config',
                          default='config/competitors_config.json',
                          help='Path to competitors configuration file')
        parser.add_argument('--problem-ids',
                          default='config/problem_ids.json',
                          help='Path to problem IDs configuration file')
        
        args = parser.parse_args()
        
        # Load configuration
        logger.info("Loading competition configuration...")
        competition_config = load_config(args.competition_config)
        competitors_config = load_config(args.competitors_config)
        problem_ids = load_config(args.problem_ids)
        
        # Validate problem_ids is a list
        if not isinstance(problem_ids, list):
            logger.error("problem_ids must be a list in the configuration file")
            return
        
        # Initialize competition organizer
        logger.info("Initializing competition organizer...")
        organizer = CompetitionOrganizer(api_base=competition_config["api_base"])
        
        # Create competitors
        logger.info("Creating competitors...")
        competitors = create_competitors(competitors_config, competition_config)
        for competitor in competitors:
            organizer.add_competitor(competitor)
            logger.info(f"Added competitor: {competitor.name}")
        
        # Create competition
        logger.info("Creating competition...")
        competition_id = organizer.create_competition(
            title=competition_config.get("competition_title", ""),
            description=competition_config.get("competition_description", ""),
            problem_ids=problem_ids,
            max_tokens_per_participant=competition_config.get("max_tokens_per_participant", 1e7),
            rules=competition_config.get("rules", {})
        )
        
        if not competition_id:
            logger.error("Failed to create competition - no competition ID returned")
            return
        
        logger.info(f"Created competition with ID: {competition_id}")
        
        # Join competition
        logger.info("Joining competition...")
        if not organizer.join_competition(competition_id):
            logger.error("Failed to join competition")
            return
        
        logger.info("Successfully joined competition")
        
        # Run competition
        logger.info("Starting competition...")
        results = await organizer.run_llm_competition()
        results_to_print = copy.deepcopy(results)
        
        # Save results to file
        results["competition_id"] = competition_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs("competition_results", exist_ok=True)
        results_file = f"competition_results/{competition_config.get('competition_title', '')}_{timestamp}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {results_file}")

        # Print results
        print_competition_results(results_to_print, competition_id)
        
    except Exception as e:
        logger.error(f"Error running competition: {str(e)}", exc_info=True)
        raise

def main_sync():
    """Synchronous main function for CLI entry point"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Competition interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error in competition: {str(e)}", exc_info=True) 


if __name__ == "__main__":
    main_sync() 