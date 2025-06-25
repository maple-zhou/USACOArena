#!/usr/bin/env python3
"""
CompeteMAS 题目库扩展工具使用示例
演示如何使用备份和恢复功能安全地扩展题库
"""

from expand_problem_library import ProblemLibraryExpander
from pathlib import Path

def example_usage():
    """使用示例"""
    print("=== CompeteMAS 题目库扩展工具使用示例 ===\n")
    
    # 1. 初始化扩展器
    expander = ProblemLibraryExpander()
    
    # 2. 显示当前状态
    print("当前题库状态:")
    stats = expander.get_statistics()
    for level, count in stats["by_level"].items():
        print(f"  {level.capitalize()}: {count} 道题目")
    print(f"  总计: {stats['total_problems']} 道题目\n")
    
    # 3. 创建备份（重要！）
    print("步骤 1: 创建原题库备份")
    backup_name = expander.create_backup()
    print(f"备份创建成功: {backup_name}\n")
    
    # 4. 准备新题目数据
    print("步骤 2: 准备新题目数据")
    new_problems = {
        "999_bronze_example_problem": {
            "problem_data": {
                "name": "示例题目 - 两数之和",
                "problem_level": "bronze",
                "cp_id": "999",
                "problem_id": "999_bronze_example_problem",
                "description": "Problem: 两数之和\n\n给定两个整数 a 和 b，计算它们的和。\n\nINPUT FORMAT:\n* Line 1: 两个整数 a 和 b，用空格分隔。\n\nOUTPUT FORMAT:\n* Line 1: 一个整数，表示 a + b 的结果。\n\nSAMPLE INPUT:\n1 2\n\nSAMPLE OUTPUT:\n3",
                "description_no_samples": "Problem: 两数之和\n\n给定两个整数 a 和 b，计算它们的和。\n\nINPUT FORMAT:\n* Line 1: 两个整数 a 和 b，用空格分隔。\n\nOUTPUT FORMAT:\n* Line 1: 一个整数，表示 a + b 的结果。",
                "description_raw": "Problem: 两数之和\n\n给定两个整数 a 和 b，计算它们的和。",
                "input_format": "* Line 1: 两个整数 a 和 b，用空格分隔。",
                "output_format": "* Line 1: 一个整数，表示 a + b 的结果。",
                "runtime_limit": 1,
                "memory_limit": 256,
                "num_tests": 3,
                "num_samples": 1,
                "samples": [
                    {
                        "input": "1 2",
                        "output": "3",
                        "input_explanation": "输入两个整数 1 和 2",
                        "output_explanation": "1 + 2 = 3",
                        "explanation": "输入两个整数 1 和 2，计算它们的和：1 + 2 = 3"
                    }
                ],
                "solution": "#include <iostream>\nusing namespace std;\n\nint main() {\n    int a, b;\n    cin >> a >> b;\n    cout << a + b << endl;\n    return 0;\n}",
                "problem_link": "",
                "test_data_link": "",
                "solution_link": "",
                "contest_link": "",
                "inner_contest_link": "",
                "runtime_limit_sentences": [],
                "memory_limit_sentences": []
            },
            "test_cases": [
                {"input": "1 2", "output": "3"},
                {"input": "10 -5", "output": "5"},
                {"input": "1000000 2000000", "output": "3000000"}
            ]
        },
        "998_silver_example_problem": {
            "problem_data": {
                "name": "示例题目 - 数组求和",
                "problem_level": "silver",
                "cp_id": "998",
                "problem_id": "998_silver_example_problem",
                "description": "Problem: 数组求和\n\n给定一个长度为 N 的数组，计算所有元素的和。\n\nINPUT FORMAT:\n* Line 1: 一个整数 N (1 ≤ N ≤ 1000)\n* Lines 2..N+1: 每行一个整数，表示数组元素\n\nOUTPUT FORMAT:\n* Line 1: 一个整数，表示数组所有元素的和\n\nSAMPLE INPUT:\n3\n1\n2\n3\n\nSAMPLE OUTPUT:\n6",
                "description_no_samples": "Problem: 数组求和\n\n给定一个长度为 N 的数组，计算所有元素的和。\n\nINPUT FORMAT:\n* Line 1: 一个整数 N (1 ≤ N ≤ 1000)\n* Lines 2..N+1: 每行一个整数，表示数组元素\n\nOUTPUT FORMAT:\n* Line 1: 一个整数，表示数组所有元素的和",
                "description_raw": "Problem: 数组求和\n\n给定一个长度为 N 的数组，计算所有元素的和。",
                "input_format": "* Line 1: 一个整数 N (1 ≤ N ≤ 1000)\n* Lines 2..N+1: 每行一个整数，表示数组元素",
                "output_format": "* Line 1: 一个整数，表示数组所有元素的和",
                "runtime_limit": 2,
                "memory_limit": 256,
                "num_tests": 2,
                "num_samples": 1,
                "samples": [
                    {
                        "input": "3\n1\n2\n3",
                        "output": "6",
                        "input_explanation": "数组长度为3，元素为1, 2, 3",
                        "output_explanation": "1 + 2 + 3 = 6",
                        "explanation": "数组长度为3，元素为1, 2, 3，计算和：1 + 2 + 3 = 6"
                    }
                ],
                "solution": "#include <iostream>\nusing namespace std;\n\nint main() {\n    int n;\n    cin >> n;\n    \n    long long sum = 0;\n    for (int i = 0; i < n; i++) {\n        int x;\n        cin >> x;\n        sum += x;\n    }\n    \n    cout << sum << endl;\n    return 0;\n}",
                "problem_link": "",
                "test_data_link": "",
                "solution_link": "",
                "contest_link": "",
                "inner_contest_link": "",
                "runtime_limit_sentences": [],
                "memory_limit_sentences": []
            },
            "test_cases": [
                {"input": "3\n1\n2\n3", "output": "6"},
                {"input": "5\n10\n20\n30\n40\n50", "output": "150"}
            ]
        }
    }
    
    # 5. 保存新题目数据到文件
    example_file = "example_new_problems.json"
    import json
    with open(example_file, 'w', encoding='utf-8') as f:
        json.dump(new_problems, f, indent=2, ensure_ascii=False)
    print(f"新题目数据已保存到: {example_file}\n")
    
    # 6. 批量添加新题目
    print("步骤 3: 批量添加新题目")
    expander.add_problems_from_file(example_file, create_backup=False)  # 已经创建过备份了
    expander.save_changes()
    
    # 7. 显示更新后的状态
    print("\n步骤 4: 验证更新结果")
    stats = expander.get_statistics()
    print("更新后的题库状态:")
    for level, count in stats["by_level"].items():
        print(f"  {level.capitalize()}: {count} 道题目")
    print(f"  总计: {stats['total_problems']} 道题目")
    
    # 8. 验证新添加的题目
    print("\n步骤 5: 验证新题目完整性")
    for problem_id in new_problems.keys():
        expander.validate_problem(problem_id)
    
    # 9. 显示备份列表
    print("\n步骤 6: 查看备份列表")
    backups = expander.list_backups()
    if backups:
        print("可用备份:")
        for backup in backups:
            print(f"  {backup}")
    
    print("\n=== 示例完成 ===")
    print("现在你可以:")
    print("1. 运行比赛测试新题目")
    print("2. 如果需要恢复，使用备份功能")
    print("3. 继续添加更多题目")

if __name__ == "__main__":
    example_usage() 