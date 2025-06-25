#!/usr/bin/env python3
"""
题目库扩展管理脚本
用于自动化添加新题目到 CompeteMAS 系统
支持备份原题库，安全扩展
"""

import json
import os
import shutil
import datetime
from typing import Dict, List, Optional
from pathlib import Path

class ProblemLibraryExpander:
    def __init__(self, base_path: str = "data/datasets"):
        self.base_path = Path(base_path)
        self.dict_path = self.base_path / "usaco_v2_dict.json"
        self.tests_path = self.base_path / "usaco_v3/tests"
        self.config_path = Path("config/all_problems.json")
        
        # 备份目录
        self.backup_dir = Path("backups")
        self.backup_dir.mkdir(exist_ok=True)
        
        # 加载现有数据
        self.load_existing_data()
    
    def create_backup(self) -> str:
        """
        创建原题库的备份
        
        Returns:
            str: 备份目录名称
        """
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"problem_library_backup_{timestamp}"
        backup_path = self.backup_dir / backup_name
        
        print(f"正在创建备份: {backup_path}")
        
        # 创建备份目录
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # 备份题目字典文件
        if self.dict_path.exists():
            shutil.copy2(self.dict_path, backup_path / "usaco_v2_dict.json")
            print(f"  ✓ 已备份题目字典文件")
        
        # 备份配置文件
        if self.config_path.exists():
            shutil.copy2(self.config_path, backup_path / "all_problems.json")
            print(f"  ✓ 已备份配置文件")
        
        # 备份测试用例目录
        if self.tests_path.exists():
            tests_backup = backup_path / "usaco_v3/tests"
            shutil.copytree(self.tests_path, tests_backup, dirs_exist_ok=True)
            print(f"  ✓ 已备份测试用例目录 ({len(list(self.tests_path.glob('*')))} 个题目)")
        
        print(f"备份完成: {backup_path}")
        return backup_name
    
    def restore_from_backup(self, backup_name: str):
        """
        从备份恢复题库
        
        Args:
            backup_name: 备份目录名称
        """
        backup_path = self.backup_dir / backup_name
        
        if not backup_path.exists():
            print(f"错误: 备份 {backup_name} 不存在")
            return False
        
        print(f"正在从备份恢复: {backup_path}")
        
        # 恢复题目字典文件
        backup_dict = backup_path / "usaco_v2_dict.json"
        if backup_dict.exists():
            shutil.copy2(backup_dict, self.dict_path)
            print(f"  ✓ 已恢复题目字典文件")
        
        # 恢复配置文件
        backup_config = backup_path / "all_problems.json"
        if backup_config.exists():
            shutil.copy2(backup_config, self.config_path)
            print(f"  ✓ 已恢复配置文件")
        
        # 恢复测试用例目录
        backup_tests = backup_path / "usaco_v3/tests"
        if backup_tests.exists():
            if self.tests_path.exists():
                shutil.rmtree(self.tests_path)
            shutil.copytree(backup_tests, self.tests_path)
            print(f"  ✓ 已恢复测试用例目录")
        
        # 重新加载数据
        self.load_existing_data()
        print(f"恢复完成")
        return True
    
    def list_backups(self) -> List[str]:
        """列出所有备份"""
        backups = []
        for item in self.backup_dir.iterdir():
            if item.is_dir() and item.name.startswith("problem_library_backup_"):
                backups.append(item.name)
        return sorted(backups, reverse=True)
    
    def load_existing_data(self):
        """加载现有的题目数据"""
        try:
            with open(self.dict_path, 'r', encoding='utf-8') as f:
                self.problem_dict = json.load(f)
            print(f"已加载 {len(self.problem_dict)} 道现有题目")
        except FileNotFoundError:
            print(f"题目字典文件未找到: {self.dict_path}")
            self.problem_dict = {}
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.all_problems = json.load(f)
            print(f"已加载 {len(self.all_problems)} 道配置题目")
        except FileNotFoundError:
            print(f"配置文件未找到: {self.config_path}")
            self.all_problems = []
    
    def add_problem(self, problem_id: str, problem_data: Dict, test_cases: List[Dict] = None):
        """
        添加新题目到题库
        
        Args:
            problem_id: 题目ID
            problem_data: 题目元数据
            test_cases: 测试用例列表 [{"input": "...", "output": "..."}]
        """
        # 检查题目是否已存在
        if problem_id in self.problem_dict:
            print(f"警告: 题目 {problem_id} 已存在，将被覆盖")
        
        # 1. 添加到题目字典
        self.problem_dict[problem_id] = problem_data
        
        # 2. 添加到配置列表
        if problem_id not in self.all_problems:
            self.all_problems.append(problem_id)
        
        # 3. 创建测试用例文件
        if test_cases:
            self.create_test_files(problem_id, test_cases)
        
        print(f"已添加题目: {problem_id}")
    
    def create_test_files(self, problem_id: str, test_cases: List[Dict]):
        """创建测试用例文件"""
        test_dir = self.tests_path / problem_id
        test_dir.mkdir(parents=True, exist_ok=True)
        
        for i, case in enumerate(test_cases, 1):
            # 创建输入文件
            input_file = test_dir / f"I.{i}"
            with open(input_file, 'w', encoding='utf-8') as f:
                f.write(case["input"])
            
            # 创建输出文件
            output_file = test_dir / f"O.{i}"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(case["output"])
        
        print(f"已创建 {len(test_cases)} 个测试用例文件")
    
    def add_problems_from_file(self, file_path: str, create_backup: bool = True):
        """
        从文件批量添加题目
        
        Args:
            file_path: 包含新题目数据的JSON文件路径
            create_backup: 是否在添加前创建备份
        """
        if create_backup:
            self.create_backup()
        
        print(f"正在从文件加载题目: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            problems_data = json.load(f)
        
        added_count = 0
        for problem_id, data in problems_data.items():
            problem_data = data.get("problem_data", {})
            test_cases = data.get("test_cases", [])
            self.add_problem(problem_id, problem_data, test_cases)
            added_count += 1
        
        print(f"批量添加完成，共添加 {added_count} 道题目")
    
    def save_changes(self):
        """保存所有更改"""
        # 保存题目字典
        with open(self.dict_path, 'w', encoding='utf-8') as f:
            json.dump(self.problem_dict, f, indent=2, ensure_ascii=False)
        
        # 保存配置列表
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.all_problems, f, indent=2)
        
        print(f"已保存更改:")
        print(f"  - 题目字典: {len(self.problem_dict)} 道题目")
        print(f"  - 配置列表: {len(self.all_problems)} 道题目")
    
    def validate_problem(self, problem_id: str) -> bool:
        """验证题目完整性"""
        # 检查题目字典
        if problem_id not in self.problem_dict:
            print(f"错误: 题目 {problem_id} 不在字典中")
            return False
        
        # 检查测试用例文件
        test_dir = self.tests_path / problem_id
        if not test_dir.exists():
            print(f"错误: 题目 {problem_id} 缺少测试用例目录")
            return False
        
        # 检查输入输出文件配对
        input_files = list(test_dir.glob("I.*"))
        output_files = list(test_dir.glob("O.*"))
        
        if len(input_files) != len(output_files):
            print(f"错误: 题目 {problem_id} 输入输出文件数量不匹配")
            return False
        
        print(f"题目 {problem_id} 验证通过")
        return True
    
    def list_problems_by_level(self, level: str = None) -> List[str]:
        """列出指定难度的题目"""
        if level:
            problems = [pid for pid, data in self.problem_dict.items() 
                       if data.get('problem_level', '').lower() == level.lower()]
        else:
            problems = list(self.problem_dict.keys())
        
        return sorted(problems)
    
    def get_statistics(self) -> Dict:
        """获取题库统计信息"""
        stats = {
            "total_problems": len(self.problem_dict),
            "by_level": {},
            "recent_additions": []
        }
        
        # 按难度统计
        for level in ["bronze", "silver", "gold", "platinum"]:
            problems = self.list_problems_by_level(level)
            stats["by_level"][level] = len(problems)
        
        return stats

def main():
    """主函数 - 演示如何使用扩展器"""
    expander = ProblemLibraryExpander()
    
    print("=== CompeteMAS 题目库扩展工具 ===")
    print("1. 创建备份")
    print("2. 从文件批量添加题目")
    print("3. 查看统计信息")
    print("4. 列出备份")
    print("5. 从备份恢复")
    print("6. 退出")
    
    while True:
        choice = input("\n请选择操作 (1-6): ").strip()
        
        if choice == "1":
            backup_name = expander.create_backup()
            print(f"备份创建成功: {backup_name}")
        
        elif choice == "2":
            file_path = input("请输入题目数据文件路径: ").strip()
            if Path(file_path).exists():
                expander.add_problems_from_file(file_path, create_backup=True)
                expander.save_changes()
            else:
                print(f"文件不存在: {file_path}")
        
        elif choice == "3":
            stats = expander.get_statistics()
            print("\n=== 题目库统计 ===")
            for level, count in stats["by_level"].items():
                print(f"{level.capitalize()}: {count} 道题目")
            print(f"总计: {stats['total_problems']} 道题目")
        
        elif choice == "4":
            backups = expander.list_backups()
            if backups:
                print("\n=== 可用备份 ===")
                for backup in backups:
                    print(f"  {backup}")
            else:
                print("没有找到备份")
        
        elif choice == "5":
            backups = expander.list_backups()
            if backups:
                print("\n=== 可用备份 ===")
                for i, backup in enumerate(backups, 1):
                    print(f"  {i}. {backup}")
                
                try:
                    idx = int(input("请选择备份编号: ")) - 1
                    if 0 <= idx < len(backups):
                        expander.restore_from_backup(backups[idx])
                        expander.save_changes()
                    else:
                        print("无效的备份编号")
                except ValueError:
                    print("请输入有效的数字")
            else:
                print("没有找到备份")
        
        elif choice == "6":
            print("退出程序")
            break
        
        else:
            print("无效选择，请输入 1-6")

if __name__ == "__main__":
    main() 