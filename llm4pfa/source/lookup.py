import os

import lizard
from pathlib import Path

def extract_function_code(source_code, start_line, end_line, fun_name = None):
    if start_line == -1 and end_line == -1:
        return None
    if source_code is not None:
        code = ('\n'.join(source_code.split('\n')[int(start_line) - 1: int(end_line)]))
        if fun_name is not None:
            start_line_code = source_code.split('\n')[int(start_line) - 1]
            if start_line_code.startswith(fun_name) and int(start_line) - 2 >= 0:
                before_start_line = source_code.split('\n')[int(start_line) - 2]
                code = before_start_line + '\n' + code
        return code
    else:
        return None



def gen_function_info_from_code(filename, code):
    anal = lizard.analyze_file.analyze_source_code(filename, code)
    function_info = {}
    function_info['function_num'] = len(anal.function_list)
    # print(len(anal.function_list))
    function_info_dict = {}
    function_info_map = {}
    for fun in anal.function_list:
        temp_dict = {
            'long_name': fun.long_name,
            'nloc': fun.nloc,
            'token_count': fun.token_count,
            'full_parameters': fun.full_parameters,
            'parameters': fun.parameters,
            'parameter_count': fun.parameter_count,
            'start_line': fun.start_line,
            'end_line': fun.end_line,
            'name': fun.name,
            'filename': fun.filename,
            'length': fun.length,
            'code': extract_function_code(code, fun.start_line, fun.end_line, fun.name)
        }
        function_info_dict[fun.name] = temp_dict
        function_info_map[fun.long_name] = temp_dict
    function_info['function_info_dict'] = function_info_dict
    return function_info, function_info_map

def get_function_info_from_file(file_path):
    # file_path = f'./C/testcases/{cwe_name}/{file_name}'
    with open(file_path, 'r', encoding='utf-8') as fp:
        code = fp.read()
    # print(code)
    func_info = gen_function_info_from_code(file_path, code)
    return func_info

def get_func_body_in_repo_by_name(name):
    repo_path = Path(os.environ["PFA_SOURCE_ROOT"])
    for dir_path, dir_names, file_names in os.walk(repo_path):
        for file_name in file_names:
            if file_name.endswith('.c') or file_name.endswith('.cpp'):
                file_path = os.path.join(dir_path, file_name)
                func_info = get_function_info_from_file(file_path)[0]
                func_info_dict = func_info['function_info_dict']
                # print(func_info_dict.keys())
                # print(func_name)
                if name in func_info_dict:
                    return func_info_dict[name]['code']
                # return
    return None