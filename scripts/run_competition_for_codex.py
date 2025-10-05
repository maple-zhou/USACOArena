import os
import json
import asyncio
import copy
import argparse
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from agents import GenericAPIAgent, StreamingGenericAPIAgent
from scripts.competition_organizer import CompetitionOrganizer
from scripts.competitors import Competitor
from usacoarena.utils.logger_config import setup_logging, get_logger
import requests

logger = get_logger("run_competition")


class CodexRegistrationError(RuntimeError):
    """Raised when registering the Codex participant fails."""


def setup_logging_from_config(competition_config, competition_config_file,competitors_config, problem_ids):
    log_config = competition_config.get("log")
    api_base = competition_config.get("api_base")

    match = re.search(r':(\d{4})$', api_base)
    if match:
        port = match.group(1)  # "5000"
    else:
        port = "5000"  # Default port

    # Generate log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    competitors_config_name = os.path.splitext(os.path.basename(competitors_config))[0]
    problem_ids_name = os.path.splitext(os.path.basename(problem_ids))[0]
    competition_config_name = os.path.splitext(os.path.basename(competition_config_file))[0]
    

    log_dir = log_config.get("dir", "logs/run_logs")
    log_dir = os.path.join(log_dir, f"run_{port}_{competitors_config_name}_{problem_ids_name}_{competition_config_name}_{timestamp}")
    # if "max_tokens_per_participant" in competition_config and competition_config["max_tokens_per_participant"] != 10000000:
    #     max_tokens_per_participant = competition_config["max_tokens_per_participant"]
    #     log_dir = os.path.join(log_dir, f"run_{port}_{competitors_config_name}_{problem_ids_name}_limit{max_tokens_per_participant}_{timestamp}")

    # elif "rules" in competition_config and "submission_tokens" in competition_config["rules"] and "AC" in competition_config["rules"]["submission_tokens"] and competition_config["rules"]["submission_tokens"]["AC"] != 100:
    #     submission_tokens = competition_config["rules"]["submission_tokens"]["AC"]

    #     log_dir = os.path.join(log_dir, f"run_{port}_{competitors_config_name}_{problem_ids_name}_sub{submission_tokens}_{timestamp}")
    
    # elif "rules" in competition_config and "penalties" in competition_config["rules"] and "CE" in competition_config["rules"]["penalties"] and competition_config["rules"]["penalties"]["CE"] != 5:
    #     penalties = competition_config["rules"]["penalties"]["CE"]
    #     log_dir = os.path.join(log_dir, f"run_{port}_{competitors_config_name}_{problem_ids_name}_pena{penalties}_{timestamp}")
    
    # elif "rules" in competition_config and "bonus_for_first_ac" in competition_config["rules"] and competition_config["rules"]["bonus_for_first_ac"] != 100:
    #     bonus_for_first_ac = competition_config["rules"]["bonus_for_first_ac"]
    #     log_dir = os.path.join(log_dir, f"run_{port}_{competitors_config_name}_{problem_ids_name}_bonus{bonus_for_first_ac}_{timestamp}")

    # elif "rules" in competition_config and "hint_tokens" in competition_config["rules"] and "level_0" in competition_config["rules"]["hint_tokens"] and competition_config["rules"]["hint_tokens"]["level_0"] != 500:
    #     hint_tokens = competition_config["rules"]["hint_tokens"]["level_0"]
    #     log_dir = os.path.join(log_dir, f"run_{port}_{competitors_config_name}_{problem_ids_name}_hint{hint_tokens}_{timestamp}")

    # elif "rules" in competition_config and "scoring" in competition_config["rules"] and "bronze" in competition_config["rules"]["scoring"] and competition_config["rules"]["scoring"]["bronze"] == 10000:
    #     bronze_score = competition_config["rules"]["scoring"]["bronze"]
    #     log_dir = os.path.join(log_dir, f"run_{port}_{competitors_config_name}_{problem_ids_name}_bronze{bronze_score}_{timestamp}")
    
    # elif "rules" in competition_config and "scoring" in competition_config["rules"] and "platinum" in competition_config["rules"]["scoring"] and competition_config["rules"]["scoring"]["platinum"] == 10000:
    #     platinum_score = competition_config["rules"]["scoring"]["platinum"]
    #     log_dir = os.path.join(log_dir, f"run_{port}_{competitors_config_name}_{problem_ids_name}_platinum{platinum_score}_{timestamp}")

    # else:
        # log_dir = os.path.join(log_dir, f"run_{port}_{competitors_config_name}_{problem_ids_name}_{timestamp}")

    
    os.makedirs(log_dir, exist_ok=True)
    
    # Setup logging
    setup_logging(level="INFO", log_file=f"{log_dir}/{competitors_config_name}_{competition_config_name}_run_competition.log")
    
    return log_dir  # Return the created log_dir


def register_codex_participant(
    api_base: str,
    competition_id: str,
    name: str,
    api_base_url: str,
    api_key: str,
    limit_tokens: int,
    lambda_value: int,
) -> str:
    """Register Codex CLI as a participant via the competition API."""

    url = f"{api_base}/api/participants/create/{competition_id}"
    payload = {
        "name": name,
        "api_base_url": api_base_url,
        "api_key": api_key,
        "limit_tokens": limit_tokens,
        "lambda_value": lambda_value,
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise CodexRegistrationError(f"HTTP error registering Codex: {exc}") from exc
    except ValueError as exc:
        raise CodexRegistrationError("Codex registration returned non-JSON response") from exc

    if data.get("status") != "success":
        raise CodexRegistrationError(
            data.get("message", "Unknown error while registering Codex")
        )

    participant_id = data.get("data", {}).get("id")
    if not participant_id:
        raise CodexRegistrationError("Codex registration response missing participant ID")

    return str(participant_id)


def write_codex_env_file(output_path: Path, env_lines: List[str]) -> None:
    """Write environment helper lines to disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

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

def create_competitors(competitors_config: Dict, competition_config: Dict, log_dir: Optional[str] = None) -> List[Competitor]:
    """Create competitors based on configuration"""
    competitors = []
    
    # Create competitors based on their type
    for competitor in competitors_config["competitors"]:
        if competitor["type"] == "generic":
            # Use the passed log_dir, if not available use default logs/{competitor_name}
            agent_log_dir = log_dir if log_dir is not None else f"logs/{competitor['name']}"
            
            agent = GenericAPIAgent(
                name=competitor["name"],
                model_id=competitor["model_id"],
                api_base_url=competitor["api_base_url"],
                api_key=competitor["api_key"],
                prompt_config_path=competitor.get("prompt_config_path"),
                log_dir=agent_log_dir,
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
            limit_tokens=competition_config.get("max_tokens_per_participant", 100000)
        )
        competitors.append(competitor_obj)
        logger.info(f"Created competitor: {competitor_obj.name}")
    
    return competitors


def log_competition_results(results: Dict, competition_id: str):
    """Log competition results using logger.critical with character limit"""
    try:
        sorted_results = {
        k: v for k, v in sorted(
            results.items(),
            key=lambda item: item[1].get("score", 0),
            reverse=True
        )
    }
        # Build the result string
        result_lines = []
        result_lines.append(f"=== Competition Results of {competition_id} ===")
        
        # Add results table
        result_lines.append(f"{'Rank':<5} {'Name':<20} {'Score':<10} {'Solved':<10} {'Status':<15}")
        result_lines.append("-" * 65)
        
        for rank, (name, data) in enumerate(sorted_results.items(), 1):
            status = "Running" if data.get('is_running', False) else "Terminated"
            result_lines.append(f"{rank:<5} {name:<20} {data.get('score', 0):<10} "
                              f"{len(data.get('solved_problems', [])):<10} {status:<15}")
        
        # Add detailed results
        result_lines.append("\n=== Detailed Results ===")
        for name, data in sorted_results.items():
            result_lines.append(f"\n{name}:")
            result_lines.append(f"  Final Score: {data.get('score', 0)}")
            
            # Token usage information
            result_lines.append(f"  Token Usage:")
            result_lines.append(f"    LLM Tokens: {data.get('LLM_tokens', 0)}")
            result_lines.append(f"    LLM Inference Count: {data.get('llm_inference_count', 0)}")
            result_lines.append(f"    Hint Tokens: {data.get('hint_tokens', 0)}")
            result_lines.append(f"    Submission Tokens: {data.get('submission_tokens', 0)}")
            # Safely get token values and ensure they are integers
            llm_tokens = data.get('LLM_tokens', 0)
            hint_tokens = data.get('hint_tokens', 0)
            submission_tokens = data.get('submission_tokens', 0)

            # Convert to int if they're not already (in case they're dicts or other types)
            try:
                llm_tokens = int(llm_tokens) if isinstance(llm_tokens, (int, float, str)) else 0
                hint_tokens = int(hint_tokens) if isinstance(hint_tokens, (int, float, str)) else 0
                submission_tokens = int(submission_tokens) if isinstance(submission_tokens, (int, float, str)) else 0
            except (ValueError, TypeError):
                llm_tokens = hint_tokens = submission_tokens = 0

            result_lines.append(f"    Total Used: {llm_tokens + hint_tokens + submission_tokens}")
            result_lines.append(f"    Limit: {data.get('limit_tokens', 0)}")
            result_lines.append(f"    Remaining: {data.get('remaining_tokens', 0)}")

            # Scoring breakdown
            result_lines.append(f"  Scoring Breakdown:")
            result_lines.append(f"    Bronze Score: {data.get('bronze_score', 0)}")
            result_lines.append(f"    Silver Score: {data.get('silver_score', 0)}")
            result_lines.append(f"    Gold Score: {data.get('gold_score', 0)}")
            result_lines.append(f"    Platinum Score: {data.get('platinum_score', 0)}")
            result_lines.append(f"    First AC Bonus: {data.get('bonus_score', 0)}")
            result_lines.append(f"    Total First AC Score: {data.get('first_ac_score', 0)}")
            result_lines.append(f"    Problem Score: {data.get('problem_score', 0)}")

            # Submission statistics
            result_lines.append(f"  Submission Statistics:")
            result_lines.append(f"    Total Submissions: {data.get('submission_count', 0)}")
            result_lines.append(f"    Accepted Submissions: {data.get('accepted_count', 0)}")
            result_lines.append(f"    Submission Penalty: {data.get('submission_penalty', 0)}")
            result_lines.append(f"    Problem Pass Score: {data.get('problem_pass_score', 0)}")

            # Per-problem statistics
            problem_stats = data.get('problem_stats', {})
            if problem_stats:
                result_lines.append(f"  Per-Problem Statistics:")
                result_lines.append(f"    Problems Attempted: {len(problem_stats)}")
                solved_problems = sum(1 for stats in problem_stats.values() if stats.get('solved', False))
                result_lines.append(f"    Problems Solved: {solved_problems}")
                total_problem_submissions = sum(stats.get('submission_count', 0) for stats in problem_stats.values())
                result_lines.append(f"    Total Problem Submissions: {total_problem_submissions}")
                problems_first_ac = sum(1 for stats in problem_stats.values() if stats.get('is_first_ac', False))
                result_lines.append(f"    Problems First AC: {problems_first_ac}")
                total_problem_penalty = sum(stats.get('penalty', 0) for stats in problem_stats.values())
                result_lines.append(f"    Total Problem Penalty: {total_problem_penalty}")
            
            # Solved problems
            solved_problems = data.get('solved_problems', [])
            if solved_problems and isinstance(solved_problems[0], dict):
                # If it's a list of dicts, extract problem_id from each dict
                solved_problems_str = ", ".join([p.get("problem_id", str(p)) for p in solved_problems])
            else:
                # If it's already a list of strings, join them directly
                solved_problems_str = ", ".join(solved_problems) if solved_problems else "None"
            result_lines.append(f"  Solved Problems: {solved_problems_str}")
            
            # Termination information
            if data.get('termination_reason'):
                result_lines.append(f"  Termination Reason: {data['termination_reason']}")
        
        # Join all lines and apply character limit
        result_str = "\n".join(result_lines)
        
        logger.critical(f"Competition Results:\n{result_str}")
        
    except Exception as e:
        logger.error(f"Error logging competition results: {str(e)}")
        raise

def save_competition_results(results, competition_id, competition_config, log_dir=None):
    """
    Save competition results to file
    
    Args:
        results: Competition results dictionary
        competition_id: Competition ID
        competition_config: Competition configuration
        log_dir: Log directory path (optional)
    
    Returns:
        str: Path to the saved file
    """
    # Sort competitors by total score
    sorted_results = {
        k: v for k, v in sorted(
            results.items(),
            key=lambda item: item[1].get("score", 0),
            reverse=True
        )
    }
    
    # Save results to file
    results["competition_id"] = competition_id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save competition_results to log_dir
    if log_dir:
        results_file = os.path.join(log_dir, f"competition_results_{timestamp}.json")
    else:
        os.makedirs("competition_results", exist_ok=True)
        results_file = f"competition_results/{competition_config.get('competition_title', '')}_{timestamp}.json"
        
    with open(results_file, 'w') as f:
        json.dump(sorted_results, f, indent=2)
    logger.info(f"Results saved to {results_file}")
    
    # Call JSON to CSV converter
    try:
        # Import converter module
        import sys
        import subprocess
        from pathlib import Path
        
        # Get current script directory
        current_dir = Path(__file__).parent.parent
        converter_script = current_dir / "json_to_csv_converter.py"
        
        if converter_script.exists():
            # Generate CSV file path (in the same directory as JSON file)
            json_path = Path(results_file)
            csv_file = json_path.with_suffix('.csv')
            
            # Call converter script
            result = subprocess.run([
                sys.executable, str(converter_script), 
                str(results_file), str(csv_file)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"CSV file generated: {csv_file}")
            else:
                logger.warning(f"Failed to generate CSV file: {result.stderr}")
        else:
            logger.warning(f"Converter script not found: {converter_script}")
            
    except Exception as e:
        logger.warning(f"Error generating CSV file: {e}")
    
    return results_file

async def main():
    """Main function to run the competition"""
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Run an LLM competition')
        
        parser.add_argument('--api-base',
                          default='http://localhost',
                          help='API base URL for the competition')
        parser.add_argument('--port',
                          default=5000,
                          help='Port for the competition')
        
        parser.add_argument('--competition-title',
                          default='Programming Competition 2025',
                          help='Title of the competition')
        parser.add_argument('--competition-description',
                          default='A competition to test coding abilities in solving programming problems',
                          help='Description of the competition')
        
        parser.add_argument('--competition-config', 
                          default='config/competition_config.json',
                          help='Path to competition configuration file')
        parser.add_argument('--competitors-config',
                          default='config/10llm.json',
                          help='Path to competitors configuration file')
        parser.add_argument('--problem-ids',
                          default='config/2025problems67.json',
                          help='Path to problem IDs configuration file')
        
        parser.add_argument('--log-level',
                          default='INFO',
                          help='Log level')
        parser.add_argument('--log-dir',
                          default='logs/run_logs',
                          help='Log directory')

        parser.add_argument('--lambda-value',
                          type=int,
                          help='Override lambda parameter when registering participants (defaults to rules.lambda).')
        parser.add_argument('--codex-name',
                          default='Codex Agent',
                          help='Display name for the Codex CLI participant.')
        parser.add_argument('--codex-api-base',
                          default='',
                          help='API base URL stored for the Codex participant (optional).')
        parser.add_argument('--codex-api-key',
                          default='',
                          help='API key stored for the Codex participant (optional).')
        parser.add_argument('--codex-limit-tokens',
                          type=int,
                          help='Token limit for Codex CLI participant (defaults to competition max).')
        parser.add_argument('--codex-env-output',
                          default="codex_agent_env.txt",
                          help='File path to save Codex CLI environment variables (defaults to <log_dir>/codex_cli_env.txt).')


        args = parser.parse_args()
        
        # Load configuration

        competition_config = load_config(args.competition_config)
        competitors_config = load_config(args.competitors_config)
        problem_ids = load_config(args.problem_ids)
        
        # Validate problem_ids is a list
        
        
        if args.api_base:
            competition_config["api_base"] = args.api_base
        if args.port:
            competition_config["api_base"] = f"{args.api_base}:{args.port}"
        
        if args.competition_title:
            competition_config["competition_title"] = args.competition_title
        if args.competition_description:
            competition_config["competition_description"] = args.competition_description
        
        if args.log_level:
            competition_config["log_level"] = args.log_level
        if args.log_dir:
            competition_config["log_dir"] = args.log_dir


        log_dir = setup_logging_from_config(competition_config, args.competition_config, args.competitors_config, args.problem_ids)

        if not isinstance(problem_ids, list):
            logger.error("problem_ids must be a list in the configuration file")
            return

        # Initialize competition organizer
        logger.info("Initializing competition organizer...")
        organizer = CompetitionOrganizer(api_base=competition_config["api_base"], log_dir=log_dir)
        
        # Create competitors
        logger.info("Creating competitors...")
        competitors = create_competitors(competitors_config, competition_config, log_dir)

        for competitor in competitors:
            organizer.add_competitor(competitor)
            logger.info(f"Added competitor: {competitor.name}")
        
        # Create competition
        logger.info("Creating competition...")
        competition_id = organizer.create_competition(
            title=competition_config.get("competition_title", ""),
            description=competition_config.get("competition_description", ""),
            problem_ids=problem_ids,
            max_tokens_per_participant=competition_config.get("max_tokens_per_participant", 100000),
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

        # Register Codex CLI as an additional participant (without running it).
        rules = competition_config.get("rules", {}) if isinstance(competition_config, dict) else {}
        lambda_value = args.lambda_value if args.lambda_value is not None else (
            rules.get("lambda", 100) if isinstance(rules, dict) else 100
        )
        codex_limit_tokens = args.codex_limit_tokens if args.codex_limit_tokens is not None else (
            competition_config.get("max_tokens_per_participant", 100000)
        )

        try:
            codex_participant_id = register_codex_participant(
                api_base=competition_config["api_base"],
                competition_id=competition_id,
                name=args.codex_name,
                api_base_url=args.codex_api_base,
                api_key=args.codex_api_key,
                limit_tokens=codex_limit_tokens,
                lambda_value=lambda_value,
            )
        except CodexRegistrationError as exc:
            logger.error(f"Failed to register Codex participant: {exc}")
            return

        logger.info(
            "Registered Codex participant '%s' with ID %s",
            args.codex_name,
            codex_participant_id,
        )

        env_lines = [
            f"COMPETITION_ID={competition_id}",
            f"PARTICIPANT_ID={codex_participant_id}",
            f"SERVER_BASE_URL={competition_config['api_base']}",
        ]

        env_path = Path(args.codex_env_output) if args.codex_env_output else Path(log_dir) / "codex_cli_env.txt"
        try:
            write_codex_env_file(env_path, env_lines)
            logger.info(f"Codex environment variables saved to {env_path}")
        except Exception as exc:
            logger.error(f"Failed to write Codex environment file {env_path}: {exc}")

        print("Codex CLI environment variables:")
        for line in env_lines:
            print(line)
        print(f"Saved to {env_path}")
        
        # Run competition
        logger.info("Starting competition...")
        results = await organizer.run_llm_competition()
        results_to_log = copy.deepcopy(results)

        # Save results to file
        save_competition_results(results, competition_id, competition_config, log_dir)


        log_competition_results(results_to_log, competition_id)
        
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
