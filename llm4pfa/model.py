import pdb

import requests
from openai import OpenAI
import os
import json
from LLM4Detection.agent_simple.tool_definion import tools
from anthropic import Anthropic

# Optimized model implementation class to reduce code duplication
class BaseModel:
    def __init__(self, url, headers, model_name, api_key=None):
        self.url = url
        self.headers = headers
        self.model_name = model_name
        self.api_key = api_key
        if api_key:
            if "anthropic" in url.lower():

                self.client = Anthropic(base_url=self.url, api_key=api_key)
            else:
                self.client = OpenAI(base_url=self.url, api_key=api_key)

    def get_response(self, question):
        messages = [{"role": "user", "content": question}]
        return self.get_response_with_messages(self.model_name, messages)

    def get_response_with_messages(self, model_name, messages):
        raise NotImplementedError("This method should be implemented by subclasses")

    def get_response_with_tool(self, model_name, messages, tools=tools, tool_choice="auto"):
        raise NotImplementedError("This method should be implemented by subclasses")


# MetaLlama model implementation
class MetaLlamaModel(BaseModel):
    def __init__(self):
        super().__init__(
            url="https://api.deepinfra.com/v1/openai/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer YOUR_API_KEY"
            },
            model_name="meta-llama/Meta-Llama-3.1-70B-Instruct"
        )
    
    def get_response_with_messages(self, model_name, messages):
        try:
            response = requests.post(
                self.url,
                headers=self.headers,
                json={
                    "model": model_name,
                    "messages": messages
                }
            )
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except requests.RequestException as e:
            return f"Error in MetaLlama API call: {str(e)}"

    def get_response_with_tool(self, model_name, messages, tools=tools, tool_choice="auto"):
        # Implement the method for MetaLlama model
        raise NotImplementedError("get_response_with_tool method not implemented for MetaLlamaModel")

# Claude model implementation
class ClaudeModel(BaseModel):
    def __init__(self):
        super().__init__(
            url="https://api.openai-proxy.org/anthropic/v1/messages",  # Update to correct Anthropic API endpoint
            headers={
                "x-api-key": "YOUR_API_KEY",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            model_name="claude-3-5-sonnet-20240620"  # Update to latest Claude model version
            # model_name="claude-3-haiku-20240307" # This version is cheaper, good for debugging
        )

    def send_request(self, data):
        try:
            response = requests.post(self.url, headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return f"Error in Claude API call: {str(e)}"

    def get_response_with_messages(self, model_name, messages):
        data = {
            "model": self.model_name,
            "max_tokens": 1024,
            "messages": messages
        }
        response_json = self.send_request(data)
        if isinstance(response_json, dict):
            return response_json.get('content', [{}])[0].get('text', "No text")
        else:
            return f"Error: {response_json}"

    def get_response_with_tool(self, model_name, messages, tools=tools, tool_choice="auto"):
        # Claude API doesn't support tools directly, so we'll need to format the messages accordingly
        formatted_messages = self._format_messages_with_tools(messages, tools)
        data = {
            "model": self.model_name,
            "max_tokens": 1024,
            "messages": formatted_messages
        }
        response_json = self.send_request(data)
        if isinstance(response_json, dict):
            content = response_json.get('content', [{}])[0].get('text', "No text")
            # Parse the content to extract tool calls if any
            tool_calls = self._parse_tool_calls(content)
            return {
                "content": content,
                "tool_calls": tool_calls
            }
        else:
            return f"Error: {response_json}"

    def _format_messages_with_tools(self, messages, tools):
        # Format messages to include tool descriptions
        tool_descriptions = "\n".join([f"{tool['type']}: {tool['function']}" for tool in tools])
        system_message = f"Firstly, You have access to the following tools:\n{tool_descriptions}\nTo use a tool, respond with the tool name followed by the arguments in JSON format. Then"
        #add system info to content
        messages[0]['content'] = system_message + messages[0]['content']
        # formatted_messages = [{"role": "system", "content": system_message}] + messages
        return messages

    def _parse_tool_calls(self, content):
        # Parse the content to extract tool calls
        # This is a simplified version and might need to be adjusted based on the actual response format
        tool_calls = []
        if "Tool:" in content:
            parts = content.split("Tool:", 1)
            tool_part = parts[1].strip()
            tool_name, tool_args = tool_part.split("\n", 1)
            tool_calls.append({
                "name": tool_name.strip(),
                "arguments": tool_args.strip()
            })
        return tool_calls

# DeepSeek model implementation
class DeepSeekModel(BaseModel):
    def __init__(self):
        super().__init__(
            url="https://api.deepseek.com",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer YOUR_API_KEY"
            },
            model_name="deepseek-chat"
        )
        self.client = OpenAI(
            api_key="YOUR_API_KEY",
            base_url="https://api.deepseek.com"
        )
    def get_response_with_messages(self, model_name, messages):
        import time
        max_retries = 5
        retry_delay = 10

        for attempt in range(max_retries):
            try:
                print(f"Attempt {attempt + 1}/{max_retries}: Sending request to DeepSeek API")
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    stream=False,
                    max_tokens=1000
                )
                
                return response.choices[0].message.content

            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                error_message = f"""
DeepSeek API Error Details (Attempt {attempt + 1}/{max_retries}):
- Error Type: {type(e).__name__}
- Error Message: {str(e)}
- Full Traceback: {error_trace}
- Request URL: {self.url}
- Model Name: {self.model_name}
- Messages: {messages}
"""
                print(error_message)
                
                if attempt < max_retries - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    return f"Error in DeepSeek API call after {max_retries} attempts: {str(e)}"
        
    def get_response_with_tool(self, model_name, messages, tools=tools, tool_choice="auto"):
        try:
            # Add system message if not present
            if not any(msg.get("role") == "system" for msg in messages):
                messages = [{"role": "system", "content": "You are a helpful assistant"}] + messages

            # Ensure all messages have required role and content fields
            formatted_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    if "role" not in msg:
                        msg["role"] = "user"
                    if "content" not in msg:
                        msg["content"] = ""
                    formatted_messages.append(msg)
                else:
                    formatted_messages.append({
                        "role": "user",
                        "content": str(msg)
                    })

            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=formatted_messages,
                tools=tools,
                tool_choice="auto"
            )
            if isinstance(response, str):
                return {
                    "content": response,
                    "tool_calls": []
                }
            content = response.choices[0].message.content if hasattr(response.choices[0].message, 'content') else "No content"
            tool_calls = response.choices[0].message.tool_calls if hasattr(response.choices[0].message, 'tool_calls') else []
            return {
                "content": content,
                "tool_calls": tool_calls
            }
        except Exception as e:
            return {
                "content": f"Error: {str(e)}",
                "tool_calls": []
            }

# GPT model implementation
class GPTModel(BaseModel):
    def __init__(self):
        super().__init__(
            url="https://openkey.cloud/v1",
            headers={
                "Content-Type": "application/json",
            },
            model_name="gpt-4o-mini",
            api_key="YOUR_API_KEY"
        )

    def get_response_with_messages(self, model_name, messages):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                temperature=0.0000001,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"GPT API call error: {str(e)}"

    def get_response_with_tool(self, model_name, messages, tools=tools, tool_choice="auto"):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                temperature=0.0000001,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            return response.choices[0].message
        except Exception as e:
            return f"GPT with tool API call error: {str(e)+str(messages)}"

# Qwen model implementation
class QwenModel(BaseModel):
    def __init__(self):
        super().__init__(
            url="https://dashscope.aliyuncs.com/compatible-mode/v1", 
            headers={
                "Content-Type": "application/json",
            },
            model_name="qwen2.5-coder-32b-instruct",
            api_key="YOUR_API_KEY"
        )

    def get_response_with_messages(self, model_name, messages):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name, # Use self.model_name instead of model_name parameter
                temperature=0.0000001,
                messages=messages
            )
            return response
        except Exception as e:
            return f"Qwen API call error: {str(e)}"

    def get_response_with_tool(self, model_name, messages, tools=tools, tool_choice="auto"):
        try:
            # Ensure message format is correct
            formatted_messages = []
            for msg in messages:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    formatted_messages.append(msg)
                else:
                    formatted_messages.append({
                        "role": "user",
                        "content": str(msg)
                    })

            response = self.client.chat.completions.create(
                model=self.model_name,
                temperature=0.0000001,
                messages=formatted_messages,
                tools=tools
            )
            
            # Return full response object, including tool_calls
            return response
        except Exception as e:
            return {
                "content": f"Qwen with tool API call error: {str(e)}",
                "tool_calls": None
            }

# Model factory class for getting responses from different models
class ModelFactory:
    _models = {
        "meta_llama": MetaLlamaModel,
        "deepseek": DeepSeekModel,
        "claude": ClaudeModel,
        "gpt": GPTModel,
        "qwen": QwenModel,
    }

    @staticmethod
    def get_model(model_name, question):
        model_class = ModelFactory._models.get(model_name)
        if not model_class:
            raise ValueError("Unsupported model name")
        model_instance = model_class()
        return model_instance.get_response(question)

def test_models():
    question = "What is your name, including version number? Then analyze which number is larger between 1.19 and 1.2"
    model_names = ["claude","meta_llama", "deepseek", "gpt", "qwen"]
    messages = [{"role": "user", "content": question}]
    messages_with_tool = [
        {"role": "user", "content": "Get the body of the function 'test_function'"}
    ]

    for model_name in model_names:
        # Get the model instance
        model_instance = ModelFactory._models[model_name]()

        # Test the get_response method
        response = model_instance.get_response(question)
        print(f"{model_name} model output (get_response): {response}")

    for model_name in model_names:
        # Get the model instance
        model_instance = ModelFactory._models[model_name]()

        # Test the get_response_with_messages method
        response_with_messages = model_instance.get_response_with_messages(model_instance.model_name, messages)
        print(f"{model_name} model output (get_response_with_messages): {response_with_messages}")

    for model_name in model_names:
        # Get the model instance
        model_instance = ModelFactory._models[model_name]()

        # Test the get_response_with_tool method
        try:
            response_with_tool = model_instance.get_response_with_tool(model_instance.model_name, messages_with_tool)
            print(f"{model_name} model output (get_response_with_tool): {response_with_tool}")
        except NotImplementedError:
            print(f"{model_name} model does not support get_response_with_tool method")

        print("---")  # Separator between model outputs

if __name__ == "__main__":
    test_models()