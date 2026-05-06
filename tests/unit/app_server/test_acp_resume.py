import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from openhands.agent_server.models import StartACPConversationRequest
from openhands.app_server.app_conversation.acp_resume import (
    ACPSessionState,
    encode_claude_project_path,
    extract_acp_session_state,
    persist_claude_session_snapshot,
    restore_acp_resume_artifacts,
)
from openhands.app_server.file_store.memory import InMemoryFileStore
from openhands.sdk import LocalWorkspace
from openhands.sdk.agent.acp_agent import ACPAgent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.event import ConversationStateUpdateEvent
from openhands.sdk.workspace import CommandResult, FileOperationResult


class LocalRemoteWorkspace:
    def __init__(self, home: Path, conversations_dir: Path):
        self.home = home
        self.conversations_dir = conversations_dir

    async def execute_command(
        self,
        command: str,
        cwd: str | Path | None = None,
        timeout: float = 30.0,
    ) -> CommandResult:
        env = {
            **os.environ,
            "HOME": str(self.home),
            "OH_CONVERSATIONS_PATH": str(self.conversations_dir),
        }
        result = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return CommandResult(
            command=command,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            timeout_occurred=False,
        )

    async def file_upload(
        self,
        source_path: str | Path,
        destination_path: str | Path,
    ) -> FileOperationResult:
        destination = Path(destination_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, destination)
        return FileOperationResult(
            success=True,
            source_path=str(source_path),
            destination_path=str(destination_path),
            file_size=destination.stat().st_size,
        )


def test_extract_acp_session_state_from_full_state():
    event = ConversationStateUpdateEvent(
        key="full_state",
        value={
            "agent_state": {
                "acp_session_id": "sid-123",
                "acp_session_cwd": "/workspace/project",
            }
        },
    )

    state = extract_acp_session_state(event)

    assert state == ACPSessionState(
        session_id="sid-123",
        cwd="/workspace/project",
        state_snapshot=event.value,
    )


@pytest.mark.asyncio
async def test_persist_and_restore_claude_session_snapshot(tmp_path: Path):
    home = tmp_path / "home"
    conversations_dir = tmp_path / "conversations"
    remote = LocalRemoteWorkspace(home=home, conversations_dir=conversations_dir)
    file_store = InMemoryFileStore()
    conversation_id = uuid4()
    session_id = "b9d174a1-b4a6-4bb5-a5f7-a389d04c4d6f"
    cwd = "/private/tmp/acp-live-verify-workspace"
    encoded_cwd = encode_claude_project_path(cwd)
    claude_session = home / ".claude" / "projects" / encoded_cwd / f"{session_id}.jsonl"
    claude_session.parent.mkdir(parents=True)
    real_shape_jsonl = (
        json.dumps({"type": "user", "message": {"content": "remember blue"}})
        + "\n"
        + json.dumps({"type": "assistant", "message": {"content": "noted"}})
        + "\n"
    ).encode()
    claude_session.write_bytes(real_shape_jsonl)

    snapshotted = await persist_claude_session_snapshot(
        file_store=file_store,
        remote_workspace=remote,  # type: ignore[arg-type]
        conversation_id=conversation_id,
        session_state=ACPSessionState(session_id=session_id, cwd=cwd),
    )
    claude_session.unlink()

    request = StartACPConversationRequest(
        workspace=LocalWorkspace(working_dir=cwd),
        conversation_id=conversation_id,
        agent=ACPAgent(acp_command=["claude-agent-acp"]),
    )
    result = await restore_acp_resume_artifacts(
        file_store=file_store,
        remote_workspace=remote,  # type: ignore[arg-type]
        start_request=request,
        session_id=session_id,
        session_cwd=cwd,
    )

    assert snapshotted is True
    assert result.restored_base_state is True
    assert result.restored_claude_session is True
    assert claude_session.read_bytes() == real_shape_jsonl

    base_state = json.loads(
        (conversations_dir / conversation_id.hex / "base_state.json").read_text()
    )
    assert base_state["agent_state"] == {
        "acp_session_id": session_id,
        "acp_session_cwd": cwd,
    }
    validated_state = ConversationState.model_validate(base_state)
    assert validated_state.agent_state["acp_session_id"] == session_id
