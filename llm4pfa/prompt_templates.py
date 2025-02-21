z3_prompt_extend = """
Important guidelines for generating Z3 scripts:
1. Variable Type Guidelines:
   - Prefer Int type over Bool type
   - Default to Int type for unknown variables
   - Convert !ptr to ptr==0 for Int variables
   
2. Boolean Representation:
   - Represent False as Int variable == 0
   - Represent True as Int variable == 1
   
3. Critical Rules:
   - Use And, Or, Not instead of &, |, ! operators
   - Avoid assigning Int values to Bool variables
   - Convert !ptr or Not(ptr) to ptr==0 only
   
4. Constraint Guidelines:
   - Prefer using ==1 or ==0 over inequality operators
   - Skip constraints for uncertain value ranges
   - Only interpret function returns when names clearly indicate meaning
"""
class Prompt:


    def re_generate_prompt(self, error_message):
        """Generate prompt for fixing Z3 script errors"""
        return f"""
        The Z3 script contains errors. Please modify and regenerate the Z3 Python script.
        Error message: {error_message}

        Additional guidelines:
        {z3_prompt_extend}

        Return only executable code without extra content (no import statements).
        """
    
    def get_z3_by_target_conditions(self, target_conditions):
        """Convert C code constraints to Z3 solver script"""
        return f"""
        Convert C code constraints into Z3 solver script.
        Current constraints: {target_conditions}

        Guidelines:
        {z3_prompt_extend}

        Format response strictly as:
        ```python
        var_name1=Int('var1')
        var_name2=Bool('var2')
        s.add(constraint 1)
        s.add(constraint 2)
        ...
        ```
        """
    
    def analysis_constraints_prompt_context(self, context_function_name, context_function_body, value, item_constrain):
        """Analyze if constraints can be satisfied when a pointer is NULL"""
        return f"""
        Function "{context_function_name}" body: "{context_function_body}"

        Please analyze:
        1. The return value of function "{context_function_name}" when pointer "{value}" is NULL
        2. Whether "{item_constrain}" can be satisfied when pointer "{value}" is NULL

        Conclude with one of:
        ### Satisfied ###
        ### Not satisfied ###
        ### Not sure ###
        """

    def analysis_constraints_prompt_context_multi(self, context_function_name, context_function_body, value, item_constrain):
        """Extended analysis for constraints with function calls"""
        return f"""
        Function "{context_function_name}" body: "{context_function_body}"

        Analysis steps:
        1. Analyze the return value of function "{context_function_name}" when pointer "{value}" is NULL
        2. Determine if "{item_constrain}" can be satisfied when pointer "{value}" is NULL
        3. If direct analysis is not possible:
        - Use search_context tool to obtain function bodies for calls involving pointer "{value}"
        - Perform deeper analysis of related function calls

        Conclude with one of:
        ### Satisfied ###
        ### Not satisfied ### 
        ### Not sure ###

        Note: Do not use ### markers anywhere else in your analysis to avoid processing errors.
        """


    def bug_line_constraints_prompt_step1(self, value, bug_text, bug_line_constraints, code_snippet):
        """Analyze code for potential NULL pointer issues using symbolic execution"""
        return f"""
        You are an expert C/C++ programmer.

        Task: Analyze the following code snippet using symbolic execution:
        1. Simulate program execution line by line
        2. When reaching statement "{bug_line_constraints}":
        - Assume pointer "{value}" is NULL
        - Determine value ranges for all variables in "{bug_line_constraints}"
        - For function calls, analyze based on function name semantics
        - Ensure line-by-line simulation analysis

        Code snippet:
        {code_snippet}
        """

    def bug_line_constraints_prompt_step2(self, pre_script):
        """Add new constraints to existing Z3 script while preserving original constraints"""
        return f"""
        Task: Extend the existing Z3 constraint script with additional constraints.

        Existing script:
        {pre_script}

        Key requirements:
        1. ADD new constraints only
        2. DO NOT modify or delete existing constraints
        3. For same-variable constraints:
        - Keep all existing constraints
        - Add new constraints alongside existing ones
        4. For type modifications:
        - Update constraint statements accordingly
        - Keep original statements, add modified versions

        Z3 script guidelines:
        {z3_prompt_extend}

        Return format:
        - Only include new constraint lines to be added
        - Maintain consistent formatting with existing code
        - Include comments explaining new constraints
        """
    
    def get_z3_by_goto(self, condition, target_conditions, var_name):
        """Convert C code constraints to Z3 solver format with filtering"""
        return f"""
        As a C language expert, convert C code constraints to Z3 solver script.

        Input constraints: {condition}
        Relevant conditions/variables: {target_conditions}, {var_name}

        Guidelines:
        1. Convert only constraints affecting the specified conditions/variables
        2. Add comments explaining why each constraint is included
        3. Maintain original variable names
        4. Convert C-style expressions properly (e.g., !ptr to ptr!=0)

        Return only executable Z3 script with explanatory comments.
        """

    def get_filter_goto(self, condition, target_conditions, var_name, func_body):
        """Filter constraints relevant to reachability analysis"""
        return f"""
        Performing reachability analysis:

        Given:
        - Code segment: {func_body}
        - Target variables: {target_conditions}, {var_name}
        - Constraints: {condition}

        Task:
        1. Filter constraints affecting reachability
        2. Include only constraints involving target variables
        3. Verify filtered constraints step by step

        Return filtered constraints in JSON array format: ```json["","",...]```"""


    def get_z3_merged3(self, m1, m2, m3):
        """Merge multiple Z3 constraint sets into a single validation function"""
        return f"""
        As a Z3 constraint solver expert, merge the following constraint sets into a single function.

        Input:
        1. Base Z3 script: {m1}
        2. Constraint set 1: {m2}
        3. Constraint set 2: {m3}

        Requirements:
        1. Merge all constraints into a check_constraints() function
        2. Retain ALL original constraints from the base script
        3. Add any missing variable definitions from constraint sets
        4. Function must return boolean (True if constraints are satisfied)
        5. Return ONLY the function code without imports
        6. Ensure code is directly executable

        Function signature:
        def check_constraints():
            # Your merged constraints here
            return result  # boolean
        """

    def get_z3_extract(self, m1):
        """Optimize and validate Z3 constraint solver script"""
        return f"""
        As a Z3 constraint solver expert, optimize the following script for correctness and reliability.

        Input Z3 script: {m1}

        Optimization requirements:
        1. Check and fix syntax errors
        2. Prevent NameError issues by ensuring all variables are defined
        3. Ensure consistent variable types throughout
        4. Fix any TypeError issues, especially for:
        - Unsupported operations between ArithRef types
        - Proper handling of bitwise operations

        Additional guidelines:
        {z3_prompt_extend}

        Output requirements:
        1. Generate a check_constraints() function
        2. Function must return boolean validation result
        3. Return ONLY the function code without imports
        4. Ensure code is directly executable

        Function signature:
        def check_constraints():
        """