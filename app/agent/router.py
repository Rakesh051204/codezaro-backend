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
import subprocess
from datetime import datetime
from github import Github, GithubException

router = APIRouter(prefix="/agent", tags=["agent"])

# Base directory for all persistent workspaces
WORKSPACE_BASE = os.path.join(os.getcwd(), "workspaces")
os.makedirs(WORKSPACE_BASE, exist_ok=True)

def get_workspace_path(user_id: int, session_id: int) -> str:
    return os.path.join(WORKSPACE_BASE, str(user_id), str(session_id))

def clone_or_update_repo(repo_url: str, target_dir: str) -> str:
    if os.path.exists(os.path.join(target_dir, ".git")):
        subprocess.run(["git", "-C", target_dir, "pull"], check=False)
        return "Repository updated"
    else:
        subprocess.run(["git", "clone", repo_url, target_dir], check=True)
        return "Repository cloned"

def has_uncommitted_changes(repo_dir: str) -> bool:
    result = subprocess.run(
        ["git", "-C", repo_dir, "status", "--porcelain"],
        capture_output=True, text=True
    )
    return bool(result.stdout.strip())

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

class PRCreate(BaseModel):
    session_id: int
    title: str
    body: str
    branch_name: Optional[str] = None

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
    # Create session record first
    new_session = AgentSession(
        user_id=current_user.id,
        workspace_path="",
        task=session_data.task,
        repo_url=session_data.repo_url,
        status=AgentSessionStatus.CREATED,
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    # Now create workspace directory
    workspace_path = get_workspace_path(current_user.id, new_session.id)
    os.makedirs(workspace_path, exist_ok=True)
    new_session.workspace_path = workspace_path
    db.commit()
    db.refresh(new_session)

    # Clone repo if provided
    if session_data.repo_url:
        try:
            clone_or_update_repo(session_data.repo_url, workspace_path)
        except Exception as e:
            new_session.status = AgentSessionStatus.FAILED
            db.commit()
            raise HTTPException(status_code=400, detail=f"Failed to clone repo: {str(e)}")

    return {"session_id": new_session.id, "workspace_path": workspace_path}


@router.get("/sessions")
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
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

    session = None
    if task.session_id:
        session = db.query(AgentSession).filter(
            AgentSession.id == task.session_id,
            AgentSession.user_id == current_user.id
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        workspace_path = session.workspace_path
        session.status = AgentSessionStatus.IN_PROGRESS
        db.commit()
    else:
        # Create new session
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
        workspace_path = get_workspace_path(current_user.id, new_session.id)
        os.makedirs(workspace_path, exist_ok=True)
        new_session.workspace_path = workspace_path
        new_session.status = AgentSessionStatus.IN_PROGRESS
        db.commit()
        session = new_session

        if task.repo_url:
            try:
                clone_or_update_repo(task.repo_url, workspace_path)
            except Exception as e:
                session.status = AgentSessionStatus.FAILED
                db.commit()
                raise HTTPException(status_code=400, detail=f"Failed to clone repo: {str(e)}")

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
""" }
        ]

        step_num = 0
        while step_num < 10:
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

            action_id = str(uuid.uuid4())
            future = asyncio.get_event_loop().create_future()
            pending_approvals[action_id] = future

            yield f"data: {json.dumps({'type': 'action_proposed', 'action_id': action_id, 'tool': action, 'params': action_input})}\n\n"

            try:
                approved = await asyncio.wait_for(future, timeout=60.0)
            except asyncio.TimeoutError:
                approved = False
            finally:
                pending_approvals.pop(action_id, None)

            if approved:
                result = agent.execute_tool(action, action_input)
                yield f"data: {json.dumps({'type': 'tool_result', 'result': result})}\n\n"
                history.append({"role": "assistant", "content": content})
                history.append({"role": "user", "content": f"Tool result:\n{result}"})
            else:
                yield f"data: {json.dumps({'type': 'action_rejected', 'action_id': action_id})}\n\n"
                history.append({"role": "assistant", "content": content})
                history.append({"role": "user", "content": "Action rejected. Proceed."})

        if session.status != AgentSessionStatus.COMPLETED:
            session.status = AgentSessionStatus.COMPLETED
            db.commit()
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ----- PR creation endpoint -----
@router.post("/pr")
async def create_pull_request(
    pr_data: PRCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = db.query(AgentSession).filter(
        AgentSession.id == pr_data.session_id,
        AgentSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.repo_url:
        raise HTTPException(status_code=400, detail="Session has no repository URL")

    workspace = session.workspace_path
    if not os.path.exists(workspace):
        raise HTTPException(status_code=400, detail="Workspace directory missing")

    if not has_uncommitted_changes(workspace):
        raise HTTPException(status_code=400, detail="No changes to commit")

    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        raise HTTPException(status_code=500, detail="GitHub token not configured")

    g = Github(github_token)

    repo_url = session.repo_url
    if repo_url.endswith(".git"):
        repo_url = repo_url[:-4]
    parts = repo_url.split("/")
    repo_name = f"{parts[-2]}/{parts[-1]}"

    try:
        repo = g.get_repo(repo_name)
    except GithubException as e:
        raise HTTPException(status_code=400, detail=f"Failed to access repo: {e.data}")

    branch_name = pr_data.branch_name or f"codezaro-agent-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    try:
        default_branch = repo.default_branch
        ref = repo.get_git_ref(f"heads/{default_branch}")
        latest_sha = ref.object.sha
        repo.create_git_ref(f"refs/heads/{branch_name}", latest_sha)
    except GithubException as e:
        raise HTTPException(status_code=400, detail=f"Failed to create branch: {e.data}")

    try:
        subprocess.run(["git", "-C", workspace, "add", "."], check=True)
        subprocess.run(
            ["git", "-C", workspace, "commit", "-m", pr_data.title or "CodeZaro agent changes"],
            check=True
        )
        auth_url = repo_url.replace("https://", f"https://{github_token}@")
        subprocess.run(
            ["git", "-C", workspace, "remote", "set-url", "origin", auth_url],
            check=True
        )
        subprocess.run(
            ["git", "-C", workspace, "push", "origin", branch_name],
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Git operation failed: {e.stderr}")

    try:
        pr = repo.create_pull(
            title=pr_data.title or "CodeZaro agent changes",
            body=pr_data.body or "Automated changes from CodeZaro agent",
            head=branch_name,
            base=default_branch,
        )
        return {"pr_url": pr.html_url, "pr_number": pr.number}
    except GithubException as e:
        raise HTTPException(status_code=500, detail=f"Failed to create PR: {e.data}")