#!/usr/bin/env python3
"""
Script to set up a competition specifically for Claude Code participation.
Uses direct API calls with full configuration support (avoids complex dependencies).
"""

import json
import requests
import argparse
import sys
import os
from datetime import datetime

def load_config(config_path: str) -> dict:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"✗ Configuration file not found: {config_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON in configuration file {config_path}: {str(e)}")
        sys.exit(1)

def create_competition_direct(
    api_base: str,
    competition_config: dict,
    problem_ids: list
) -> str:
    """Create competition using direct API calls with full configuration"""
    title = competition_config.get("competition_title", "Claude Code Competition")
    print(f"Creating competition: {title}")

    # Prepare request data with full configuration
    data = {
        "title": title,
        "description": competition_config.get("competition_description", "Programming competition for Claude Code agent"),
        "problem_ids": problem_ids,
        "max_tokens_per_participant": competition_config.get("max_tokens_per_participant", 100000),
        "rules": competition_config.get("rules", {})
    }

    try:
        response = requests.post(
            f"{api_base}/api/competitions/create",
            json=data,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()

        result = response.json()
        if result.get("status") != "success":
            print(f"✗ API error: {result.get('message', 'Unknown error')}")
            return None

        competition_id = result.get("data", {}).get("competition", {}).get("id")
        if not competition_id:
            print(f"✗ Invalid API response: missing competition ID")
            return None

        print(f"✓ Competition created successfully: {competition_id}")

        # Log any problems that were not found
        not_found_problems = result.get("data", {}).get("not_found_problems", [])
        if not_found_problems:
            print(f"⚠ Problems not found: {', '.join(not_found_problems)}")

        return competition_id

    except requests.exceptions.RequestException as e:
        print(f"✗ API request failed: {e}")
        return None
    except Exception as e:
        print(f"✗ Failed to create competition: {e}")
        return None

def create_claude_participant(api_base: str, competition_id: str, config: dict) -> str:
    """Create Claude Code participant and return participant ID"""
    print(f"Creating Claude Code participant in competition {competition_id}")

    response = requests.post(f"{api_base}/api/participants/create/{competition_id}", json={
        "name": config["name"],
        "api_base_url": "",
        "api_key": "",
        "limit_tokens": config["limit_tokens"],
        "lambda_value": config.get("lambda_value", 100)
    })

    if response.status_code == 200:
        result = response.json()
        if result.get('status') == 'success':
            participant_id = result['data']['id']
            print(f"✓ Claude Code participant created: {participant_id}")
            return participant_id

    print(f"✗ Failed to create participant: {response.text}")
    return None

def verify_setup(api_base: str, competition_id: str) -> bool:
    """Verify the competition setup"""
    print(f"Verifying competition setup...")

    response = requests.get(f"{api_base}/api/competitions/get/{competition_id}?include_details=true")

    if response.status_code == 200:
        result = response.json()
        if result.get('status') == 'success':
            data = result['data']
            print(f"✓ Competition verified:")
            print(f"  - Title: {data['title']}")
            print(f"  - Problems: {len(data.get('problems', []))}")
            print(f"  - Participants: {len(data.get('participants', []))}")
            return True

    print(f"✗ Failed to verify competition: {response.text}")
    return False

def main():
    parser = argparse.ArgumentParser(description='Setup competition for Claude Code using full configuration')
    parser.add_argument('--api-base', default='http://localhost:5000',
                       help='API base URL (default: http://localhost:5000)')
    parser.add_argument('--port', type=int, help='Server port (overrides api-base port)')
    parser.add_argument('--competition-config',
                       default='config/competition_config.json',
                       help='Path to competition configuration file')
    parser.add_argument('--problems',
                       default='config/problems_main.json',
                       help='Path to problems JSON file')
    parser.add_argument('--participant-name', default='Claude Code Agent',
                       help='Name for Claude Code participant')
    parser.add_argument('--output', default='claude_competition_setup.json',
                       help='Output file for competition credentials')
    # Override options
    parser.add_argument('--title', help='Override competition title')
    parser.add_argument('--max-tokens', type=int, help='Override maximum tokens per participant')

    args = parser.parse_args()

    # Adjust API base if port specified
    if args.port:
        args.api_base = f"http://localhost:{args.port}"

    # Load configurations
    print(f"Loading competition config from: {args.competition_config}")
    competition_config = load_config(args.competition_config)

    print(f"Loading problems from: {args.problems}")
    problem_ids = load_config(args.problems)
    if not isinstance(problem_ids, list):
        print(f"✗ Problems file must contain a JSON array, got: {type(problem_ids)}")
        sys.exit(1)

    # Apply overrides
    if args.title:
        competition_config["competition_title"] = args.title
    if args.max_tokens:
        competition_config["max_tokens_per_participant"] = args.max_tokens
    if args.port:
        competition_config["api_base"] = args.api_base

    print(f"Loaded {len(problem_ids)} problems")
    print(f"Competition config: {competition_config.get('competition_title', 'Untitled')}")
    print(f"Max tokens: {competition_config.get('max_tokens_per_participant', 'Not specified')}")

    # Test server connection
    try:
        response = requests.get(f"{args.api_base}/api/system/oj-status")
        if response.status_code != 200:
            print(f"⚠ Warning: Server at {args.api_base} may not be running properly")
    except Exception as e:
        print(f"✗ Cannot connect to server at {args.api_base}: {e}")
        sys.exit(1)

    print("=" * 60)
    print(f"Setting up Claude Code competition on {args.api_base}")

    # Create competition using direct API calls with full configuration
    competition_id = create_competition_direct(
        args.api_base, competition_config, problem_ids
    )
    if not competition_id:
        sys.exit(1)

    # Create Claude Code participant using API directly (simpler than using organizer)
    participant_config = {
        "name": args.participant_name,
        "limit_tokens": competition_config.get("max_tokens_per_participant", 100000)
    }

    participant_id = create_claude_participant(args.api_base, competition_id, participant_config)
    if not participant_id:
        sys.exit(1)

    # Verify setup
    if not verify_setup(args.api_base, competition_id):
        sys.exit(1)

    # Save credentials
    credentials = {
        "setup_timestamp": datetime.now().isoformat(),
        "server_url": args.api_base,
        "competition_id": competition_id,
        "participant_id": participant_id,
        "competition_config_file": args.competition_config,
        "problems_file": args.problems,
        "competition_title": competition_config.get("competition_title", "Claude Code Competition"),
        "participant_name": args.participant_name,
        "max_tokens": competition_config.get("max_tokens_per_participant", 100000),
        "problem_count": len(problem_ids),
        "rules": competition_config.get("rules", {}),
        "claude_code_prompt": f"""I'm participating in a CompeteMAS programming competition in AUTONOMOUS MODE. My credentials are:
- Competition ID: {competition_id}
- Participant ID: {participant_id}
- Server URL: {args.api_base}

You are now in autonomous mode. Start the competition immediately without waiting for my input. Begin by checking your status and listing available problems, then continuously solve problems until the competition ends or you run out of tokens.

Take action NOW."""
    }

    with open(args.output, 'w') as f:
        json.dump(credentials, f, indent=2)

    print("=" * 60)
    print("✓ Competition setup completed successfully!")
    print(f"✓ Credentials saved to: {args.output}")
    print()
    print("Configuration used:")
    print(f"  - Competition config: {args.competition_config}")
    print(f"  - Problems file: {args.problems}")
    print(f"  - Scoring rules: Bronze({competition_config.get('rules', {}).get('scoring', {}).get('bronze', 'N/A')}), Silver({competition_config.get('rules', {}).get('scoring', {}).get('silver', 'N/A')}), Gold({competition_config.get('rules', {}).get('scoring', {}).get('gold', 'N/A')}), Platinum({competition_config.get('rules', {}).get('scoring', {}).get('platinum', 'N/A')})")
    print()
    print("Next steps:")
    print("1. Open Claude Code")
    print("2. Use this prompt to start competing:")
    print()
    print(credentials["claude_code_prompt"])
    print()
    print(f"Competition Details:")
    print(f"  - Competition ID: {competition_id}")
    print(f"  - Participant ID: {participant_id}")
    print(f"  - Max Tokens: {competition_config.get('max_tokens_per_participant', 100000):,}")
    print(f"  - Problems: {len(problem_ids)}")
    print(f"  - Hint costs: L0({competition_config.get('rules', {}).get('hint_tokens', {}).get('level_0', 'N/A')}), L1({competition_config.get('rules', {}).get('hint_tokens', {}).get('level_1', 'N/A')}), L2({competition_config.get('rules', {}).get('hint_tokens', {}).get('level_2', 'N/A')}), L3({competition_config.get('rules', {}).get('hint_tokens', {}).get('level_3', 'N/A')}), L4({competition_config.get('rules', {}).get('hint_tokens', {}).get('level_4', 'N/A')})")

if __name__ == "__main__":
    main()