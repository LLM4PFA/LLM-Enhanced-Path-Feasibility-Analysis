import re


def is_direct_dereference(variable_name, code_line):
    # 构建正则表达式，匹配直接显式的解引用以及函数调用中的解引用
    #pattern = rf'\b{re.escape(variable_name)}\s*->\s*\w+|\&\s*\w+\s*->\s*{re.escape(variable_name)}'
    pattern = fr'(\*\s*{variable_name}|&?\s*{variable_name}\s*->\s*\w+)'
    # 使用正则表达式匹配代码行
    match = re.search(pattern, code_line)

    # 如果匹配到，返回True，否则返回False
    return match is not None


def extract_function_name(variable_name, code_line):
    # Check if code_line is None or not a string
    if code_line is None or not isinstance(code_line, str):
        return None

    # 定义 C/C++ 常见控制流关键字
    keywords = {'if', 'while', 'for', 'switch', 'catch', 'return'}

    # 修改正则表达式以匹配最后一个函数调用
    pattern = rf'(?:[^(]*\([^)]*\))*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*((?:[^\(\)]|\((?:[^\(\)]|\([^()]*\))*\))*?)\b{re.escape(variable_name)}\b'
    match = re.search(pattern, code_line)

    if match:
        func_name = match.group(1)
        # 检查是否为关键字
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

    # 去除前导空白字符
    loc_text = loc_text.strip()

    # 修改正则表达式模式，确保捕获参数组
    # 第一步：匹配函数名；跳过包裹调用的控制流关键字
    func_pattern = r'\b(?!(?:if|while|for|switch|catch|sizeof)\b)([a-zA-Z_]\w*)\s*\('
    func_match = re.search(func_pattern, loc_text)
    if not func_match:
        return None

    # 第二步：从函数名匹配位置开始匹配参数列表
    function_name = func_match.group(1)
    start_pos = func_match.end() - 1  # 从左括号开始

    # 简化的参数匹配模式，只匹配从左括号开始的内容
    param_pattern = r'\((.*?)\)'
    param_match = re.search(param_pattern, loc_text[start_pos:])
    if not param_match:
        return None

    # 获取参数字符串并检查是否包含目标变量
    params = param_match.group(1)
    if variable_name not in params:
        return None

    # 添加参数预处理和清理
    param_list = []
    for param in params.split(','):
        param = param.strip()
        if not param:  # 跳过空参数
            continue
        # 分割参数并确保有内容后再获取最后一个元素
        param_parts = param.strip().split()
        if param_parts:  # 确保分割后的列表不为空
            cleaned_param = param_parts[-1].strip('*&')
            param_list.append(cleaned_param)

    try:
        position = param_list.index(variable_name)
        match = re.search(r'\((.*?)\)', new_function_body, re.DOTALL)
        if match:
            params_str = match.group(1)
            # 分割参数列表，忽略逗号内的空格
            params = [param.strip() for param in params_str.split(',')]
            if 0 <= position < len(params):
                # 提取参数名
                param_name = params[position].split()[-1].strip('*')
                return param_name
        return None
    except ValueError as e:
        print(f"Error: {e}")
        return None
