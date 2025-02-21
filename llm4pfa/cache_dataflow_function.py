import json
import pdb
import os
from openai import OpenAI
from util.path_util import PathUtil
from util.data_utils import DataUtils
from LLM4Detection.agent_simple import tool_utils
from tqdm import tqdm
from util import extract_util_plus
from LLM4Detection.agent.tool_utils import is_direct_dereference, extract_function_name, \
    get_dereferenced_locations_plus, get_param_name

# Configuration
# PROJECT_ROOT = "/home/zqc/ytest/libav/"  # Replace with your project root path
# CODE_DATA_PATH = PathUtil.codeql_result_data("libav_nullpointer", "json")
# OUTPUT_PATH = PathUtil.codeql_result_data("libav_nullpointer_gpt4omini_dataflow_function_cache_1124", "json")
# FUNC_BODY_CACHE_PATH = PathUtil.processed_data(f"function_cache_gpt-4omini-turbo_libav", "json")
# CODEQL_DEREFERENCED_CACHE = PathUtil.codeql_dereferenced_cache("libav_nullpointer_dereferenced_cache", "json")
# ASSIGN_LINE_FILE_PATH = 'data/SA_results/codeql/result/libav_nullpointer_100_assignLine.json'
REPO_NAME = "libav"
PROJECT_ROOT = f"/home/fdse/ytest/{REPO_NAME}/"  # Replace with your project root path
# CODE_DATA_PATH = PathUtil.codeql_result_data(f"{REPO_NAME}_nullpointer_process", "json")
CODE_DATA_PATH = PathUtil.codeql_result_data(f"cppcheck_{REPO_NAME}_nullpointer_process", "json")
OUTPUT_PATH = PathUtil.codeql_result_data(f"cppcheck_{REPO_NAME}_nullpointer_gpt4omini_dataflow_function_cache_0122", "json")
FUNC_BODY_CACHE_PATH = PathUtil.processed_data(f"function_cache_gpt-4omini_{REPO_NAME}", "json")
CODEQL_DEREFERENCED_CACHE = PathUtil.codeql_dereferenced_cache(f"{REPO_NAME}_nullpointer_dereferenced_cache", "json")
ASSIGN_LINE_FILE_PATH = f'data/SA_results/codeql/result/{REPO_NAME}_nullpointer_100_assignLine.json'
START_NUM = 0
END_NUM = 100
MODEL_NAME = "gpt-4o-mini"


# Load cache
if os.path.exists(FUNC_BODY_CACHE_PATH):
    with open(FUNC_BODY_CACHE_PATH, 'r') as f:
        function_cache = json.load(f)
else:
    function_cache = {}

def data_flow_analysis_pipeline(var_name, loc_text, code_snippet, function_name_list, function_body_list, file_path, derefere_cache, depth=0):
    """
    Data flow analysis pipeline function
    Args:
        var_name: Variable name
        loc_text: Location text
        code_snippet: Code snippet
        function_name_list: List of function names
        function_body_list: List of function bodies
        file_path: File path
        derefere_cache: Dereference cache
        depth: Recursion depth counter
    Returns:
        tuple: (cache_func_list, final_deref_line)
    """
    # Add maximum recursion depth limit
    MAX_RECURSION_DEPTH = 20
    if depth >= MAX_RECURSION_DEPTH:
        return [], loc_text

    is_direct_dereference_flag = is_direct_dereference(var_name, loc_text)

    if is_direct_dereference_flag:
        return [], loc_text
    else:
        new_function_name = extract_function_name(var_name, loc_text)
        if new_function_name is None:
            return [], loc_text

        if new_function_name in function_cache:
            new_function_body = function_cache[new_function_name]
            if new_function_body:
                new_function_body = new_function_body[0]
            else:
                raise ValueError(f"Function cache for {new_function_name} is empty.")
        else:
            new_function_body = tool_utils.get_func_body_in_repo_by_name(name=new_function_name,repo_name=REPO_NAME)
            
            if new_function_body:
                print("Select a function body from the list below:")

                selected_body = new_function_body[0]
                new_function_body = [selected_body] + list(new_function_body[1:])
            else:
                return [],loc_text
            function_cache[new_function_name] = new_function_body
            new_function_body = new_function_body[0]
            with open(FUNC_BODY_CACHE_PATH, 'w') as f:
                json.dump(function_cache, f)
            

        function_body_list.append(new_function_body)
        function_name_list.append(new_function_name)
        inner_var_name = get_param_name(var_name, loc_text, new_function_body)
        if inner_var_name is None:
            return [], loc_text

        deref_line, deref_index, deref_file_path = get_dereferenced_locations_plus(derefere_cache, new_function_name, inner_var_name)
        if deref_line is None:
            return [], loc_text
        
        cache_func_list, final_deref_line = data_flow_analysis_pipeline(
            inner_var_name, 
            deref_line, 
            new_function_body, 
            function_name_list, 
            function_body_list, 
            file_path, 
            derefere_cache,
            depth + 1  # Increase recursion depth counter
        )
        cache_func_list.append(new_function_body)
        return cache_func_list, final_deref_line
    
def detect_pipeline():
    code_data = DataUtils.load_json(CODE_DATA_PATH)
    with open(ASSIGN_LINE_FILE_PATH, 'r') as assignLine_file:
        assignLine_data = json.load(assignLine_file)
    
    cache_func_body_list = DataUtils.load_json(OUTPUT_PATH) if PathUtil.exists(OUTPUT_PATH) else []
    derefere_cache = DataUtils.load_json(CODEQL_DEREFERENCED_CACHE) if PathUtil.exists(CODEQL_DEREFERENCED_CACHE) else {}

    for i, item in enumerate(tqdm(code_data[START_NUM:END_NUM])):
        try:
            current_index = START_NUM + i
            # if any(cache_item["index"] == current_index for cache_item in cache_func_body_list):
            #     continue


            function_name_list = []
            function_body_list = []
            response_list = []

            var_name = item['var_name']
            loc_text = item["location"]["context"]["snippet"]["text"]
            target_index = item["location"]["region"]["startLine"]
            file_path = PROJECT_ROOT + item["location"]["file_path"]
            code_snippet = item["function_code"]

            # Iterate through segments for reachability analysis
            if not code_snippet:
                continue
            extract_conditions_plus = extract_util_plus.extract_conditions_s(var_name, loc_text, target_index, code_snippet,file_path)
            response, final_deref_line = data_flow_analysis_pipeline(
                var_name, loc_text, code_snippet, response_list, 
                function_name_list, file_path, derefere_cache
            )
            response.append(code_snippet)
            cache_func_body = {}
            cache_func_body["prt"] = var_name
            cache_func_body["function_call"] = response[::-1]
            cache_func_body["sink"] = loc_text
            cache_func_body["final_sink"] = final_deref_line
            cache_func_body["source"] = assignLine_data[str(current_index+1)]
            # cache_func_body["index"] = item["index"]
            cache_func_body_list.append(cache_func_body)
            DataUtils.save_json(OUTPUT_PATH, cache_func_body_list)
        except RecursionError as e:
            import traceback
            print(f"\nRecursionError at index {current_index}:")
            print(traceback.format_exc())
            continue
        except Exception as e:
            import traceback
            print(f"\nError at index {current_index}:")
            print(traceback.format_exc())
            continue

if __name__ == '__main__':
    detect_pipeline()