import json
import re
from LLM4Detection.m_agent.conditions_info import ContextHelper,Conditions
import clang.cindex

def extract_variable_name(condition):
    """Extract the variable name from a condition like 'res == NULL' or '!res'"""
    # Match 'res == NULL'
    match = re.match(r'\s*(\w+)\s*==\s*NULL\s*', condition)
    if match:
        return match.group(1)
    # Match '!res'
    match = re.match(r'\s*!(\w+)\s*', condition)
    if match:
        return match.group(1)
    return None

def convert_bug_on_to_if(line):
    """Convert BUG_ON or UNWINDER_BUG_ON to if statement and extract variable name"""
    # Replace BUG_ON and UNWINDER_BUG_ON with if
    line = line.replace('BUG_ON', 'if').replace('UNWINDER_BUG_ON', 'if').rstrip(';')
    # Extract condition part
    match = re.match(r'\s*if\s*\((.*)\)\s*', line)
    if match:
        condition = match.group(1)
        variable_name = extract_variable_name(condition)
        if variable_name:
            # Generate non-null constraint condition
            return f"{variable_name} ==0"
    return line

def find_complete_condition_start(lines, start_index):
    """Find the start index of a complete condition statement.
    
    Args:
        lines (list[str]): A list of lines from the file.
        start_index (int): The index of the line where the condition ends.
        
    Returns:
        int: The index of the start line of the complete condition statement.
    """
    # Initialize bracket counter
    bracket_count = 0
    
    # Traverse upwards from the given start line
    for i in range(start_index, -1, -1):
        line = lines[i]
        # Calculate the number of left and right brackets in current line
        left_brackets = line.count('(')
        right_brackets = line.count(')')
        
        # Update bracket counter
        bracket_count += left_brackets - right_brackets
        
        # If bracket counter is 0, we found the start line of complete condition
        if bracket_count == 0:
            return i
    
    # If no complete condition found, return -1
    return -1

def extract_condition_content(condition):
    """Extract the content inside the parentheses of if/else if statements"""
    match = re.search(r'\((.*)\)', condition)
    if match:
        return match.group(1).strip()
    return condition

def is_incomplete_condition(line):
    """Check if the condition line has unclosed parentheses"""
    return line.count('(') > line.count(')')

def complete_condition(line, lines, start_index):
    """Complete the condition line if it's split across multiple lines"""
    i = start_index
    line = line.strip()

    if line.startswith('} else if') or line.startswith('else if'):
        line = line.split('if', 1)[-1] if 'if' in line else line
        line = line.strip()
        line = "if " + line
    line = line.rstrip('{').strip()
    while is_incomplete_condition(line) and i < len(lines) - 1:
        i += 1
        next_line = lines[i].strip()
        if next_line.endswith('{'):
            next_line = next_line.rstrip('{').strip()
        line += ' ' + next_line
    return line

def extract_switch_cases(lines, start_index):
    """Extract conditions from switch-case statements"""
    cases = []
    switch_condition = None
    for i in range(start_index, -1, -1):
        line = lines[i].strip()
        if line.startswith('switch'):
            switch_condition = extract_condition_content(line)
            break
    line = lines[start_index].strip()
    if line.startswith('case'):
        case_condition = line.split('case', 1)[-1].split(':', 1)[0].strip()
        cases.append(case_condition)
    else:
        for i in range(start_index, -1, -1):
            line = lines[i].strip()
            if line.startswith('case'):
                case_condition = line.split('case', 1)[-1].split(':', 1)[0].strip()
                cases.append(case_condition)
            if line.startswith('switch'):
                break
    return switch_condition, cases


def extract_conditions_around_target_with_lines(lines, target_line_index, target_extract, var_name):
    """Extract nested conditions around a specific target line with their line numbers"""
    nested_conditions = []
    def is_if_statement(line):
        return line.strip().startswith('if') or line.strip().startswith('} else if')

    def split_conditions(condition):
        return re.split(r'&&', condition)

    def contains_var_name(condition, var_name):
        pattern = rf'(?<![\w\.\]])\b{re.escape(var_name)}\b(?![\w\.\[])'
        return re.search(pattern, condition) is not None

    # Check if the extracted line is complete
    if target_extract:
        if target_line_index >= len(lines):
            return []
        target_line = lines[target_line_index].strip()
        current_line_index = target_line_index
        
        if target_line.count('(') < target_line.count(')'):
            while target_line.count('(') < target_line.count(')') and current_line_index > 0:
                current_line_index -= 1
                last_line = lines[current_line_index].strip()
                target_line = last_line + ' ' + target_line
                
        if target_line.count('(') > target_line.count(')'):
            index = current_line_index
            while is_incomplete_condition(target_line) and index < len(lines) - 1:
                index += 1
                next_line = lines[index].strip()
                if next_line.endswith('{'):
                    next_line = next_line.rstrip('{').strip()
                target_line += ' ' + next_line

        if is_if_statement(target_line):
            condition_start = target_line.index('(') + 1
            condition_end = target_line.rindex(')')
            condition = target_line[condition_start:condition_end].strip()
            conditions = split_conditions(condition)
            for i in range(len(conditions)):
                cond = conditions[i]
                if contains_var_name(cond, var_name):
                    if i:
                        preceding_conditions = ' && '.join(c.strip() for c in conditions[:i])
                        extracted_condition = {
                            'condition': f'if ({preceding_conditions.strip()})',
                            'line_number': current_line_index
                        }
                        nested_conditions.append(extracted_condition)

    target_indent = len(lines[target_line_index]) - len(lines[target_line_index].lstrip('\t'))
    skip_if = False

    for i in range(target_line_index - 1, -1, -1):
        line = lines[i]
        stripped_line = line.strip()
        line_indent = len(line) - len(line.lstrip('\t'))

        if line_indent < target_indent:
            if stripped_line.startswith('} else if') or stripped_line.startswith('else if'):
                if skip_if:
                    continue
                nested_conditions.insert(0, {
                    'condition': complete_condition(line.strip(), lines, i),
                    'line_number': i
                })
                skip_if = True
                continue

            if stripped_line.startswith(('if', 'while', 'for','list_for_each','skb_list', 'kvm_for_each')):
                if skip_if:
                    skip_if = False
                    target_indent -= 1
                    continue
                nested_conditions.insert(0, {
                    'condition': complete_condition(line.strip(), lines, i),
                    'line_number': i
                })
                target_indent = line_indent

            if stripped_line.startswith('else') or (stripped_line.startswith('} else') and not stripped_line.startswith('} else if')):
                conditions = []
                for j in range(i - 1, -1, -1):
                    prev_line = lines[j]
                    prev_stripped_line = prev_line.strip()
                    prev_line_indent = len(prev_line) - len(prev_line.lstrip('\t'))
                    if prev_line_indent == line_indent and prev_stripped_line.startswith(('if', 'else if', '} else if')):
                        condition = complete_condition(prev_stripped_line, lines, j)
                        conditions.insert(0, condition)
                        if prev_stripped_line.startswith('if'):
                            break
                combined_condition = " && ".join([f"!({extract_condition_content(cond)})" for cond in conditions])
                nested_conditions.insert(0, {
                    'condition': "if(" + combined_condition + ")",
                    'line_number': i
                })
                skip_if = False
                target_indent -= 1
                continue

            if stripped_line.startswith('case') or stripped_line.startswith('default'):
                switch_condition, cases = extract_switch_cases(lines, i)
                if stripped_line.startswith('default'):
                    case_conditions = [f"{switch_condition} != {case}" for case in cases]
                    combined_condition = " && ".join(case_conditions)
                    nested_conditions.insert(0, {
                        'condition': "if(" + combined_condition + ")",
                        'line_number': i
                    })
                else:
                    case_value = stripped_line.split('case', 1)[-1].split(':', 1)[0].strip()
                    nested_conditions.insert(0, {
                        'condition': f"if({switch_condition} == {case_value})",
                        'line_number': i
                    })
                target_indent = line_indent

            if stripped_line.startswith('do'):
                do_condition = None
                for j in range(target_line_index + 1, len(lines)):
                    next_line = lines[j]
                    next_line_indent = len(next_line) - len(next_line.lstrip('\t'))
                    if next_line_indent == line_indent and next_line.strip().startswith('} while'):
                        do_condition = complete_condition(next_line.strip(), lines, j)
                        break
                if do_condition:
                    nested_conditions.insert(0, {
                        'condition': do_condition,
                        'line_number': i
                    })
                target_indent = line_indent

            if ':' in stripped_line and line_indent == 0 and not any(char.isalnum() for char in stripped_line.split(':')[1]) and target_extract:
                label_name = stripped_line.split(':')[0].strip()
                nested_conditions.insert(0, {
                    'condition': f'goto {label_name}',
                    'line_number': i
                })
                target_indent = line_indent
                continue
                
    return nested_conditions

def extract_conditions_around_target_old(lines, target_line_index, target_extract, var_name):
    """Extract nested conditions around a specific target line"""
    nested_conditions = []
    def is_if_statement(line):
        return line.strip().startswith('if') or line.strip().startswith('} else if')

    def split_conditions(condition):
        return re.split(r'&&', condition)

    def contains_var_name(condition, var_name):
        pattern = rf'(?<![\w\.\]])\b{re.escape(var_name)}\b(?![\w\.\[])'
        return re.search(pattern, condition) is not None

    # Check if the extracted line is complete
    if target_extract:
        target_line = lines[target_line_index].strip()
        if target_line.count('(') < target_line.count(')'):
            # Look upwards for the complete line
            while target_line.count('(') < target_line.count(')') and target_line_index > 0:
                target_line_index -= 1
                last_line = lines[target_line_index].strip()
                target_line = last_line + ' ' + target_line
        if target_line.count('(') > target_line.count(')'):
            index = target_line_index
            while is_incomplete_condition(target_line) and index < len(lines) - 1:
                index += 1
                next_line = lines[index].strip()
                if next_line.endswith('{'):
                    next_line = next_line.rstrip('{').strip()
                target_line += ' ' + next_line

        if is_if_statement(target_line):
            # print(target_line)
            # Extract the condition inside the if statement
            condition_start = target_line.index('(') + 1
            condition_end = target_line.rindex(')')
            condition = target_line[condition_start:condition_end].strip()
            conditions = split_conditions(condition)
            for i in range(len(conditions)):
                cond = conditions[i]
                if contains_var_name(cond, var_name):
                    if i:
                        preceding_conditions = ' && '.join(c.strip() for c in conditions[:i])
                        extracted_condition = f'if ({preceding_conditions.strip()})'
                        nested_conditions.append(extracted_condition) 

    target_indent = len(lines[target_line_index]) - len(lines[target_line_index].lstrip('\t '))
    skip_if = False

    for i in range(target_line_index - 1, -1, -1):
        line = lines[i]
        stripped_line = line.strip()
        line_indent = len(line) - len(line.lstrip('\t '))

        if line_indent < target_indent:
            if stripped_line.startswith('} else if') or stripped_line.startswith('else if'):
                if skip_if:
                    continue
                nested_conditions.insert(0, complete_condition(line.strip(), lines, i))
                skip_if = True
                continue

            if stripped_line.startswith(('if', 'while', 'for','list_for_each','skb_list', 'kvm_for_each')):
                if skip_if:
                    skip_if = False
                    target_indent -= 1
                    continue
                nested_conditions.insert(0, complete_condition(line.strip(), lines, i))
                target_indent = line_indent

            if stripped_line.startswith('else') or (stripped_line.startswith('} else') and not stripped_line.startswith('} else if')):
                conditions = []
                for j in range(i - 1, -1, -1):
                    prev_line = lines[j]
                    prev_stripped_line = prev_line.strip()
                    prev_line_indent = len(prev_line) - len(prev_line.lstrip('\t'))
                    if prev_line_indent == line_indent and prev_stripped_line.startswith(('if', 'else if', '} else if')):
                        condition = complete_condition(prev_stripped_line, lines, j)
                        conditions.insert(0, condition)
                        if prev_stripped_line.startswith('if'):
                            break
                combined_condition = " && ".join([f"!({extract_condition_content(cond)})" for cond in conditions])
                combined_condition = "if(" + combined_condition + ")"
                nested_conditions.insert(0, combined_condition)
                skip_if = False
                target_indent -= 1
                continue

            if stripped_line.startswith('case') or stripped_line.startswith('default'):
                switch_condition, cases = extract_switch_cases(lines, i)
                if stripped_line.startswith('default'):
                    case_conditions = [f"{switch_condition} != {case}" for case in cases]
                    combined_condition = " && ".join(case_conditions)
                    combined_condition = "if(" + combined_condition + ")"
                else:
                    case_value = stripped_line.split('case', 1)[-1].split(':', 1)[0].strip()
                    combined_condition = f"if({switch_condition} == {case_value})"
                target_indent = line_indent 
                nested_conditions.insert(0, combined_condition)

            if stripped_line.startswith('do'):
                do_condition = None
                for j in range(target_line_index + 1, len(lines)):
                    next_line = lines[j]
                    next_line_indent = len(next_line) - len(next_line.lstrip('\t'))
                    if next_line_indent == line_indent and next_line.strip().startswith('} while'):
                        do_condition = complete_condition(next_line.strip(), lines, j)
                        break
                if do_condition:
                    nested_conditions.insert(0, do_condition)
                target_indent = line_indent

            if ':' in stripped_line and line_indent == 0 and not any(char.isalnum() for char in stripped_line.split(':')[1]) and target_extract:
                label_name = stripped_line.split(':')[0].strip()
                nested_conditions.insert(0, f'goto {label_name}')
                target_indent = line_indent
                continue
    return nested_conditions

def extract_return_goto_conditions2(lines,assignment_line_index,target_line_index, var_name):
    """Extract nested conditions for all return and goto statements"""
    conditions = []
    for i, line in enumerate(lines):
        if line.strip().startswith(('return', 'goto')) and i > assignment_line_index and i < target_line_index:
            nested_conditions = extract_conditions_around_target(lines, i, False, var_name)
            conditions.append({"text": line.strip(), "condition": nested_conditions})
    return conditions

def extract_return_goto_conditions(translation_unit, start_line,end_line, var_name):
    """Extract nested conditions for all return and goto statements"""
    conditions = []
    # Get labels between two lines
    fro_target_labels = get_labels_in_range(translation_unit.cursor,start_line,end_line)
    # Get jump statements between two lines
    result = find_constraints_goto(translation_unit.cursor,start_line,end_line)
    for res in result:
        target_label = res['targetLabel']
        if target_label not in fro_target_labels:
            conditions.append({"text": res['lineCode'], "condition": res['conditions']})
    
    return conditions

def get_labels_in_range(node, start_line, end_line):
    labels = []

    def visit(node):
        # Check if node is a label
        if node.kind == clang.cindex.CursorKind.LABEL_STMT:
            # Get label line number
            label_line = node.location.line
            if start_line <= label_line <= end_line:
                labels.append(node.spelling)

        # Recursively traverse child nodes
        for child in node.get_children():
            visit(child)

    visit(node)
    return labels

def extract_conditions_around_target_v2(lines, target_line_index, target_extract, var_name):
    """Extract nested conditions around a specific target line"""
    nested_conditions = []
    
    def is_if_statement(line):
        return line.strip().startswith('if') or line.strip().startswith('} else if')

    def split_conditions(condition):
        # Improved condition splitting, preserving complete parentheses
        parts = []
        current = []
        paren_count = 0
        
        for char in condition:
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
                
            if char == '&' and paren_count == 0:
                if current and current[-1] == '&':
                    parts.append(''.join(current[:-1]))
                    current = []
                    continue
            current.append(char)
            
        if current:
            parts.append(''.join(current))
        return [p.strip() for p in parts if p.strip()]

    def contains_var_name(condition, var_name):
        # Improved variable name matching
        pattern = rf'(?<![a-zA-Z0-9_]){re.escape(var_name)}(?![a-zA-Z0-9_])'
        return re.search(pattern, condition) is not None

    def is_incomplete_condition(line):
        return line.count('(') != line.count(')')

    def complete_condition(line, lines, index):
        """Complete a multi-line condition statement"""
        if not line:
            return ""
            
        # Handle case where line starts with } else if
        if line.startswith('} else if'):
            line = line[1:].strip()
            
        # Extract condition inside parentheses
        try:
            start = line.index('(')
            condition = line[start:]
            current_index = index
            
            # Handle multi-line conditions
            while is_incomplete_condition(condition) and current_index < len(lines) - 1:
                current_index += 1
                next_line = lines[current_index].strip()
                if next_line.endswith('{'):
                    next_line = next_line[:-1].strip()
                condition += ' ' + next_line
                
            # Ensure extracted content inside parentheses
            if '(' in condition and ')' in condition:
                paren_count = 0
                end_pos = 0
                for i, char in enumerate(condition):
                    if char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
                        if paren_count == 0:
                            end_pos = i
                            break
                            
                if end_pos > 0:
                    return condition[1:end_pos].strip()
                    
        except ValueError:
            pass
            
        return ""

    def extract_condition_content(condition):
        """Extract the actual condition from an if statement"""
        try:
            if '(' in condition and ')' in condition:
                start = condition.index('(') + 1
                end = condition.rindex(')')
                return condition[start:end].strip()
        except ValueError:
            pass
        return condition

    def extract_switch_cases(lines, case_index):
        """Extract switch condition and all case values"""
        switch_condition = None
        cases = []
        
        # Look up for switch statement
        for i in range(case_index - 1, -1, -1):
            line = lines[i].strip()
            if line.startswith('switch'):
                switch_condition = complete_condition(line, lines, i)
                break
                
        # Collect all case values
        i = case_index - 1
        while i >= 0:
            line = lines[i].strip()
            if line.startswith('case'):
                case_value = line.split('case', 1)[1].split(':', 1)[0].strip()
                cases.append(case_value)
            elif line.startswith('switch'):
                break
            i -= 1
            
        return switch_condition, cases

    # Process target line if requested
    if target_extract and target_line_index < len(lines):
        target_line = lines[target_line_index]
        if not target_line.strip():
            return []
            
        # Process multi-line target statement
        full_target_line = target_line
        temp_index = target_line_index
        
        # Search upwards for incomplete conditions
        while temp_index > 0 and target_line.count(')') > target_line.count('('):
            temp_index -= 1
            prev_line = lines[temp_index].strip()
            full_target_line = prev_line + ' ' + full_target_line
            
        # Search downwards for incomplete conditions
        temp_index = target_line_index
        while temp_index < len(lines) - 1 and full_target_line.count('(') > full_target_line.count(')'):
            temp_index += 1
            next_line = lines[temp_index].strip()
            if next_line.endswith('{'):
                next_line = next_line[:-1].strip()
            full_target_line += ' ' + next_line

        if is_if_statement(full_target_line):
            condition = complete_condition(full_target_line, lines, target_line_index)
            if condition:
                conditions = split_conditions(condition)
                for i, cond in enumerate(conditions):
                    if contains_var_name(cond, var_name):
                        if i > 0:
                            preceding_conditions = ' && '.join(conditions[:i])
                            nested_conditions.append(f'if ({preceding_conditions})')

    # Get target line indent level
    target_indent = len(lines[target_line_index]) - len(lines[target_line_index].lstrip())
    current_indent = target_indent
    skip_if = False

    # Scan upwards for conditions
    for i in range(target_line_index - 1, -1, -1):
        line = lines[i]
        stripped_line = line.strip()
        if not stripped_line:
            continue
            
        line_indent = len(line) - len(line.lstrip())

        if line_indent < current_indent:
            current_indent = line_indent
            
            # Handle control structures
            if any(stripped_line.startswith(keyword) for keyword in ['if', 'while', 'for', '} else if', 'else if']):
                condition = complete_condition(stripped_line, lines, i)
                if condition and contains_var_name(condition, var_name):
                    nested_conditions.insert(0, f'if ({condition})')
                    if stripped_line.startswith(('} else if', 'else if')):
                        skip_if = True
                    elif stripped_line.startswith('if'):
                        skip_if = False
                        
            # Handle else blocks
            elif stripped_line.startswith(('else', '} else')) and not stripped_line.startswith('} else if'):
                conditions = []
                j = i - 1
                while j >= 0:
                    prev_line = lines[j].strip()
                    prev_indent = len(lines[j]) - len(lines[j].lstrip())
                    if prev_indent == line_indent and prev_line.startswith(('if', 'else if', '} else if')):
                        condition = complete_condition(prev_line, lines, j)
                        if condition:
                            conditions.insert(0, condition)
                        if prev_line.startswith('if'):
                            break
                    j -= 1
                    
                if conditions:
                    combined_condition = " && ".join([f"!({cond})" for cond in conditions])
                    nested_conditions.insert(0, f"if ({combined_condition})")
                    
            # Handle switch/case statements
            elif stripped_line.startswith(('case', 'default')):
                switch_condition, cases = extract_switch_cases(lines, i)
                if switch_condition:
                    if stripped_line.startswith('default'):
                        case_conditions = [f"{switch_condition} != {case}" for case in cases]
                        combined_condition = " && ".join(case_conditions)
                        nested_conditions.insert(0, f"if ({combined_condition})")
                    else:
                        case_value = stripped_line.split('case', 1)[1].split(':', 1)[0].strip()
                        nested_conditions.insert(0, f"if ({switch_condition} == {case_value})")

            # Handle goto labels
            elif ':' in stripped_line and line_indent == 0:
                label_part = stripped_line.split(':')[1].strip()
                if not label_part or not any(char.isalnum() for char in label_part):
                    if target_extract:
                        label_name = stripped_line.split(':')[0].strip()
                        nested_conditions.insert(0, f'goto {label_name}')

    return nested_conditions

def extract_return_goto_conditions2(lines, target_line_index, var_name):
    """Extract conditions for return and goto statements"""
    statements = []
    
    def is_incomplete_condition(line):
        return line.count('(') != line.count(')')
        
    def get_indent_level(line):
        return len(line) - len(line.lstrip())
        
    def contains_var_name(condition, var_name):
        pattern = rf'(?<![a-zA-Z0-9_]){re.escape(var_name)}(?![a-zA-Z0-9_])'
        return re.search(pattern, condition) is not None
        
    def complete_condition(line, lines, index):
        """Complete a multi-line condition statement"""
        if not line:
            return ""
            
        # Handle case where line starts with } else if
        if line.startswith('} else if'):
            line = line[1:].strip()
            
        # Extract condition inside parentheses
        try:
            start = line.index('(')
            condition = line[start:]
            current_index = index
            
            # Handle multi-line conditions
            while is_incomplete_condition(condition) and current_index < len(lines) - 1:
                current_index += 1
                next_line = lines[current_index].strip()
                if next_line.endswith('{'):
                    next_line = next_line[:-1].strip()
                condition += ' ' + next_line
                
            # Ensure extracted content inside parentheses
            if '(' in condition and ')' in condition:
                paren_count = 0
                end_pos = 0
                for i, char in enumerate(condition):
                    if char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
                        if paren_count == 0:
                            end_pos = i
                            break
                            
                if end_pos > 0:
                    return condition[1:end_pos].strip()
                    
        except ValueError:
            pass
            
        return ""

    def get_controlling_conditions(lines, start_index, target_indent):
        """Get all controlling conditions for a given line"""
        conditions = []
        current_indent = target_indent
        i = start_index
        
        while i >= 0:
            line = lines[i].strip()
            if not line:
                i -= 1
                continue
                
            line_indent = get_indent_level(lines[i])
            
            if line_indent < current_indent:
                current_indent = line_indent
                
                # Handle if/else if chains
                if any(line.startswith(keyword) for keyword in ['if', 'else if', '} else if']):
                    condition = complete_condition(line, lines, i)
                    if condition:
                        conditions.insert(0, condition)
                        
                # Handle else blocks
                elif line.startswith(('else', '} else')) and not line.startswith('} else if'):
                    j = i - 1
                    else_conditions = []
                    while j >= 0:
                        prev_line = lines[j].strip()
                        prev_indent = get_indent_level(lines[j])
                        if prev_indent == line_indent and prev_line.startswith(('if', 'else if', '} else if')):
                            cond = complete_condition(prev_line, lines, j)
                            if cond:
                                else_conditions.insert(0, f"!({cond})")
                            if prev_line.startswith('if'):
                                break
                        j -= 1
                    if else_conditions:
                        conditions.insert(0, ' && '.join(else_conditions))
                        
                # Handle while/for loops
                elif any(line.startswith(keyword) for keyword in ['while', 'for']):
                    condition = complete_condition(line, lines, i)
                    if condition:
                        conditions.insert(0, condition)
                        
            i -= 1
            
        return conditions

    # Get target line indent level
    target_indent = get_indent_level(lines[target_line_index])
    
    # Scan upwards for return and goto statements
    i = target_line_index
    while i >= 0:
        line = lines[i].strip()
        if not line:
            i -= 1
            continue
            
        line_indent = get_indent_level(lines[i])
        if ('BUG_ON' in line or 'UNWINDER_BUG_ON' in line) and target_indent ==  line_indent:
            controlling_conditions = []
            controlling_conditions.insert(0,convert_bug_on_to_if(line))
        
            # controlling_conditions.append(get_controlling_conditions(lines, i-1, line_indent))
            statements.append({'text': 'return', 'condition': controlling_conditions})
        
        # Check return statement
        if line.startswith('return'):
            controlling_conditions = get_controlling_conditions(lines, i-1, line_indent)
            statement = {
                'text': 'return',
                'condition': controlling_conditions
            }
            statements.append(statement)
            
        # Check goto statement
        elif 'goto' in line:
            # Extract goto label
            try:
                goto_label = line.split('goto')[1].strip().rstrip(';')
                controlling_conditions = get_controlling_conditions(lines, i-1, line_indent)
                statement = {
                    'text': goto_label,
                    'condition': controlling_conditions
                }
                statements.append(statement)
            except:
                pass
                
        # Check break statement
        elif line.startswith('break'):
            controlling_conditions = get_controlling_conditions(lines, i-1, line_indent)
            statement = {
                'text': 'break',
                'condition': controlling_conditions
            }
            statements.append(statement)
            
        i -= 1
        
    return statements

def extract_return_goto_conditions(translation_unit, start_line,end_line, var_name):
    """Extract nested conditions for all return and goto statements"""
    conditions = []
    # Get labels between two lines
    fro_target_labels = get_labels_in_range(translation_unit.cursor,start_line,end_line)
    # Get jump statements between two lines
    result = find_constraints_goto(translation_unit.cursor,start_line,end_line)
    for res in result:
        target_label = res['targetLabel']
        if target_label not in fro_target_labels:
            conditions.append({"text": res['lineCode'], "condition": res['conditions']})
    return conditions

def get_labels_in_range(node, start_line, end_line):
    labels = []

    def visit(node):
        # Check if node is a label
        if node.kind == clang.cindex.CursorKind.LABEL_STMT:
            # Get label line number
            label_line = node.location.line
            if start_line <= label_line <= end_line:
                labels.append(node.spelling)

        # Recursively traverse child nodes
        for child in node.get_children():
            visit(child)

    visit(node)
    return labels

def extract_var_non_empty_conditions(translation_unit, start_line,end_line, var_name):
   
    conditions = []
    if_statements = find_statements_between_lines(translation_unit.cursor, start_line, end_line)

    # Filter out if statements that check if var_name is non-empty
    filtered_if_statements = filter_if_statements(if_statements, var_name)

    for if_stmt in filtered_if_statements:
        condition,if_parts, else_parts = extract_if_else(if_stmt)
        conditions.append({"text": "", "condition": condition, "content": if_parts, "else_content": else_parts})

    return conditions

def extract_if_else(if_stmt):
    # children is the child block, index 0 is the if condition, 1 is the if curly brace part, 2 is the else curly brace part, if it is else-if, then else is the if block as a child
    children = list(if_stmt.get_children())
    else_parts = ''
    if_parts = ''
    
    if len(children) >= 2:
        if_parts = extract_code(children[1])
        if len(children) == 3:
            else_node = children[2]
            if else_node.kind == clang.cindex.CursorKind.IF_STMT:
                sub_condition,sub_if_parts, sub_else_parts = extract_if_else(else_node)
                else_parts = sub_else_parts
            else:
                else_parts = extract_code(else_node)
    
    return extract_code(children[0]),if_parts, else_parts

def find_ifdef_range(file_path, target_line):
    index = clang.cindex.Index.create()
    translation_unit = index.parse(file_path)

    tokens = list(translation_unit.get_tokens(extent=translation_unit.cursor.extent))
    token_iter = iter(tokens)

    directive_stack = []

    for token in token_iter:
        if token.kind == clang.cindex.TokenKind.PUNCTUATION and token.spelling == '#':
            try:
                directive_token = next(token_iter)
                directive = directive_token.spelling

                if directive in ['ifdef', 'ifndef', 'if']:
                    condition_tokens = []
                    if directive == 'if':
                        for next_token in token_iter:
                            if next_token.kind == clang.cindex.TokenKind.PUNCTUATION and next_token.spelling == '#':
                                break
                            condition_tokens.append(next_token.spelling)
                        condition = ' '.join(condition_tokens)
                    else:
                        macro_token = next(token_iter)
                        condition = macro_token.spelling

                    directive_stack.append((directive, condition, token.location.line))
                elif directive in ['endif', 'else', 'elif']:
                    if directive_stack:
                        start_directive, condition, start_line = directive_stack.pop()
                        if start_line <= target_line <= token.location.line:
                            nested_conditions = [condition]
                            while directive_stack:
                                nested_directive, nested_condition, nested_start_line = directive_stack.pop()
                                if nested_start_line <= start_line:
                                    break
                                nested_conditions.append(nested_condition)
                            nested_conditions.reverse()

                            return {
                                "directives": [start_directive] + [d for d, _, _ in directive_stack],
                                "conditions": nested_conditions,
                                "range": (start_line, token.location.line),
                                "condition": ' AND '.join(nested_conditions)
                            }

            except StopIteration:
                print("Reached end of tokens unexpectedly.")
                continue

    return None

def find_function_start(cursor, end_line):
    """
    Find the start line number of the function containing the specified line number.
    :param cursor: Root node of AST (translation_unit.cursor).
    :param end_line: Target line number, representing a line in the function we want to find.
    :return: Start line number of the function, or None if not found.
    """
    # Traverse AST, find function node
    for node in cursor.walk_preorder():
        # If it's a function definition (CXXMethod or FunctionDecl)
        if node.kind in [clang.cindex.CursorKind.FUNCTION_DECL]:
        # if node.kind in [clang.cindex.CursorKind.FUNCTION_DECL, clang.cindex.CursorKind.CXX_METHOD]:
            start_line = node.extent.start.line
            end_line_node = node.extent.end.line
            # Check if target line number is within the function's range
            if start_line <= end_line <= end_line_node:
                return start_line
    return None

def find_statements_between_lines(node, start_line, end_line, if_statements=None):
    """ Find all if blocks between two lines """
    if if_statements is None:
        if_statements = []
    
    if node.location.line > start_line and node.location.line < end_line:
        # If the node is an IF statement and is between the start and end lines
        if node.kind == clang.cindex.CursorKind.IF_STMT:
            if_statements.append(node)

    # Recursively process children
    for child in node.get_children():
        find_statements_between_lines(child, start_line, end_line, if_statements)

    return if_statements

def find_constraints_goto(node, start_line, end_line, results=None, conditions=None):
    if results is None:
        results = []
    if conditions is None:
        conditions = []
        
    # Check if the line number of the node is within the target range
    if start_line <= node.extent.start.line <= end_line:
        # If it's a goto statement, get target label name
        if node.kind == clang.cindex.CursorKind.GOTO_STMT:
            target_label = node.referenced.spelling if node.referenced else 'Unknown'
            results.append({
                'line': node.extent.start.line,
                'lineCode': extract_code(node),
                'col': node.extent.start.column,
                'kind': node.kind,
                'targetLabel': target_label,  # Add target label name
                'conditions': list(conditions)  # Copy current conditions
            })
        # If it's a return statement, add directly
        elif node.kind == clang.cindex.CursorKind.RETURN_STMT:
            results.append({
                'line': node.extent.start.line,
                'lineCode': extract_code(node),
                'col': node.extent.start.column,
                'kind': node.kind,
                'targetLabel': "",
                'conditions': list(conditions)  # Copy current conditions
            })
    
    # If current node is a condition statement, add to condition stack
    if node.kind in (clang.cindex.CursorKind.IF_STMT, clang.cindex.CursorKind.WHILE_STMT,
                     clang.cindex.CursorKind.FOR_STMT, clang.cindex.CursorKind.SWITCH_STMT):
        children = list(node.get_children())
        condition_code = extract_code(children[0])
        conditions.append(condition_code)
    
    # Recursively traverse child nodes
    for child in node.get_children():
        find_constraints_goto(child, start_line, end_line, results, conditions)
    
    # If current node is a condition statement, remove from condition stack during backtracking
    if node.kind in (clang.cindex.CursorKind.IF_STMT, clang.cindex.CursorKind.WHILE_STMT,
                     clang.cindex.CursorKind.FOR_STMT, clang.cindex.CursorKind.SWITCH_STMT):
        conditions.pop()

    return results

def extract_code(node):
    """ Convert ast object to str format """
    code = []
    for token in node.get_tokens():
        code.append(token.spelling)
    return ' '.join(code)

def is_null_check(condition_code, variable_name):
    """
    Check if a variable is checked for non-null in a given constraint condition
    """
    # Define regular expressions for common null/boolean/int checks
    null_check_pattern = re.compile(rf'\b{variable_name}\b\s*==\s*NULL|\b{variable_name}\b\s*!=\s*NULL')
    bool_check_pattern = re.compile(rf'\b{variable_name}\b\s*(==|!=)\s*0|\b{variable_name}\b')
    
    # Combine both patterns into one
    if null_check_pattern.search(condition_code) or bool_check_pattern.search(condition_code):
        return True
    
    return False

def filter_if_statements(if_statements, variable_name):
    filtered_if_statements = []
    for if_stmt in if_statements:
        condition = next(if_stmt.get_children())  # Get the condition expression
        condition_code = extract_code(condition)

        # Check if the condition is a null check for the variable
        if is_null_check(condition_code, variable_name):
            filtered_if_statements.append(if_stmt)
    
    return filtered_if_statements

def is_inside_function_call(line, var_name):
    # if(!var_name)
    if re.search(rf'\bif\s*\(\s*(!\s*)?\b{re.escape(var_name)}\b', line):
        return False
    # if(var_name != NULL)
    if re.search(rf'\b{re.escape(var_name)}\s*!=\s*NULL\b', line):
        return False
    # if(&&/|| !var_name
    if re.search(rf'(\|\||\&\&)\s*\(*\s*(!\s*)?\b{var_name}\b', line):
        return False
    # Check for common function call patterns
    return bool(re.search(r'\b\w+\s*\([^)]*\b' + re.escape(var_name) + r'\b', line))

def extract_if_content(lines, start_index, line, var_name):
    """Extract the content of if statement blocks"""
    content_lines = []
    indent_level = len(line) - len(line.lstrip())
    nested_indent_level = indent_level
    target_line = line
    index = start_index

    # Complete the condition line if it's split across multiple lines
    while is_incomplete_condition(target_line) and start_index < len(lines) - 1:
        start_index += 1
        next_line = lines[start_index].strip()
        if next_line.endswith('{'):
            next_line = next_line.rstrip('{').strip()
        target_line += ' ' + next_line

    else_if = False
    end_index = start_index + 1
    for i in range(start_index + 1, len(lines)):
        next_line = lines[i]
        # print(next_line)
        next_line_indent = len(next_line) - len(next_line.lstrip())
        if next_line_indent == nested_indent_level and not next_line.strip().startswith(('else', '} else', '#', '}')):
            end_index = i
            break
        if next_line_indent < nested_indent_level and not next_line.strip().startswith('#') and next_line:
            end_index = i
            break

    content_lines.extend([line for line in lines[index:end_index]])
    return '\n'.join(content_lines)

def filter_pointer_declaration(var_name,lines):
    filtered_lines = []
    
    # Regular expression pattern to match any pointer declaration
    declaration_pattern = re.compile(rf"\b\w+\s*\*\s*{re.escape(var_name)}\s*(?:=|;)")
    
    for line in lines:
        if not declaration_pattern.search(line):
            filtered_lines.append(line)
    
    return filtered_lines

def extract_conditions_filter_assignments(var_name, var_assignment_statements, context_helper:ContextHelper):
    target_statement = context_helper.target_text
    
    target_statement_condition = target_statement.condition
    var_assignment_statements_filter = filter_pointer_declaration(var_name,var_assignment_statements)
    function_body = context_helper.function_body
    # 1. Get constraints for all assignment statements
    # 2. Get constraints for dereference statements  
    # 3. Starting from dereference statement, find assignment statement constraints that are true subsets of dereference constraints from near to far
    # 4. Delete more distant assignment statements
    # 5. Function body range starts from found assignment statement including dereference constraints, up to dereference statement. Jump context and non-empty check context follow same logic
    lines = function_body.split('\n')

    target_line_index = -1
    assignments_line_index = {var: [] for var in var_assignment_statements}
    for i, line in enumerate(lines):
        for var_assignment_statement in var_assignment_statements:
            if var_assignment_statement in line:
                assignments_line_index[var_assignment_statement].append(i)
        if target_statement.text in line:
            target_line_index = i

    return context_helper

def extract_conditions(var_name, var_assignment_statement, target_statement, function_code):
    """
    Extracts conditions and related statements surrounding a target variable assignment 
    and a target statement within a given block of code.

    Parameters:
    var_name (str): The name of the variable whose assignment is being tracked.
    
    var_assignment_statement: The specific line of code where the variable is assigned NULL value.
    
    target_statement: The dereferenced line.
    
    function_code: The entire block of code (typically a function) provided as a string.

    Returns:
    str: A JSON string containing:
         - The target statement and its surrounding conditions.
         - Conditions related to the variable assignment.
         - Conditions where the variable is checked for being non-empty.
         - Any return or goto statements between the assignment and the target statement.
    """
    lines = function_code.split('\n')

    target_line_index = -1
    assignment_line_index = 0

    for i, line in enumerate(lines):
        if var_assignment_statement and var_assignment_statement in line:
            assignment_line_index = i
        if target_statement in line:
            # We also need to consider finding the true index of the complete target_line, for example, in the following case:
            # pr_debug("omap_hwmod: %s %pOFn at %pR\n",
            #         oh->name, np, res); //sink
            if(line.count('(') < line.count(')')):
                target_line_index = find_complete_condition_start(lines,i)
            else:
                target_line_index = i

    if assignment_line_index == -1 or target_line_index == -1 or assignment_line_index > target_line_index:
        return json.dumps({
            "target_statement": None,
            "variable_assignments": [],
            "variable_non_empty": [],
            "return_goto_statements": [],
            "filter_function_code":None
        })
    # target_conditions = extract_conditions_around_target_old(lines, target_line_index, True, var_name)
    target_conditions = extract_conditions_around_target_with_lines(lines, target_line_index, True, var_name)

    variable_assignments_conditions = extract_conditions_around_target_old(lines, assignment_line_index, False, var_name)
    
    # variable_assignments_conditions_filter = filter_assignments_conditions(variable_assignments_conditions)

    # variable_non_empty = extract_var_non_empty_conditions(lines, assignment_line_index, target_line_index, var_name)

    return_goto_statements = extract_return_goto_conditions2(lines, target_line_index, var_name)
    # return_goto_statements = extract_return_goto_conditions2(lines, assignment_line_index, target_line_index, var_name)
    # result = {
    #     "target_statement": {"text": target_statement, "condition": target_conditions},
    #     "variable_assignments": {"text": var_assignment_statement, "condition": variable_assignments_conditions},
    #     # "variable_non_empty": variable_non_empty,
    #     "return_goto_statements": return_goto_statements,
    #     "filter_function_code":function_code
    # }
    result = {
        "bug_line_constraints": [{"text": target_statement, "condition": target_conditions}],
        "target_conditions": target_conditions,
        "variable_assignments": {"text": lines[assignment_line_index], "condition": variable_assignments_conditions},
        "variable_non_empty": [],
        "early_jump_constraints": return_goto_statements,
        "filter_function_code": function_code
    }
    return json.dumps(result, indent=4, ensure_ascii=False)

def parse_condition(condition):
    # Simple parsing of function conditions and returning macros to be defined
    macro_defs = []
    tokens = condition.split()

    for token in tokens:
        # Extract macros that may need to be defined, such as CONFIG_
        if token.startswith("CONFIG_"):
            macro_defs.append(token.strip('!'))

    return macro_defs

def extract_conditions_s(var_name, target_statement,end_line, function_code,file_path) -> dict:
    lines = function_code.split('\n')
    index = clang.cindex.Index.create()
    translation_unit = index.parse(file_path)
    ifdef = find_ifdef_range(file_path,end_line)
    args = ['-std=c11']
    if ifdef is not None:
        condition = ifdef['condition']
        macro_names = parse_condition(condition)
        args.extend(['-D' + macro for macro in macro_names])
    translation_unit = index.parse(file_path,args)
    start_line = find_function_start(translation_unit.cursor, end_line)
    if start_line is None:
        print(f"Could not find a function that contains line {end_line}.")
        return {
            "bug_line_constraints": None,
            "variable_assignments": [],
            "target_conditions": [],
            "variable_non_empty": [],
            "early_jump_constraints": [],
            "filter_function_code": None
        }
    target_line_index = -1
    assignment_line_index = 0  # First line is assumed to be assignment line

    for i, line in enumerate(lines):
        if target_statement == line:
            target_line_index = i

    if target_line_index == -1 or assignment_line_index > target_line_index:
        return {
            "bug_line_constraints": None,
            "variable_assignments": [],
            "variable_non_empty": [],
            "target_conditions": [],
            "early_jump_constraints": [],
            "filter_function_code": None
        }

    target_conditions = extract_conditions_around_target_v2(lines, end_line-start_line, True, var_name)

    variable_assignments_conditions = extract_conditions_around_target_v2(lines, assignment_line_index, False, var_name)

    variable_non_empty = extract_var_non_empty_conditions(translation_unit,start_line, end_line, var_name)

    return_goto_statements = extract_return_goto_conditions(translation_unit,start_line, end_line, var_name)

    result = {
        "bug_line_constraints": [{"text": target_statement, "condition": target_conditions}],
        "target_conditions": target_conditions,
        "variable_assignments": {"text": lines[assignment_line_index], "condition": variable_assignments_conditions},
        "variable_non_empty": variable_non_empty,
        "early_jump_constraints": return_goto_statements,
        "filter_function_code": function_code
    }
    

    # pdb.set_trace()

    return result

    # return json.dumps(result, indent=4, ensure_ascii=False)

# print(extract_conditions("idev", "idev = __in6_dev_get(dev);","\t\tif (dev && check_stable_privacy(idev, dev_net(dev), mode) < 0)","static int inet6_validate_link_af(const struct net_device *dev,\n\t\t\t\t  const struct nlattr *nla,\n\t\t\t\t  struct netlink_ext_ack *extack)\n{\n\tstruct nlattr *tb[IFLA_INET6_MAX + 1];\n\tstruct inet6_dev *idev = NULL;\n\tint err;\n\n\tif (dev) {\n\t\tidev = __in6_dev_get(dev);\n\t\tif (!idev)\n\t\t\treturn -EAFNOSUPPORT;\n\t}\n\n\terr = nla_parse_nested_deprecated(tb, IFLA_INET6_MAX, nla,\n\t\t\t\t\t  inet6_af_policy, extack);\n\tif (err)\n\t\treturn err;\n\n\tif (!tb[IFLA_INET6_TOKEN] && !tb[IFLA_INET6_ADDR_GEN_MODE])\n\t\treturn -EINVAL;\n\n\tif (tb[IFLA_INET6_ADDR_GEN_MODE]) {\n\t\tu8 mode = nla_get_u8(tb[IFLA_INET6_ADDR_GEN_MODE]);\n\n\t\tif (check_addr_gen_mode(mode) < 0)\n\t\t\treturn -EINVAL;\n\t\tif (dev && check_stable_privacy(idev, dev_net(dev), mode) < 0)\n\t\t\treturn -EINVAL;\n\t}\n\n\treturn 0;\n}"))