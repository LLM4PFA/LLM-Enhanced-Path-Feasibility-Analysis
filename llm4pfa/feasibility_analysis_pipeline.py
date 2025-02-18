import json
import pdb

from util.path_util import PathUtil
from util.data_utils import DataUtils
from LLM4Detection.agent_simple import tool_utils
from LLM4Detection.agent_simple.tool_definion import tools
from tqdm import tqdm
from z3 import *
from util import extract_util_plus
from LLM4Detection.agent.tool_utils import is_direct_dereference, extract_function_name, \
    get_dereferenced_locations_plus, get_param_name
from LLM4Detection.agent_simple.prompt_template import Prompt
from LLM4Detection.baseline_models.model import ModelFactory

import re

code_data_path = PathUtil.codeql_result_data("kernel69_nullpointer_process", "json")
code_context_path = PathUtil.codeql_result_data("kernel69_nullpointer_gpt4omini_dataflow_function_cache_1017", "json")
constraints_path = PathUtil.codeql_result_data("kernel69_nullpointer_gpt4omini_constrain_cache_1010", "json")
output_path = PathUtil.output("codeql_linux_nullpointer_qwen_124_8", "json")
func_body_cache_path = PathUtil.processed_data(f"function_cache_gpt-4omini_linux", "json")
result_memory_cache_path = PathUtil.processed_data(f"result_memory_cache", "json")
codeql_dereferenced_cache = PathUtil.codeql_dereferenced_cache()

function_cache = DataUtils.get_cache(func_body_cache_path)
result_memory_cache = DataUtils.get_cache(result_memory_cache_path)
code_context_info = DataUtils.load_json(code_context_path)

prompt = Prompt()

start_num = 0
end_num = 70
model_name = "gpt"

model = ModelFactory._models[model_name]()

def get_context_function_body_with_tool(tool_call, function_name_list, function_body_list):
    function_name = tool_call.function.name
    function_args = json.loads(tool_call.function.arguments)
    function_name_list.append(function_args)
    print("Call Function: ", function_name, function_args)

    function_key = json.dumps(function_args)
    function_key_name = json.loads(function_key)['name']
    function_response = get_function_body_by_name(function_key_name)

    function_body_list.append(function_response)

    with open(func_body_cache_path, 'w') as f:
        json.dump(function_cache, f)

    return function_key_name, function_response, function_name_list, function_body_list

def get_answer_from_model_with_tool(messages, model_name, function_name_list, function_body_list, iter_num, var_name, bug_line_constraint):

    response_message = model.get_response_with_tool(model_name, messages, tools)

    tool_calls = response_message.tool_calls if hasattr(response_message, 'tool_calls') else []

    if tool_calls:

        for tool_call in tool_calls:

            context_function_name, context_function_body, function_name_list, function_body_list = get_context_function_body_with_tool(tool_call, function_name_list, function_body_list)

            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool", 
                    "name": "search_function",
                    # "role": "user",
                    "content": str(context_function_body) + str(prompt.analysis_constraints_prompt_context_multi_(context_function_name, context_function_body, var_name, bug_line_constraint))
                }
            )

        if iter_num > 1:
            return response_message["content"] if isinstance(response_message, dict) else response_message, function_name_list, function_body_list
        iter_num += 1

        return get_answer_from_model_with_tool(messages, model_name, function_name_list, function_body_list, iter_num, var_name, bug_line_constraint)

    else:
        return response_message["content"] if isinstance(response_message, dict) else response_message, function_name_list, function_body_list

def get_answer_from_model_without_tool(messages, model_name):
    step_response = model.get_response_with_messages(model_name, messages)

    # Handle case where response is a string instead of object with choices
    if isinstance(step_response, str):
        response_message = step_response
    else:
        response_message = step_response.choices[0].message.content
        
    print(response_message)
    return response_message


def process_final_response(response,content=''):

    try:
        response = response.split("```python")[1].split("```")[0]

        response = response.replace("from z3 import *", "")
    except Exception as e:
        print(e)
        response = response

    return response

def process_array_response(response):
    response = response.split("```json")[1].split("```")[0]
    cleaned_string = response.strip()
    return json.loads(cleaned_string)

def process_goto_conditions(early_jump_constraints, goto_label):
    early_jump_constraints_list = []
    for item_constraint in early_jump_constraints:
        if goto_label != item_constraint['text'] and item_constraint['condition'] != []:
            constraint_str = ""
            for item in item_constraint['condition']:
                constraint_str += "!(" + item + ") || "
            constraint_str = constraint_str[:-4]
            early_jump_constraints_list.append(constraint_str)
    return early_jump_constraints_list

def get_function_body_by_name(new_function_name):

    if new_function_name in function_cache:
        new_function_body = function_cache[new_function_name]
        if new_function_body == "There are more than 1 function in the repo!":
            new_function_body = tool_utils.get_func_body_in_repo_by_name(name=new_function_name)
            function_cache[new_function_name] = new_function_body
    else:
        new_function_body = tool_utils.get_func_body_in_repo_by_name(name=new_function_name)
        function_cache[new_function_name] = new_function_body
        with open(func_body_cache_path, 'w') as f:
            json.dump(function_cache, f)

    return new_function_body

def extract_function_arguments(function_call):
    match = re.match(r'(\w+)\((.*)\)', function_call)

    if match:
        function_name = match.group(1)
        arguments = match.group(2)

        args_list = re.findall(r'(?:[^,(]|\([^)]*\))+', arguments)

        return args_list
    else:
        return []

def data_flow_analysis_pipeline(var_name, loc_text, code_snippet, response_list, function_name_list, function_body_list,target_index, file_path, derefere_cache, target_conditions, early_jump_constraints,level, idx,original_index):

    # get conditional expressions

    extract_conditions_plus = json.loads(extract_util_plus.extract_conditions(var_name, None, loc_text, code_snippet))
    if extract_conditions_plus["bug_line_constraints"][0]["text"] == loc_text:
        target_conditions =  extract_conditions_plus["bug_line_constraints"][0]["condition"]
    early_jump_constraints = extract_conditions_plus["early_jump_constraints"]

    goto_label = ""               
    z3_constraints = ""

    for item_constraint in target_conditions:
        if "goto" in item_constraint["condition"] or "return" in item_constraint["condition"]:
            target_conditions.remove(item_constraint)
            goto_label = item_constraint

        
    # generate z3 template
    non_null_value = var_name + " == 0"
    target_conditions.append(non_null_value)
    target_conditions_prompt = prompt.get_z3_by_target_conditions(target_conditions)
    messages = [{"role": "user", "content": target_conditions_prompt}]
    response_message_target = get_answer_from_model_without_tool(messages, model_name)
    target_conditions.remove(non_null_value)
    response_list.append("step 1 z3 script: " + response_message_target)

    # symbolic range reasoning with LLM

    target_conditions = [item for item in target_conditions if "while" not in item]

    if target_conditions != []:
        for item_constraint in target_conditions:

            # context analysis
            context_function_name = extract_function_name(var_name, item_constraint['condition'])

            if context_function_name != None and context_function_name != "if":

                context_function_body = get_function_body_by_name(context_function_name)

                # consider multiple levels---------:
                user_prompt = prompt.analysis_constraints_prompt_context_multi(context_function_name, context_function_body,var_name, item_constraint)
                message_context = [{"role": "user", "content": user_prompt}]

                # pdb.set_trace()
                # llm_response, function_name_list, function_body_list = get_answer_from_model_with_tool(message_context,model_name,function_name_list,function_body_list,0, var_name,item_constraint)

                # consider only 1 level
                function_name_list.append(context_function_name)
                function_body_list.append(context_function_body)
                llm_response = get_answer_from_model_without_tool(message_context, model_name)

                llm_response_str = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
                response_list.append("step 2 context analysis:" + llm_response_str)

                if "Not satisfied" in llm_response_str:
                    gpt_result = {
                        "response": response_list,
                        "function_name_list": function_name_list,
                        "function_body_list": function_body_list,
                        "result": False
                    }
                    print("result2_context = False")
                    return gpt_result

            # =============================

            else:
                user_prompt = prompt.bug_line_constraints_prompt_step1(var_name, loc_text, item_constraint, code_snippet)
                messages.append({"role": "user", "content": user_prompt})
                llm_response = get_answer_from_model_without_tool(messages, model_name)
                messages.append({"role": "assistant", "content": llm_response})

        # convert llm response into z3 constraints and merge

        messages.append({"role": "user", "content": prompt.bug_line_constraints_prompt_step2(response_message_target)})
        bug_line_constraints_response = get_answer_from_model_without_tool(messages, model_name)
        bug_line_constraints_response_process = process_final_response(bug_line_constraints_response)

        # optimize z3 script
        merged_prompt = prompt.get_z3_extract(bug_line_constraints_response_process)
        messages = [{"role": "user", "content": merged_prompt}]
        final_response = get_answer_from_model_without_tool(messages, model_name)
        response_list.append("step 2 analysis: " + final_response)
        final_response = process_final_response(final_response)
        response_list.append("step 2 z3 script: " + final_response)

        # solving
        cnt = 0
        while (cnt <= 3):
            cnt += 1
            try:
                exec(final_response, globals())
                result = check_constraints()
                print("dereference constraint:", result)
                if not result:
                    gpt_result = {
                        "response": response_list,
                        "function_name_list": function_name_list,
                        "function_body_list": function_body_list,
                        "z3_script": final_response,
                        "result": False
                    }
                    print("result2=False")
                    # DataUtils.save_json(output_path, gpt_result)
                    # pdb.set_trace()
                    return gpt_result
                else:
                    break
            except Exception as e:
                print(e)
                # pdb.set_trace()
                messages.append({"role": "assistant", "content": final_response})
                messages.append({"role": "user", "content": prompt.re_generate_prompt(str(e))})
                final_response = get_answer_from_model_without_tool(messages, model_name)
                final_response = process_final_response(final_response)
                response_list.append("fix step2 z3 script: " + final_response)

        z3_constraints = final_response

    early_jump_constraints_list = process_goto_conditions(early_jump_constraints, goto_label)

    if early_jump_constraints_list != []:
        filter_goto_prompt = prompt.get_filter_goto(early_jump_constraints_list, target_conditions, var_name, code_snippet)
        messages = [{"role": "user", "content": filter_goto_prompt}]
        response_filter_goto = get_answer_from_model_without_tool(messages, model_name)
        early_jump_constraints_list = process_array_response(response_filter_goto)
        response_list.append("response_filter_goto: " + response_filter_goto)

    if early_jump_constraints_list != []:

        # context analysis
        # for early_jump_constraint in early_jump_constraints_list:
        #
        #     # pdb.set_trace()
        #     context_function_name = extract_function_name(var_name, early_jump_constraint)
        #
        #     if context_function_name != None and context_function_name != "if":
        #
        #         # pdb.set_trace()
        #
        #         context_function_body = get_function_body_by_name(context_function_name)
        #         function_name_list.append("goto_constrain: " + context_function_name)
        #         function_body_list.append(f"goto_constrain: {str(context_function_body)}")
        #
        #         # entering only 1 level function --------------
        #         user_prompt = prompt.analysis_constraints_prompt_context_multi(context_function_name, context_function_body,var_name, early_jump_constraint)
        #         message_context = [{"role": "user", "content": user_prompt}]
        #         llm_response = get_answer_from_model_without_tool(message_context, model_name)
        #         # -------------------------
        #
        #         # entering multiple level functions
        #         # user_prompt = prompt.analysis_constraints_prompt_context_multi(context_function_name, context_function_body,var_name, early_jump_constraint)
        #         # message_context = [{"role": "user", "content": user_prompt}]
        #         #
        #         # llm_response, function_name_list, function_body_list = get_answer_from_model_with_tool(message_context, model_name, function_name_list, function_body_list, 0, var_name, early_jump_constraint)
        #         # ----------------------------
        #         llm_response_str = llm_response.content if hasattr(llm_response, 'content') else str(llm_response)
        #         response_list.append("step 3 context analysis:" + llm_response_str)
        #         # pdb.set_trace()
        #
        #         if "Not satisfied" in llm_response_str or "not satisfied" in llm_response_str:
        #             gpt_result = {
        #                 "response": response_list,
        #                 "function_name_list": function_name_list,
        #                 "function_body_list": function_body_list,
        #                 "result": False
        #             }
        #             print("result3_context = False")
        #             return gpt_result

        # convert into z3 constraint
        goto_prompt = prompt.get_z3_by_goto(early_jump_constraints_list, target_conditions, var_name)
        messages = [{"role": "user", "content": goto_prompt}]
        response_message_goto = get_answer_from_model_without_tool(messages, model_name)
        response_list.append("z3 script: " + response_message_goto)
        # pdb.set_trace()

        # merge into z3 script
        merged_prompt = prompt.get_z3_merged3(response_message_target, z3_constraints, response_message_goto)
        messages = [{"role": "user", "content": merged_prompt}]
        final_response = get_answer_from_model_without_tool(messages, model_name)
        final_response = process_final_response(final_response)
        response_list.append("final z3 script: " + final_response)

        # solving
        cnt = 0
        while (cnt <= 3):
            cnt += 1
            try:
                exec(final_response, globals())
                # pdb.set_trace()
                # 调用函数
                result = check_constraints()
                print("goto result:", result)
                # pdb.set_trace()

                if not result:
                    gpt_result = {
                        "response": response_list,
                        "function_name_list": function_name_list,
                        "function_body_list": function_body_list,
                        "z3_script": final_response,
                        "result": False
                    }
                    return gpt_result
                else:
                    cnt = 5
                    break
            except Exception as e:
                print(e)
                # pdb.set_trace()
                messages.append({"role": "assistant", "content": final_response})
                messages.append({"role": "user", "content": prompt.re_generate_prompt(str(e))})
                final_response = get_answer_from_model_without_tool(messages, model_name)
                final_response = process_final_response(final_response)
                response_list.append("fix final z3 script: " + final_response)

    # get next function information in the call trace

    try:
        new_function_name = extract_function_name(var_name, loc_text)
        # if new_function_name in result_memory_cache:

        new_function_body = code_context_info[original_index]["function_call"][level + 1]

        function_body_list.append(new_function_body)
        function_name_list.append(new_function_name)

    except Exception as e:
        gpt_result = {
            "response": response_list,
            "function_name_list": function_name_list,
            "function_body_list": function_body_list,
            "result": True
        }

        return gpt_result

    # get new sink point in the next function

    try:
        inner_var_name = get_param_name(var_name,loc_text,new_function_body)
        deref_line,deref_index,deref_file_path = get_dereferenced_locations_plus(derefere_cache,new_function_name, inner_var_name)
    except Exception as e:
        gpt_result = {
            "response": response_list,
            "function_name_list": function_name_list,
            "function_body_list": function_body_list,
            "result": "new deref line get error"
        }
        return gpt_result

    if deref_line is None:
        gpt_result = {
        "response": response_list,
        "function_name_list": function_name_list,
        "function_body_list": function_body_list,
        "result": True
        }

        return gpt_result


    args = extract_function_arguments(new_function_name)
    if var_name in args:
        args.remove(var_name)
    new_target_condition = []
    new_early_jump_constraints = []
    for item in args:
        for con1 in target_conditions:
            if item in con1:
                new_target_condition.append(con1)
        for con2 in early_jump_constraints_list:
            if item in con2:
                new_early_jump_constraints.append(con2)

    return data_flow_analysis_pipeline(inner_var_name, deref_line, new_function_body, response_list,function_name_list, function_body_list,target_index,file_path,derefere_cache, new_target_condition, new_early_jump_constraints, level+1, idx,original_index)

def detect_pipeline():
    code_data = DataUtils.load_json(code_data_path)
    constraints_data = DataUtils.load_json(constraints_path)

    gpt_result = []

    if PathUtil.exists(output_path):
        gpt_result = DataUtils.load_json(output_path)

    if PathUtil.exists(codeql_dereferenced_cache):
        derefere_cache = DataUtils.load_json(codeql_dereferenced_cache)

    cnt = start_num
    for item in tqdm(code_data[start_num:end_num]):

        try:
            function_name_list = []
            function_body_list = []
            response_list = []
            var_name = item['var_name']
            loc_text = item["location"]["context"]["snippet"]["text"]
            target_index = item["location"]["region"]["startLine"]
            file_path = "/home/zqc/ozy/project/BDCodeQL/linux-6.9.6/" + item["location"]["file_path"]
            code_snippet = item["function_code"]
            original_index = cnt

            response = data_flow_analysis_pipeline(var_name, loc_text, code_snippet, response_list, function_name_list,function_body_list, target_index, file_path, derefere_cache,constraints_data[cnt]["target_conditions"], constraints_data[cnt]["early_jump_constraints"], 0, cnt,original_index)
            cnt += 1

        except Exception as e:
            print(e)
            response = {}
            response["result"] = str(e)
            cnt += 1
        response["code_snippet"] = code_snippet
        response["var_name"] = var_name
        response["loc_text"] = loc_text
        response["index"] = cnt-1
        gpt_result.append(response)
        DataUtils.save_json(output_path, gpt_result)


if __name__ == '__main__':
    detect_pipeline()
