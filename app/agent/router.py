from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
from app.deps import get_current_user
from app.models import User, AgentSession, AgentSessionStatus
from app.agent.agent import CodeZaroAgent
from app.database import get_db
from sqlalchemy.orm import Session
import tempfile
import json
import asyncio
import uuid
import os
import shutil
import subprocess
from datetime import datetime

router = APIRouter(prefix="/agent", tags=["agent"])

# Base directory for all persistent workspaces
WORKSPACE_BASE = os.path.join(os.getcwd(), "workspaces")
os.makedirs(WORKSPACE_BASE, exist_ok=True)

def get_workspace_path(user_id: int, session_id: int) -> str:
    """Return the full path for a session's workspace"""
    return os.path.join(WORKSPACE_BASE, str(user_id), str(session_id))

def clone_or_update_repo(repo_url: str, target_dir: str) -> str:
    """Clone a git repo into target_dir, or pull if already exists"""
    if os.path.exists(os.path.join(target_dir, ".git")):
        # Repo exists, pull latest
        subprocess.run(["git", "-C", target_dir, "pull"], check=False)
        return "Repository updated"
    else:
        # Clone fresh
        subprocess.run(["git", "clone", repo_url, target_dir], check=True)
        return "Repository cloned"

# ----- Models -----
class AgentTask(BaseModel):
    task: str
    session_id: Optional[int] = None
    repo_url: Optional[str] = None

class ApprovalDecision(BaseModel):
    action_id: str
    approved: bool

class SessionCreate(BaseModel):
    task: str
    repo_url: Optional[str] = None

# In-memory store for pending approvals
pending_approvals: Dict[str, asyncio.Future] = {}

# ----- Endpoints -----

@router.post("/sessions")
def create_session(
    session_data: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new agent session for the current user."""
    # Create workspace directory
    # We'll create the session first, then the path
    new_session = AgentSession(
        user_id=current_user.id,
        workspace_path="",  # placeholder, updated after session created
        task=session_data.task,
        repo_url=session_data.repo_url,
        status=AgentSessionStatus.CREATED,
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    # Now we have the session ID, create the workspace path
    workspace_path = get_workspace_path(current_user.id, new_session.id)
    os.makedirs(workspace_path, exist_ok=True)

    # Update session with the actual path
    new_session.workspace_path = workspace_path
    db.commit()
    db.refresh(new_session)

    # If repo_url is provided, clone the repo into the workspace
    if session_data.repo_url:
        try:
            clone_or_update_repo(session_data.repo_url, workspace_path)
        except Exception as e:
            # Mark session as failed if cloning fails
            new_session.status = AgentSessionStatus.FAILED
            db.commit()
            raise HTTPException(status_code=400, detail=f"Failed to clone repo: {str(e)}")

    return {"session_id": new_session.id, "workspace_path": workspace_path}


@router.get("/sessions")
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all agent sessions for the current user."""
    sessions = db.query(AgentSession).filter(
        AgentSession.user_id == current_user.id
    ).order_by(AgentSession.created_at.desc()).all()
    return [
        {
            "id": s.id,
            "task": s.task,
            "repo_url": s.repo_url,
            "status": s.status.value,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
        }
        for s in sessions
    ]


@router.post("/approve")
async def approve_action(
    decision: ApprovalDecision,
    current_user: User = Depends(get_current_user)
):
    action_id = decision.action_id
    if action_id not in pending_approvals:
        raise HTTPException(status_code=404, detail="Action not found or already approved")
    future = pending_approvals[action_id]
    if future.done():
        raise HTTPException(status_code=400, detail="Action already decided")
    future.set_result(decision.approved)
    return {"status": "ok"}


@router.post("/stream")
async def stream_agent(
    task: AgentTask,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Temporarily bypass Pro tier check for testing
    # if current_user.tier != "PRO":
    #     raise HTTPException(status_code=403, detail="Agent mode requires Pro subscription")

    # Load or create session
    session = None
    if task.session_id:
        # Resume existing session
        session = db.query(AgentSession).filter(
            AgentSession.id == task.session_id,
            AgentSession.user_id == current_user.id
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        workspace_path = session.workspace_path
        # Update status to in_progress
        session.status = AgentSessionStatus.IN_PROGRESS
        db.commit()
    else:
        # Create a new session
        workspace_path = get_workspace_path(current_user.id, 0)  # placeholder for now
        # We'll create the session after we know the ID
        new_session = AgentSession(
            user_id=current_user.id,
            workspace_path="",
            task=task.task,
            repo_url=task.repo_url,
            status=AgentSessionStatus.CREATED,
        )
        db.add(new_session)
        db.commit()
        db.refresh(new_session)

        # Now we have the ID, create the workspace directory
        workspace_path = get_workspace_path(current_user.id, new_session.id)
        os.makedirs(workspace_path, exist_ok=True)

        new_session.workspace_path = workspace_path
        new_session.status = AgentSessionStatus.IN_PROGRESS
        db.commit()
        session = new_session

        # If repo_url is provided, clone the repo
        if task.repo_url:
            try:
                clone_or_update_repo(task.repo_url, workspace_path)
            except Exception as e:
                session.status = AgentSessionStatus.FAILED
                db.commit()
                raise HTTPException(status_code=400, detail=f"Failed to clone repo: {str(e)}")

    # Initialize the agent with the persistent workspace
    agent = CodeZaroAgent(workspace_dir=workspace_path)

    async def event_generator():
        history = [
            {"role": "system", "content": f"""
You are an AI coding assistant that can use tools to accomplish tasks in a workspace.

Workspace path: {workspace_path}

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
                session.status = AgentSessionStatus.COMPLETED
                db.commit()
                yield f"data: {json.dumps({'done': True})}\n\n"
                break

            action = decision.get("action")
            action_input = decision.get("action_input", {})

            if not action or action not in [t["name"] for t in agent.tools]:
                break

            # --- Approval phase ---
            action_id = str(uuid.uuid4())
            future = asyncio.get_event_loop().create_future()
            pending_approvals[action_id] = future

            # Send proposal event
            yield f"data: {json.dumps({'type': 'action_proposed', 'action_id': action_id, 'tool': action, 'params': action_input})}\n\n"

            # Wait for approval (with timeout)
            try:
                approved = await asyncio.wait_for(future, timeout=60.0)
            except asyncio.TimeoutError:
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
                # Rejected
                yield f"data: {json.dumps({'type': 'action_rejected', 'action_id': action_id})}\n\n"
                history.append({"role": "assistant", "content": content})
                history.append({"role": "user", "content": "Action was rejected by the user. Proceed with the next step."})

        # End of loop (max steps reached or error)
        if session.status != AgentSessionStatus.COMPLETED:
            session.status = AgentSessionStatus.COMPLETED  # or FAILED if we have error info
            db.commit()
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")