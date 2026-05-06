"""Helpers for durable ACP resume state.

ACP ``session/load`` can only work after a sandbox recycle if both OpenHands'
resume signal and the ACP server's own session file are restored into the new
sandbox before the SDK creates the conversation.
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import tempfile
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from openhands.agent_server.models import StartACPConversationRequest
from openhands.app_server.file_store.files import FileStore
from openhands.app_server.utils.async_utils import call_sync_from_async
from openhands.sdk.event import ConversationStateUpdateEvent
from openhands.sdk.workspace.remote.async_remote_workspace import AsyncRemoteWorkspace

ACP_STATE_SNAPSHOT_FILE = "state.json"
CLAUDE_SESSION_SNAPSHOT_FILE = "claude-session.jsonl.b64"
REMOTE_CONVERSATIONS_DIR_ENV = "OH_CONVERSATIONS_PATH"
REMOTE_DEFAULT_CONVERSATIONS_DIR = "/workspace/conversations"


@dataclass(frozen=True)
class ACPSessionState:
    session_id: str
    cwd: str
    state_snapshot: dict[str, Any] | None = None


@dataclass(frozen=True)
class ACPRestoreResult:
    restored_base_state: bool = False
    restored_claude_session: bool = False


def extract_acp_session_state(
    event: ConversationStateUpdateEvent,
) -> ACPSessionState | None:
    """Extract ACP session state from a ConversationStateUpdateEvent."""
    state_snapshot: dict[str, Any] | None = None
    agent_state: dict[str, Any] | None = None

    if event.key == "full_state" and isinstance(event.value, dict):
        state_snapshot = event.value
        maybe_agent_state = state_snapshot.get("agent_state")
        if isinstance(maybe_agent_state, dict):
            agent_state = maybe_agent_state
    elif event.key == "agent_state" and isinstance(event.value, dict):
        agent_state = event.value

    if not agent_state:
        return None

    session_id = agent_state.get("acp_session_id")
    cwd = agent_state.get("acp_session_cwd")
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    if not isinstance(cwd, str) or not cwd.strip():
        return None

    return ACPSessionState(
        session_id=session_id,
        cwd=cwd,
        state_snapshot=state_snapshot,
    )


def encode_claude_project_path(cwd: str) -> str:
    """Match Claude Code's ``~/.claude/projects`` path encoding."""
    return "".join(c if c.isalnum() else "-" for c in cwd)


def _conversation_store_prefix(conversation_id: UUID) -> str:
    return f"app-conversations/{conversation_id.hex}/acp"


def _store_path(conversation_id: UUID, filename: str) -> str:
    return f"{_conversation_store_prefix(conversation_id)}/{filename}"


async def persist_acp_state_snapshot(
    file_store: FileStore,
    conversation_id: UUID,
    state_snapshot: dict[str, Any],
) -> None:
    """Persist the latest SDK full-state snapshot durably."""
    await call_sync_from_async(
        file_store.write,
        _store_path(conversation_id, ACP_STATE_SNAPSHOT_FILE),
        json.dumps(state_snapshot, separators=(",", ":")),
    )


async def load_acp_state_snapshot(
    file_store: FileStore,
    conversation_id: UUID,
) -> dict[str, Any] | None:
    try:
        snapshot = await call_sync_from_async(
            file_store.read,
            _store_path(conversation_id, ACP_STATE_SNAPSHOT_FILE),
        )
    except FileNotFoundError:
        return None
    return json.loads(snapshot)


async def persist_claude_session_snapshot(
    file_store: FileStore,
    remote_workspace: AsyncRemoteWorkspace,
    conversation_id: UUID,
    session_state: ACPSessionState,
) -> bool:
    """Snapshot Claude Code's per-session JSONL file from the sandbox."""
    command = _build_read_claude_session_command(
        session_state.cwd, session_state.session_id
    )
    result = await remote_workspace.execute_command(command, timeout=30.0)
    if result.exit_code != 0:
        return False

    encoded = result.stdout.strip()
    if not encoded:
        return False

    await call_sync_from_async(
        file_store.write,
        _store_path(conversation_id, CLAUDE_SESSION_SNAPSHOT_FILE),
        encoded,
    )
    return True


async def restore_acp_resume_artifacts(
    file_store: FileStore,
    remote_workspace: AsyncRemoteWorkspace,
    start_request: StartACPConversationRequest,
    session_id: str,
    session_cwd: str,
) -> ACPRestoreResult:
    """Restore OpenHands and Claude Code ACP resume artifacts into a sandbox."""
    base_state_restored = await _restore_base_state(
        file_store=file_store,
        remote_workspace=remote_workspace,
        start_request=start_request,
        session_id=session_id,
        session_cwd=session_cwd,
    )
    claude_restored = await _restore_claude_session_file(
        file_store=file_store,
        remote_workspace=remote_workspace,
        conversation_id=start_request.conversation_id,
        session_id=session_id,
        session_cwd=session_cwd,
    )
    return ACPRestoreResult(
        restored_base_state=base_state_restored,
        restored_claude_session=claude_restored,
    )


async def _restore_base_state(
    file_store: FileStore,
    remote_workspace: AsyncRemoteWorkspace,
    start_request: StartACPConversationRequest,
    session_id: str,
    session_cwd: str,
) -> bool:
    snapshot = await load_acp_state_snapshot(file_store, start_request.conversation_id)
    if snapshot is None:
        snapshot = build_minimal_acp_base_state(
            start_request=start_request,
            session_id=session_id,
            session_cwd=session_cwd,
        )
    else:
        agent_state = snapshot.get("agent_state")
        if not isinstance(agent_state, dict):
            agent_state = {}
        agent_state["acp_session_id"] = session_id
        agent_state["acp_session_cwd"] = session_cwd
        snapshot["agent_state"] = agent_state

    remote_base_state_path = await _remote_base_state_path(
        remote_workspace, start_request.conversation_id
    )
    await _upload_bytes(
        remote_workspace,
        json.dumps(snapshot, separators=(",", ":")).encode("utf-8"),
        remote_base_state_path,
    )
    return True


def build_minimal_acp_base_state(
    start_request: StartACPConversationRequest,
    session_id: str,
    session_cwd: str,
) -> dict[str, Any]:
    """Build the smallest SDK base_state.json needed to trigger ACP load_session."""
    return {
        "id": str(start_request.conversation_id),
        "agent": start_request.agent.model_dump(
            mode="json", context={"expose_secrets": True}
        ),
        "workspace": start_request.workspace.model_dump(mode="json"),
        "max_iterations": start_request.max_iterations,
        "stuck_detection": start_request.stuck_detection,
        "agent_state": {
            "acp_session_id": session_id,
            "acp_session_cwd": session_cwd,
        },
        "tags": start_request.tags or {},
    }


async def _restore_claude_session_file(
    file_store: FileStore,
    remote_workspace: AsyncRemoteWorkspace,
    conversation_id: UUID,
    session_id: str,
    session_cwd: str,
) -> bool:
    try:
        encoded = await call_sync_from_async(
            file_store.read,
            _store_path(conversation_id, CLAUDE_SESSION_SNAPSHOT_FILE),
        )
    except FileNotFoundError:
        return False

    try:
        contents = base64.b64decode(encoded.encode("ascii"), validate=True)
    except Exception:
        return False

    destination = await _remote_claude_session_path(
        remote_workspace, session_cwd, session_id
    )
    await _upload_bytes(remote_workspace, contents, destination)
    return True


async def _upload_bytes(
    remote_workspace: AsyncRemoteWorkspace,
    contents: bytes,
    destination: str,
) -> None:
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    try:
        result = await remote_workspace.file_upload(tmp_path, destination)
        if not result.success:
            raise RuntimeError(
                f"Failed to upload {destination}: {result.error or 'unknown error'}"
            )
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass


async def _remote_base_state_path(
    remote_workspace: AsyncRemoteWorkspace,
    conversation_id: UUID,
) -> str:
    command = (
        "python3 - <<'PY'\n"
        "import os\n"
        "from pathlib import Path\n"
        f"base = os.environ.get({REMOTE_CONVERSATIONS_DIR_ENV!r}, "
        f"{REMOTE_DEFAULT_CONVERSATIONS_DIR!r})\n"
        f"path = Path(base) / {conversation_id.hex!r}\n"
        "path.mkdir(parents=True, exist_ok=True)\n"
        'print(path / "base_state.json")\n'
        "PY"
    )
    result = await remote_workspace.execute_command(command, timeout=10.0)
    if result.exit_code != 0:
        raise RuntimeError(result.stderr or "Failed to create conversation state dir")
    return result.stdout.strip()


async def _remote_claude_session_path(
    remote_workspace: AsyncRemoteWorkspace,
    cwd: str,
    session_id: str,
) -> str:
    encoded = encode_claude_project_path(cwd)
    command = (
        "python3 - <<'PY'\n"
        "import os\n"
        "from pathlib import Path\n"
        'config = os.environ.get("CLAUDE_CONFIG_DIR") or '
        'str(Path.home() / ".claude")\n'
        f'path = Path(config) / "projects" / {encoded!r}\n'
        "path.mkdir(parents=True, exist_ok=True)\n"
        f'print(path / ({session_id!r} + ".jsonl"))\n'
        "PY"
    )
    result = await remote_workspace.execute_command(command, timeout=10.0)
    if result.exit_code != 0:
        raise RuntimeError(result.stderr or "Failed to create Claude session dir")
    return result.stdout.strip()


def _build_read_claude_session_command(cwd: str, session_id: str) -> str:
    return (
        f"ACP_SESSION_CWD={shlex.quote(cwd)} "
        f"ACP_SESSION_ID={shlex.quote(session_id)} "
        "python3 - <<'PY'\n"
        "import base64\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        'cwd = os.environ["ACP_SESSION_CWD"]\n'
        'sid = os.environ["ACP_SESSION_ID"]\n'
        'encoded = "".join(c if c.isalnum() else "-" for c in cwd)\n'
        'config = os.environ.get("CLAUDE_CONFIG_DIR") or '
        'str(Path.home() / ".claude")\n'
        'path = Path(config) / "projects" / encoded / f"{sid}.jsonl"\n'
        "if not path.is_file():\n"
        "    sys.exit(42)\n"
        'sys.stdout.write(base64.b64encode(path.read_bytes()).decode("ascii"))\n'
        "PY"
    )
