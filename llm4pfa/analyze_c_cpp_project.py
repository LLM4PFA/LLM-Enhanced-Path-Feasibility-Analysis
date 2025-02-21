import os
import json
import lizard
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import sys
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('code_analysis.log'),
        logging.StreamHandler()
    ]
)

PROJECT_CONFIG = {
    'name': 'libav',
    'base_path': '/home/zqc/ytest',
    'max_workers': 4,  # Number of parallel processing threads
    'supported_extensions': ('.c', '.cpp', '.h', '.hpp', '.cc'),  # Supported file types
    'chunk_size': 1000  # Maximum number of functions to process at once to prevent memory overflow
}

def get_project_paths():
    """Generate project paths based on configuration."""
    try:
        project_name = PROJECT_CONFIG['name']
        base_path = PROJECT_CONFIG['base_path']
        return {
            'project_path': os.path.join(base_path, project_name),
            'output_path': os.path.join(base_path, project_name, f'{project_name}_function_info_list.json')
        }
    except KeyError as e:
        logging.error(f"Configuration error: Missing key {e}")
        sys.exit(1)

def extract_function_code(source_code: str, start_line: int, end_line: int) -> Optional[str]:
    """Extracts the function code from the source code given start and end lines."""
    try:
        if start_line == -1 or end_line == -1:
            return None
        lines = source_code.split('\n')
        return '\n'.join(lines[start_line - 1:end_line])
    except Exception as e:
        logging.warning(f"Error extracting function code: {e}")
        return None

def calculate_comment_density(code: str) -> float:
    """Calculate code comment density"""
    lines = code.split('\n')
    comment_lines = sum(1 for line in lines if line.strip().startswith(('/*', '*/', '//', '*')))
    return comment_lines / len(lines) if lines else 0

def analyze_file(file_path: str) -> Dict[str, Any]:
    """Analyzes a single C/C++ file to extract function information."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            code = file.read()

        analysis = lizard.analyze_file.analyze_source_code(file_path, code)
        
        function_info_dict = {}
        for function in analysis.function_list:
            function_code = extract_function_code(code, function.start_line, function.end_line)
            
            function_info = {
                'long_name': function.long_name,
                'nloc': function.nloc,
                'token_count': function.token_count,
                'cyclomatic_complexity': function.cyclomatic_complexity,
                'full_parameters': function.full_parameters,
                'parameters': function.parameters,
                'parameter_count': len(function.parameters),
                'start_line': function.start_line,
                'end_line': function.end_line,
                'name': function.name,
                'filename': file_path,
                'length': function.end_line - function.start_line + 1,
                'code': function_code,
                'comment_density': calculate_comment_density(function_code) if function_code else 0
            }
            #function_info_dict[function.name] = function_info
            # 如果函数名已存在，追加到列表中；否则创建新列表
            if function.name in function_info_dict:
                function_info_dict[function.name].append(function_info)
            else:
                function_info_dict[function.name] = [function_info]
        return function_info_dict
    except Exception as e:
        logging.error(f"Error analyzing file {file_path}: {e}")
        return {}

def analyze_project(repo_path: str) -> Dict[str, Any]:
    """Analyzes all C/C++ files in a project directory using parallel processing."""
    all_function_info = {}
    file_paths = []

    # 收集所有需要分析的文件
    for dirpath, _, filenames in os.walk(repo_path):
        for filename in filenames:
            if filename.endswith(PROJECT_CONFIG['supported_extensions']):
                file_paths.append(os.path.join(dirpath, filename))

    logging.info(f"Found {len(file_paths)} files to analyze")

    # 使用线程池并行处理文件
    with ThreadPoolExecutor(max_workers=PROJECT_CONFIG['max_workers']) as executor:
        future_to_file = {executor.submit(analyze_file, file_path): file_path 
                         for file_path in file_paths}
        
        for future in tqdm(as_completed(future_to_file), total=len(file_paths), 
                          desc="Analyzing files"):
            file_path = future_to_file[future]
            try:
                function_info = future.result()
                all_function_info.update(function_info)
            except Exception as e:
                logging.error(f"Error processing {file_path}: {e}")

    return all_function_info

def save_to_json(data: Dict[str, Any], output_path: str) -> None:
    """Saves the extracted function information to a JSON file."""
    try:
        with open(output_path, 'w', encoding='utf-8') as json_file:
            json.dump(data, json_file, indent=4)
        logging.info(f"Successfully saved analysis results to {output_path}")
    except Exception as e:
        logging.error(f"Error saving results: {e}")

if __name__ == "__main__":
    logging.info("Starting code analysis...")
    paths = get_project_paths()
    
    function_info = analyze_project(paths['project_path'])
    save_to_json(function_info, paths['output_path'])
    
    logging.info(f"Analysis completed. Results written to {paths['output_path']}")