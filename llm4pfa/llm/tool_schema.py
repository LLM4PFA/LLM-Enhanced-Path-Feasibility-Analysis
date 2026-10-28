"""Tool interface adapter for the existing function-source lookup callback.

The callback reads arguments['name'], searches for that function's source,
and labels its tool response 'search_function'. The schema matches the existing callback interface.
"""

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_function",
            "description": "Retrieve the source code of a function in the target project by its name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the function whose source code is needed.",
                    }
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    }
]
