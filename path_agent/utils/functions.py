"""Function call parsing, argument mapping, dereference lookup, and source retrieval."""

import os
import re
from pathlib import Path

import lizard


def is_direct_dereference(variable_name, code_line):

    #pattern = rf'\b{re.escape(variable_name)}\s*->\s*\w+|\&\s*\w+\s*->\s*{re.escape(variable_name)}'
    pattern = fr'(\*\s*{variable_name}|&?\s*{variable_name}\s*->\s*\w+)'

    match = re.search(pattern, code_line)


    return match is not None


def extract_function_name(variable_name, code_line):
    # Check if code_line is None or not a string
    if code_line is None or not isinstance(code_line, str):
        return None


    keywords = {'if', 'while', 'for', 'switch', 'catch', 'return'}


    pattern = rf'(?:[^(]*\([^)]*\))*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*((?:[^\(\)]|\((?:[^\(\)]|\([^()]*\))*\))*?)\b{re.escape(variable_name)}\b'
    match = re.search(pattern, code_line)

    if match:
        func_name = match.group(1)

        if func_name not in keywords:
            return func_name
    return None


def get_dereferenced_locations_plus(derefere, func_name, var_name):
    key = func_name + "@" + var_name
    location_lines = derefere.get(key)

    if location_lines is None:
        return None, None, None

    location_line = location_lines.get("location_line")

    if not location_line:
        return None, None, None

    line = location_line[0] if location_line else None
    return line,location_lines.get("line_number"),location_lines.get("file_uri")


def get_param_name(variable_name: str, loc_text: str, new_function_body):
    # Ensure loc_text and new_function_body are not None
    if loc_text is None or new_function_body is None:
        return None

    # Convert new_function_body to string if it's not already
    if not isinstance(new_function_body, str):
        new_function_body = str(new_function_body)


    loc_text = loc_text.strip()



    func_pattern = r'\b(?!(?:if|while|for|switch|catch|sizeof)\b)([a-zA-Z_]\w*)\s*\('
    func_match = re.search(func_pattern, loc_text)
    if not func_match:
        return None


    function_name = func_match.group(1)
    start_pos = func_match.end() - 1


    param_pattern = r'\((.*?)\)'
    param_match = re.search(param_pattern, loc_text[start_pos:])
    if not param_match:
        return None


    params = param_match.group(1)
    if variable_name not in params:
        return None


    param_list = []
    for param in params.split(','):
        param = param.strip()
        if not param:
            continue

        param_parts = param.strip().split()
        if param_parts:
            cleaned_param = param_parts[-1].strip('*&')
            param_list.append(cleaned_param)

    try:
        position = param_list.index(variable_name)
        match = re.search(r'\((.*?)\)', new_function_body, re.DOTALL)
        if match:
            params_str = match.group(1)

            params = [param.strip() for param in params_str.split(',')]
            if 0 <= position < len(params):

                param_name = params[position].split()[-1].strip('*')
                return param_name
        return None
    except ValueError as e:
        print(f"Error: {e}")
        return None


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
