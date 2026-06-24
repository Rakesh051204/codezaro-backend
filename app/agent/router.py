from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.deps import get_current_user
from app.models import User
from app.agent.agent import CodeZaroAgent
import tempfile
import json
import asyncio
import uuid
from typing import Dict, Optional

router = APIRouter(prefix="/agent", tags=["agent"])

class AgentTask(BaseModel):
    task: str
    repo_url: str = None

class ApprovalDecision(BaseModel):
    action_id: str
    approved: bool

# In-memory store for pending approvals
pending_approvals: Dict[str, asyncio.Future] = {}


@router.post("/approve")
async def approve_action(decision: ApprovalDecision, current_user: User = Depends(get_current_user)):
    action_id = decision.action_id
    if action_id not in pending_approvals:
        raise HTTPException(status_code=404, detail="Action not found or already approved")
    future = pending_approvals[action_id]
    if future.done():
        raise HTTPException(status_code=400, detail="Action already decided")
    future.set_result(decision.approved)
    return {"status": "ok"}


@router.post("/stream")
async def stream_agent(task: AgentTask, current_user: User = Depends(get_current_user)):
    # Temporarily bypass Pro tier check for testing
    # if current_user.tier != "PRO":
    #     raise HTTPException(status_code=403, detail="Agent mode requires Pro subscription")

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

If you need to chain multiple steps, do them one at a time.
Do not include any other text in your response besides the JSON.
""" }
        ]

        step_num = 0
        while step_num < 10:
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

            step_num += 1

            # Send thought and action (if any) as a normal step
            yield f"data: {json.dumps({'step': step_num, 'decision': decision})}\n\n"

            if decision.get("stop", False):
                yield f"data: {json.dumps({'done': True})}\n\n"
                break

            action = decision.get("action")
            action_input = decision.get("action_input", {})

            if not action or action not in [t["name"] for t in agent.tools]:
                break

            # --- Approval phase ---
            action_id = str(uuid.uuid4())
            # Create a Future that will be resolved by the /approve endpoint
            future = asyncio.get_event_loop().create_future()
            pending_approvals[action_id] = future

            # Send proposal event
            yield f"data: {json.dumps({'type': 'action_proposed', 'action_id': action_id, 'tool': action, 'params': action_input})}\n\n"

            # Wait for approval (with timeout)
            try:
                approved = await asyncio.wait_for(future, timeout=60.0)
            except asyncio.TimeoutError:
                # If no response, treat as reject
                approved = False
            finally:
                pending_approvals.pop(action_id, None)

            if approved:
                # Execute tool
                result = agent.execute_tool(action, action_input)
                yield f"data: {json.dumps({'type': 'tool_result', 'result': result})}\n\n"
                history.append({"role": "assistant", "content": content})
                history.append({"role": "user", "content": f"Tool result:\n{result}"})
            else:
                # Rejected: skip this action and continue
                yield f"data: {json.dumps({'type': 'action_rejected', 'action_id': action_id})}\n\n"
                # Optionally add a message to history saying the action was rejected
                history.append({"role": "assistant", "content": content})
                history.append({"role": "user", "content": "Action was rejected by the user. Proceed with the next step."})

        # End of loop
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")