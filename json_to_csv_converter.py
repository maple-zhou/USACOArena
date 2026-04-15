#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON competition results to CSV converter
Transform competition result JSON files into CSV format for analysis.
"""

import json
import csv
import sys
from pathlib import Path
from typing import Dict, List, Any


def flatten_solved_problems(solved_problems: List[Dict]) -> Dict[str, Any]:
    """
    Flatten the solved_problems list into a dictionary structure.
    """
    if not solved_problems:
        return {
            'solved_problem_count': 0,
            'solved_problems_summary': '',
            'first_solved_problem': '',
            'last_solved_problem': ''
        }

    problem_count = len(solved_problems)
    problem_summary = '; '.join([f"{p['problem_id']}({p['score']})" for p in solved_problems])
    first_problem = solved_problems[0]['problem_id'] if solved_problems else ''
    last_problem = solved_problems[-1]['problem_id'] if solved_problems else ''

    return {
        'solved_problem_count': problem_count,
        'solved_problems_summary': problem_summary,
        'first_solved_problem': first_problem,
        'last_solved_problem': last_problem
    }


def flatten_problem_stats(problem_stats: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten the problem_stats dictionary into CSV-friendly fields.
    """
    if not problem_stats:
        return {
            'total_problems_attempted': 0,
            'problems_solved': 0,
            'total_submissions': 0,
            'avg_submissions_per_problem': 0,
            'total_penalty': 0,
            'problems_first_ac': 0,
            'problem_details_summary': ''
        }

    total_problems_attempted = len(problem_stats)
    problems_solved = sum(1 for stats in problem_stats.values() if stats.get('solved', False))
    total_submissions = sum(stats.get('submission_count', 0) for stats in problem_stats.values())
    avg_submissions = round(total_submissions / total_problems_attempted, 2) if total_problems_attempted > 0 else 0
    total_penalty = sum(stats.get('penalty', 0) for stats in problem_stats.values())
    problems_first_ac = sum(1 for stats in problem_stats.values() if stats.get('is_first_ac', False))

    # Create summary of problem details
    details = []
    for problem_id, stats in problem_stats.items():
        detail = f"{problem_id}(subs:{stats.get('submission_count', 0)}, solved:{stats.get('solved', False)}, score:{stats.get('best_score', 0)})"
        details.append(detail)
    problem_details_summary = '; '.join(details)

    return {
        'total_problems_attempted': total_problems_attempted,
        'problems_solved': problems_solved,
        'total_submissions': total_submissions,
        'avg_submissions_per_problem': avg_submissions,
        'total_penalty': total_penalty,
        'problems_first_ac': problems_first_ac,
        'problem_details_summary': problem_details_summary
    }


def get_all_problem_ids(data: Dict[str, Any]) -> List[str]:
    """
    Collect every problem ID observed in participant problem_stats.
    """
    all_problem_ids = set()

    for participant_data in data.values():
        problem_stats = participant_data.get('problem_stats', {})
        if problem_stats:
            all_problem_ids.update(problem_stats.keys())

    # Sort to keep a stable column order
    return sorted(list(all_problem_ids))


def flatten_individual_problem_stats(problem_stats: Dict[str, Any], all_problem_ids: List[str]) -> Dict[str, Any]:
    """
    Generate per-problem statistic columns.
    """
    result = {}

    for problem_id in all_problem_ids:
        stats = problem_stats.get(problem_id, {})

        # Four statistical columns per problem
        result[f'{problem_id}_score'] = stats.get('best_score', 0)
        result[f'{problem_id}_passed_cases'] = stats.get('passed_test_cases', 0)
        result[f'{problem_id}_submissions'] = stats.get('submission_count', 0)
        result[f'{problem_id}_penalty'] = stats.get('penalty', 0)

    return result


def flatten_competition_rules(rules_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten competition rules into CSV-friendly fields.
    """
    result = {}

    # Handle scoring rules
    scoring = rules_data.get('scoring', {})
    result['rules_bronze_points'] = scoring.get('bronze', 0)
    result['rules_silver_points'] = scoring.get('silver', 0)
    result['rules_gold_points'] = scoring.get('gold', 0)
    result['rules_platinum_points'] = scoring.get('platinum', 0)

    # Handle bonus rules
    result['rules_bonus_for_first_ac'] = rules_data.get('bonus_for_first_ac', 0)

    # Handle penalty rules
    penalties = rules_data.get('penalties', {})
    result['rules_penalty_ac'] = penalties.get('AC', 0)
    result['rules_penalty_wa'] = penalties.get('WA', 0)
    result['rules_penalty_re'] = penalties.get('RE', 0)
    result['rules_penalty_ce'] = penalties.get('CE', 0)
    result['rules_penalty_tle'] = penalties.get('TLE', 0)
    result['rules_penalty_mle'] = penalties.get('MLE', 0)

    # Handle hint token rules
    hint_tokens = rules_data.get('hint_tokens', {})
    result['rules_hint_tokens_level_0'] = hint_tokens.get('level_0', 0)
    result['rules_hint_tokens_level_1'] = hint_tokens.get('level_1', 0)
    result['rules_hint_tokens_level_2'] = hint_tokens.get('level_2', 0)
    result['rules_hint_tokens_level_3'] = hint_tokens.get('level_3', 0)
    result['rules_hint_tokens_level_4'] = hint_tokens.get('level_4', 0)

    # Handle submission token rules
    submission_tokens = rules_data.get('submission_tokens', {})
    result['rules_submission_tokens_ac'] = submission_tokens.get('AC', 0)
    result['rules_submission_tokens_wa'] = submission_tokens.get('WA', 0)
    result['rules_submission_tokens_re'] = submission_tokens.get('RE', 0)
    result['rules_submission_tokens_ce'] = submission_tokens.get('CE', 0)
    result['rules_submission_tokens_tle'] = submission_tokens.get('TLE', 0)
    result['rules_submission_tokens_mle'] = submission_tokens.get('MLE', 0)

    # Handle test token rules
    test_tokens = rules_data.get('test_tokens', {})
    result['rules_test_tokens_default'] = test_tokens.get('default', 0)
    result['rules_test_tokens_per_test_case'] = test_tokens.get('per_test_case', 0)

    # Handle language multipliers
    language_multipliers = test_tokens.get('language_multipliers', {})
    result['rules_test_tokens_cpp_multiplier'] = language_multipliers.get('cpp', 0)
    result['rules_test_tokens_java_multiplier'] = language_multipliers.get('java', 0)
    result['rules_test_tokens_python_multiplier'] = language_multipliers.get('python', 0)

    # Handle lambda value
    result['rules_lambda'] = rules_data.get('lambda', 0)

    # Note: input_token_multipliers and output_token_multipliers contain extensive model-specific data
    # These are typically identical across participants and can be omitted
    # Add specific multipliers only when explicitly required

    return result


def convert_json_to_csv(json_file_path: str, csv_file_path: str = None) -> str:
    """
    Convert JSON file to CSV file

    Args:
        json_file_path: JSON file path
        csv_file_path: Output CSV file path, if None then auto-generate

    Returns:
        Generated CSV file path
    """
    # Read JSON file
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # If CSV file path is not specified, auto-generate
    if csv_file_path is None:
        json_path = Path(json_file_path)
        csv_file_path = json_path.with_suffix('.csv')

    # Get all problem IDs from all participants
    all_problem_ids = get_all_problem_ids(data)

    # Define base CSV column names
    base_fieldnames = [
        'name',                           # Participant name
        'participant_id',                 # Participant ID
        'competition_id',                 # Competition ID
        'LLM_tokens',                     # LLM tokens used
        'hint_tokens',                    # Hint tokens
        'submission_tokens',              # Submission tokens
        'test_tokens',                    # Test tokens used
        'limit_tokens',                   # Token limit
        'remaining_tokens',               # Remaining tokens
        'consumed_tokens',                # Consumed tokens
        'consumed_credit',                # Consumed tokens
        'submission_count',               # Submission count
        'accepted_count',                 # Accepted count
        'submission_penalty',             # Submission penalty
        'problem_pass_score',             # Problem pass score

        # New statistics fields
        'llm_inference_count',            # Total LLM inference calls
        'first_ac_score',                 # Score from being first to solve problems
        'problem_score',                  # Score from passing problems (excluding first AC bonus)

        # Detailed rule-based scoring breakdown
        'bronze_score',                   # Score from bronze problems
        'silver_score',                   # Score from silver problems
        'gold_score',                     # Score from gold problems
        'platinum_score',                 # Score from platinum problems
        'bonus_score',                    # First AC bonuses

        'score',                          # Total score
        'is_running',                     # Is running
        'termination_reason',             # Termination reason
        'solved_problem_count',           # Solved problem count
        'solved_problems_summary',        # Solved problems summary
        'first_solved_problem',           # First solved problem
        'last_solved_problem',            # Last solved problem

        # Per-problem statistics summary
        'total_problems_attempted',       # Total problems attempted
        'problems_solved',                # Number of problems solved
        'total_submissions',              # Total submissions across all problems
        'avg_submissions_per_problem',    # Average submissions per problem
        'total_penalty',                  # Total penalty across all problems
        'problems_first_ac',              # Number of problems where participant was first to solve
        'problem_details_summary'         # Detailed per-problem summary
    ]

    # Competition rules columns
    rules_fieldnames = [
        # Scoring rules
        'rules_bronze_points',            # Bronze problem points
        'rules_silver_points',            # Silver problem points
        'rules_gold_points',              # Gold problem points
        'rules_platinum_points',          # Platinum problem points
        'rules_bonus_for_first_ac',       # First AC bonus points

        # Penalty rules
        'rules_penalty_ac',               # AC penalty
        'rules_penalty_wa',               # WA penalty
        'rules_penalty_re',               # RE penalty
        'rules_penalty_ce',               # CE penalty
        'rules_penalty_tle',              # TLE penalty
        'rules_penalty_mle',              # MLE penalty

        # Hint token costs
        'rules_hint_tokens_level_0',      # Level 0 hint token cost
        'rules_hint_tokens_level_1',      # Level 1 hint token cost
        'rules_hint_tokens_level_2',      # Level 2 hint token cost
        'rules_hint_tokens_level_3',      # Level 3 hint token cost
        'rules_hint_tokens_level_4',      # Level 4 hint token cost

        # Submission token costs
        'rules_submission_tokens_ac',     # AC submission token cost
        'rules_submission_tokens_wa',     # WA submission token cost
        'rules_submission_tokens_re',     # RE submission token cost
        'rules_submission_tokens_ce',     # CE submission token cost
        'rules_submission_tokens_tle',    # TLE submission token cost
        'rules_submission_tokens_mle',    # MLE submission token cost

        # Test token costs
        'rules_test_tokens_default',      # Default test token cost
        'rules_test_tokens_per_test_case', # Per test case token cost
        'rules_test_tokens_cpp_multiplier', # C++ language multiplier for test tokens
        'rules_test_tokens_java_multiplier', # Java language multiplier for test tokens
        'rules_test_tokens_python_multiplier', # Python language multiplier for test tokens

        # Lambda value
        'rules_lambda'                    # Lambda value for token scoring
    ]

    # Generate individual problem columns
    individual_problem_fieldnames = []
    for problem_id in all_problem_ids:
        individual_problem_fieldnames.extend([
            f'{problem_id}_score',        # Problem score
            f'{problem_id}_passed_cases', # Passed test cases
            f'{problem_id}_submissions',  # Number of submissions
            f'{problem_id}_penalty'       # Problem penalty
        ])

    # Combine all fieldnames
    fieldnames = base_fieldnames + rules_fieldnames + individual_problem_fieldnames

    # Write CSV file
    with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        # Write header
        writer.writeheader()

        # Write data rows
        for participant_name, participant_data in data.items():
            # Flatten solved_problems
            solved_info = flatten_solved_problems(participant_data.get('solved_problems', []))

            # Flatten problem_stats
            problem_stats_info = flatten_problem_stats(participant_data.get('problem_stats', {}))

            # Flatten individual problem stats
            individual_problem_info = flatten_individual_problem_stats(
                participant_data.get('problem_stats', {}),
                all_problem_ids
            )

            # Extract competition rules data from participant data
            # The rules are spread into the participant data by competition_organizer.py
            rules_data = {}
            for key in ['scoring', 'bonus_for_first_ac', 'penalties', 'lambda', 'input_token_multipliers', 'output_token_multipliers']:
                if key in participant_data.get('rules', {}):
                    rules_data[key] = participant_data.get('rules', {})[key]

            # Handle token-related rules separately to avoid conflicts with participant consumption data
            # Only extract these if they are dictionaries (rules), not integers (consumption)
            for key in ['hint_tokens', 'submission_tokens', 'test_tokens']:
                if key in participant_data.get('rules', {}) and isinstance(participant_data.get('rules', {})[key], dict):
                    rules_data[key] = participant_data.get('rules', {})[key]

            # Flatten competition rules
            rules_info = flatten_competition_rules(rules_data)

            # Merge data
            row_data = {
                'name': participant_name,
                'participant_id': participant_data.get('participant_id', ''),
                'competition_id': participant_data.get('competition_id', ''),
                'LLM_tokens': participant_data.get('LLM_tokens', 0),
                'hint_tokens': participant_data.get('hint_tokens', 0),
                'submission_tokens': participant_data.get('submission_tokens', 0),
                'test_tokens': participant_data.get('test_tokens', 0),
                'limit_tokens': participant_data.get('limit_tokens', 0),
                'remaining_tokens': participant_data.get('remaining_tokens', 0),
                'consumed_tokens': participant_data.get('consumed_tokens', 0),
                "consumed_credit": participant_data.get('consumed_credit', 0),
                'submission_count': participant_data.get('submission_count', 0),
                'accepted_count': participant_data.get('accepted_count', 0),
                'submission_penalty': participant_data.get('submission_penalty', 0),
                'problem_pass_score': participant_data.get('problem_pass_score', 0),

                # New statistics fields
                'llm_inference_count': participant_data.get('llm_inference_count', 0),
                'first_ac_score': participant_data.get('first_ac_score', 0),
                'problem_score': participant_data.get('problem_score', 0),

                # Detailed rule-based scoring breakdown
                'bronze_score': participant_data.get('bronze_score', 0),
                'silver_score': participant_data.get('silver_score', 0),
                'gold_score': participant_data.get('gold_score', 0),
                'platinum_score': participant_data.get('platinum_score', 0),
                'bonus_score': participant_data.get('bonus_score', 0),

                'score': participant_data.get('score', 0),
                'is_running': participant_data.get('is_running', False),
                'termination_reason': participant_data.get('termination_reason', ''),
                **solved_info,
                **problem_stats_info,
                **rules_info,
                **individual_problem_info
            }

            writer.writerow(row_data)

    return str(csv_file_path)


def main():
    """
    Main function
    """
    if len(sys.argv) < 2:
        print("Usage: python json_to_csv_converter.py <json_file_path> [csv_file_path]")
        print("Example: python json_to_csv_converter.py competition_results.json")
        print("Example: python json_to_csv_converter.py competition_results.json output.csv")
        sys.exit(1)
    
    json_file_path = sys.argv[1]
    csv_file_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        output_path = convert_json_to_csv(json_file_path, csv_file_path)
        print(f"Conversion successful! CSV file saved to: {output_path}")
    except FileNotFoundError:
        print(f"Error: File not found {json_file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file format - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 