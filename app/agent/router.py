from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.deps import get_current_user
from app.models import User
from app.agent.agent import CodeZaroAgent
import tempfile
import json
import asyncio

router = APIRouter(prefix="/agent", tags=["agent"])

class AgentTask(BaseModel):
    task: str
    repo_url: str = None

@router.post("/run")
async def run_agent(task: AgentTask, current_user: User = Depends(get_current_user)):
    if current_user.tier != "PRO":
        raise HTTPException(status_code=403, detail="Agent mode requires Pro subscription")
    workspace = tempfile.mkdtemp(prefix="codezaro_agent_")
    agent = CodeZaroAgent(workspace_dir=workspace)
    try:
        steps = agent.plan_and_act(task.task, max_steps=10)
        return {"success": True, "steps": steps, "workspace": workspace}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/stream")
async def stream_agent(task: AgentTask, current_user: User = Depends(get_current_user)):
    if current_user.tier != "PRO":
        raise HTTPException(status_code=403, detail="Agent mode requires Pro subscription")

    workspace = tempfile.mkdtemp(prefix="codezaro_agent_")
    agent = CodeZaroAgent(workspace_dir=workspace)

    async def event_generator():
        history = [
            {"role": "system", "content": f"""
You are an AI coding assistant that can use tools to accomplish tasks in a workspace.

Workspace path: {workspace}

Available tools:
- read_file(path): reads a file
- write_file(path, content): writes content to a file
- run_command(command): runs a shell command (e.g., 'ls', 'python script.py')

Your task: {task.task}

You must respond with a JSON object containing:
- "thought": your reasoning
- "action": one of the tool names
- "action_input": a dictionary of parameters for that tool
- "stop": true if you think the task is complete, false otherwise
""" }
        ]

        for step_num in range(10):
            # Get decision from LLM
            response = agent.client.chat.completions.create(
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

            # Send the step to the client
            yield f"data: {json.dumps({'step': step_num + 1, 'decision': decision})}\n\n"

            if decision.get("stop", False):
                yield f"data: {json.dumps({'done': True})}\n\n"
                break

            action = decision.get("action")
            action_input = decision.get("action_input", {})
            if action and action in [t["name"] for t in agent.tools]:
                result = agent.execute_tool(action, action_input)
                # Send tool result too
                yield f"data: {json.dumps({'tool_result': result})}\n\n"
                history.append({"role": "assistant", "content": content})
                history.append({"role": "user", "content": f"Tool result:\n{result}"})
            else:
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")