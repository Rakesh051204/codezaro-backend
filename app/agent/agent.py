import os
import subprocess
import json
from typing import List, Dict, Any
from groq import Groq
from app.config import settings

class CodeZaroAgent:
    def __init__(self, workspace_dir: str = "./workspace"):
        self.workspace = workspace_dir
        os.makedirs(self.workspace, exist_ok=True)
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.tools = [
            {
                "name": "read_file",
                "description": "Read the contents of a file in the workspace",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write content to a file in the workspace (creates or overwrites)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file"},
                        "content": {"type": "string", "description": "Content to write"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "run_command",
                "description": "Run a shell command in the workspace (e.g., 'python test.py', 'git diff')",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to run"}
                    },
                    "required": ["command"]
                }
            }
        ]

    def read_file(self, path: str) -> str:
        full_path = os.path.join(self.workspace, path)
        if not os.path.exists(full_path):
            return f"Error: File {path} not found"
        with open(full_path, "r") as f:
            return f.read()

    def write_file(self, path: str, content: str) -> str:
        full_path = os.path.join(self.workspace, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)
        return f"File {path} written successfully"

    def run_command(self, command: str) -> str:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return "Command timed out after 30 seconds"

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        if tool_name == "read_file":
            return self.read_file(parameters["path"])
        elif tool_name == "write_file":
            return self.write_file(parameters["path"], parameters["content"])
        elif tool_name == "run_command":
            return self.run_command(parameters["command"])
        else:
            return f"Unknown tool: {tool_name}"

    def plan_and_act(self, task: str, max_steps: int = 10) -> List[Dict[str, Any]]:
        history = [
            {"role": "system", "content": f"""
You are an AI coding assistant that can use tools to accomplish tasks in a workspace.

Workspace path: {self.workspace}

Available tools:
- read_file(path): reads a file
- write_file(path, content): writes content to a file
- run_command(command): runs a shell command (e.g., 'ls', 'python script.py')

Your task: {task}

You must respond with a JSON object containing:
- "thought": your reasoning
- "action": one of the tool names
- "action_input": a dictionary of parameters for that tool
- "stop": true if you think the task is complete, false otherwise

If you need to chain multiple steps, do them one at a time.
Do not include any other text in your response besides the JSON.
""" }
        ]

        steps = []
        for _ in range(max_steps):
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=history,
                temperature=0.0,
                max_tokens=500
            )
            content = response.choices[0].message.content

            try:
                decision = json.loads(content)
            except json.JSONDecodeError:
                import re
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    decision = json.loads(match.group(0))
                else:
                    decision = {"stop": True, "thought": "Could not parse decision, stopping."}

            steps.append(decision)

            if decision.get("stop", False):
                break

            action = decision.get("action")
            action_input = decision.get("action_input", {})
            if action and action in [t["name"] for t in self.tools]:
                result = self.execute_tool(action, action_input)
                history.append({"role": "assistant", "content": content})
                history.append({"role": "user", "content": f"Tool result:\n{result}"})
            else:
                break

        return steps