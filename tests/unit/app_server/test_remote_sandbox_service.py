"""Tests for RemoteSandboxService.

This module tests the RemoteSandboxService implementation, focusing on:
- Remote runtime API communication and error handling
- Sandbox lifecycle management (start, pause, resume, delete)
- Status mapping from remote runtime to internal sandbox statuses
- Environment variable injection for CORS and webhooks
- Data transformation from remote runtime to SandboxInfo objects
- User-scoped sandbox operations and security
- Pagination and search functionality
- Error handling for HTTP failures and edge cases
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from openhands.app_server.errors import SandboxError
from openhands.app_server.sandbox.remote_sandbox_service import (
    ALLOW_CORS_ORIGINS_VARIABLE,
    STATUS_MAPPING,
    WEBHOOK_CALLBACK_VARIABLE,
    RemoteSandboxService,
    StoredRemoteSandbox,
)
from openhands.app_server.sandbox.sandbox_models import (
    AGENT_SERVER,
    VSCODE,
    WORKER_1,
    WORKER_2,
    SandboxInfo,
    SandboxStatus,
)
from openhands.app_server.sandbox.sandbox_spec_models import SandboxSpecInfo
from openhands.app_server.user.user_context import UserContext


@pytest.fixture
def mock_sandbox_spec_service():
    """Mock SandboxSpecService for testing."""
    mock_service = AsyncMock()
    mock_spec = SandboxSpecInfo(
        id='test-image:latest',
        command=['/usr/local/bin/openhands-agent-server', '--port', '60000'],
        initial_env={'TEST_VAR': 'test_value'},
        working_dir='/workspace/project',
    )
    mock_service.get_default_sandbox_spec.return_value = mock_spec
    mock_service.get_sandbox_spec.return_value = mock_spec
    return mock_service


@pytest.fixture
def mock_user_context():
    """Mock UserContext for testing."""
    mock_context = AsyncMock(spec=UserContext)
    mock_context.get_user_id.return_value = 'test-user-123'
    return mock_context


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient for testing."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def mock_db_session():
    """Mock database session for testing."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def remote_sandbox_service(
    mock_sandbox_spec_service, mock_user_context, mock_httpx_client, mock_db_session
):
    """Create RemoteSandboxService instance with mocked dependencies."""
    return RemoteSandboxService(
        sandbox_spec_service=mock_sandbox_spec_service,
        api_url='https://api.example.com',
        api_key='test-api-key',
        web_url='https://web.example.com',
        resource_factor=1,
        runtime_class='gvisor',
        start_sandbox_timeout=120,
        max_num_sandboxes=10,
        user_context=mock_user_context,
        httpx_client=mock_httpx_client,
        db_session=mock_db_session,
    )


def create_runtime_data(
    session_id: str = 'test-sandbox-123',
    status: str = 'running',
    url: str = 'https://sandbox.example.com',
    session_api_key: str = 'test-session-key',
    runtime_id: str = 'runtime-456',
) -> dict[str, Any]:
    """Helper function to create runtime data for testing."""
    return {
        'session_id': session_id,
        'status': status,
        'url': url,
        'session_api_key': session_api_key,
        'runtime_id': runtime_id,
    }


def create_stored_sandbox(
    sandbox_id: str = 'test-sandbox-123',
    user_id: str = 'test-user-123',
    spec_id: str = 'test-image:latest',
    created_at: datetime | None = None,
    session_api_key_hash: str | None = None,
) -> StoredRemoteSandbox:
    """Helper function to create StoredRemoteSandbox for testing."""
    if created_at is None:
        created_at = datetime.now(timezone.utc)

    return StoredRemoteSandbox(
        id=sandbox_id,
        created_by_user_id=user_id,
        sandbox_spec_id=spec_id,
        session_api_key_hash=session_api_key_hash,
        created_at=created_at,
    )


class TestRemoteSandboxService:
    """Test cases for RemoteSandboxService core functionality."""

    @pytest.mark.asyncio
    async def test_send_runtime_api_request_success(self, remote_sandbox_service):
        """Test successful API request to remote runtime."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = {'result': 'success'}
        remote_sandbox_service.httpx_client.request.return_value = mock_response

        # Execute
        response = await remote_sandbox_service._send_runtime_api_request(
            'GET', '/test-endpoint', json={'test': 'data'}
        )

        # Verify
        assert response == mock_response
        remote_sandbox_service.httpx_client.request.assert_called_once_with(
            'GET',
            'https://api.example.com/test-endpoint',
            headers={'X-API-Key': 'test-api-key'},
            json={'test': 'data'},
        )

    @pytest.mark.asyncio
    async def test_send_runtime_api_request_timeout(self, remote_sandbox_service):
        """Test API request timeout handling."""
        # Setup
        remote_sandbox_service.httpx_client.request.side_effect = (
            httpx.TimeoutException('Request timeout')
        )

        # Execute & Verify
        with pytest.raises(httpx.TimeoutException):
            await remote_sandbox_service._send_runtime_api_request('GET', '/test')

    @pytest.mark.asyncio
    async def test_send_runtime_api_request_http_error(self, remote_sandbox_service):
        """Test API request HTTP error handling."""
        # Setup
        remote_sandbox_service.httpx_client.request.side_effect = httpx.HTTPError(
            'HTTP error'
        )

        # Execute & Verify
        with pytest.raises(httpx.HTTPError):
            await remote_sandbox_service._send_runtime_api_request('GET', '/test')


class TestStatusMapping:
    """Test cases for status mapping functionality."""

    @pytest.mark.asyncio
    async def test_get_sandbox_status_from_runtime_with_status(
        self, remote_sandbox_service
    ):
        """Test status mapping using status field."""
        runtime_data = create_runtime_data(status='running')

        status = remote_sandbox_service._get_sandbox_status_from_runtime(runtime_data)

        assert status == SandboxStatus.RUNNING

    @pytest.mark.asyncio
    async def test_get_sandbox_status_from_runtime_no_runtime(
        self, remote_sandbox_service
    ):
        """Test status mapping with no runtime data."""
        status = remote_sandbox_service._get_sandbox_status_from_runtime(None)

        assert status == SandboxStatus.MISSING

    @pytest.mark.asyncio
    async def test_get_sandbox_status_from_runtime_unknown_status(
        self, remote_sandbox_service
    ):
        """Test status mapping with unknown status values."""
        runtime_data = create_runtime_data(status='unknown_status')

        status = remote_sandbox_service._get_sandbox_status_from_runtime(runtime_data)

        assert status == SandboxStatus.MISSING

    @pytest.mark.asyncio
    async def test_get_sandbox_status_from_runtime_empty_status(
        self, remote_sandbox_service
    ):
        """Test status mapping with empty status field."""
        runtime_data = create_runtime_data(status='')

        status = remote_sandbox_service._get_sandbox_status_from_runtime(runtime_data)

        assert status == SandboxStatus.MISSING

    @pytest.mark.asyncio
    async def test_status_mapping_coverage(self, remote_sandbox_service):
        """Test all status mappings are handled correctly."""
        test_cases = [
            ('running', SandboxStatus.RUNNING),
            ('paused', SandboxStatus.PAUSED),
            ('stopped', SandboxStatus.MISSING),
            ('starting', SandboxStatus.STARTING),
            ('error', SandboxStatus.ERROR),
        ]

        for status, expected_status in test_cases:
            runtime_data = create_runtime_data(status=status)
            result = remote_sandbox_service._get_sandbox_status_from_runtime(
                runtime_data
            )
            assert result == expected_status, f'Failed for status: {status}'

    @pytest.mark.asyncio
    async def test_status_mapping_case_insensitive(self, remote_sandbox_service):
        """Test that status mapping is case-insensitive."""
        test_cases = [
            ('RUNNING', SandboxStatus.RUNNING),
            ('Running', SandboxStatus.RUNNING),
            ('PAUSED', SandboxStatus.PAUSED),
            ('Starting', SandboxStatus.STARTING),
        ]

        for status, expected_status in test_cases:
            runtime_data = create_runtime_data(status=status)
            result = remote_sandbox_service._get_sandbox_status_from_runtime(
                runtime_data
            )
            assert result == expected_status, f'Failed for status: {status}'


class TestEnvironmentInitialization:
    """Test cases for environment variable initialization."""

    @pytest.mark.asyncio
    async def test_init_environment_with_web_url(self, remote_sandbox_service):
        """Test environment initialization with web_url set."""
        # Setup
        sandbox_spec = SandboxSpecInfo(
            id='test-image',
            command=['test'],
            initial_env={'EXISTING_VAR': 'existing_value'},
            working_dir='/workspace',
        )
        sandbox_id = 'test-sandbox-123'

        # Execute
        environment = await remote_sandbox_service._init_environment(
            sandbox_spec, sandbox_id
        )

        # Verify
        expected_webhook_url = 'https://web.example.com/api/v1/webhooks'
        assert environment['EXISTING_VAR'] == 'existing_value'
        assert environment[WEBHOOK_CALLBACK_VARIABLE] == expected_webhook_url
        assert environment[ALLOW_CORS_ORIGINS_VARIABLE] == 'https://web.example.com'
        # Verify worker port environment variables are set
        assert environment[WORKER_1] == '12000'
        assert environment[WORKER_2] == '12001'

    @pytest.mark.asyncio
    async def test_init_environment_without_web_url(self, remote_sandbox_service):
        """Test environment initialization without web_url."""
        # Setup
        remote_sandbox_service.web_url = None
        sandbox_spec = SandboxSpecInfo(
            id='test-image',
            command=['test'],
            initial_env={'EXISTING_VAR': 'existing_value'},
            working_dir='/workspace',
        )
        sandbox_id = 'test-sandbox-123'

        # Execute
        environment = await remote_sandbox_service._init_environment(
            sandbox_spec, sandbox_id
        )

        # Verify
        assert environment['EXISTING_VAR'] == 'existing_value'
        assert WEBHOOK_CALLBACK_VARIABLE not in environment
        assert ALLOW_CORS_ORIGINS_VARIABLE not in environment
        # Worker port environment variables should still be set regardless of web_url
        assert environment[WORKER_1] == '12000'
        assert environment[WORKER_2] == '12001'


class TestSandboxInfoConversion:
    """Test cases for converting stored sandbox and runtime data to SandboxInfo."""

    @pytest.mark.asyncio
    async def test_to_sandbox_info_with_running_runtime(self, remote_sandbox_service):
        """Test conversion to SandboxInfo with running runtime."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data(status='running')

        # Execute
        sandbox_info = remote_sandbox_service._to_sandbox_info(
            stored_sandbox, runtime_data
        )

        # Verify
        assert sandbox_info.id == 'test-sandbox-123'
        assert sandbox_info.created_by_user_id == 'test-user-123'
        assert sandbox_info.sandbox_spec_id == 'test-image:latest'
        assert sandbox_info.status == SandboxStatus.RUNNING
        assert sandbox_info.session_api_key == 'test-session-key'
        assert len(sandbox_info.exposed_urls) == 4

        # Check exposed URLs
        url_names = [url.name for url in sandbox_info.exposed_urls]
        assert AGENT_SERVER in url_names
        assert VSCODE in url_names
        assert WORKER_1 in url_names
        assert WORKER_2 in url_names

    @pytest.mark.asyncio
    async def test_to_sandbox_info_with_starting_runtime(self, remote_sandbox_service):
        """Test conversion to SandboxInfo with starting runtime."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data(status='starting')

        # Execute
        sandbox_info = remote_sandbox_service._to_sandbox_info(
            stored_sandbox, runtime_data
        )

        # Verify
        assert sandbox_info.status == SandboxStatus.STARTING
        assert sandbox_info.session_api_key == 'test-session-key'
        assert sandbox_info.exposed_urls is None

    @pytest.mark.asyncio
    async def test_to_sandbox_info_loads_runtime_when_none_provided(
        self, remote_sandbox_service
    ):
        """Test that runtime data is loaded when not provided."""
        # Setup
        stored_sandbox = create_stored_sandbox()

        # Execute
        sandbox_info = remote_sandbox_service._to_sandbox_info(stored_sandbox, None)

        # Verify
        assert sandbox_info.status == SandboxStatus.MISSING


class TestSandboxLifecycle:
    """Test cases for sandbox lifecycle operations."""

    @pytest.mark.asyncio
    async def test_start_sandbox_success(
        self, remote_sandbox_service, mock_sandbox_spec_service
    ):
        """Test successful sandbox start."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = create_runtime_data(status='running')
        remote_sandbox_service.httpx_client.request.return_value = mock_response
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])

        # Mock database operations
        remote_sandbox_service.db_session.add = MagicMock()
        remote_sandbox_service.db_session.commit = AsyncMock()

        # Execute
        with patch('base62.encodebytes', return_value='test-sandbox-123'):
            sandbox_info = await remote_sandbox_service.start_sandbox()

        # Verify
        assert sandbox_info.id == 'test-sandbox-123'
        assert sandbox_info.status == SandboxStatus.RUNNING
        remote_sandbox_service.pause_old_sandboxes.assert_called_once_with(
            9
        )  # max_num_sandboxes - 1
        remote_sandbox_service.db_session.add.assert_called_once()
        remote_sandbox_service.db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_sandbox_with_specific_spec(
        self, remote_sandbox_service, mock_sandbox_spec_service
    ):
        """Test starting sandbox with specific sandbox spec."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = create_runtime_data()
        remote_sandbox_service.httpx_client.request.return_value = mock_response
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])
        remote_sandbox_service.db_session.add = MagicMock()
        remote_sandbox_service.db_session.commit = AsyncMock()

        # Execute
        with patch('base62.encodebytes', return_value='test-sandbox-123'):
            await remote_sandbox_service.start_sandbox('custom-spec-id')

        # Verify
        mock_sandbox_spec_service.get_sandbox_spec.assert_called_once_with(
            'custom-spec-id'
        )

    @pytest.mark.asyncio
    async def test_start_sandbox_spec_not_found(
        self, remote_sandbox_service, mock_sandbox_spec_service
    ):
        """Test starting sandbox with non-existent spec."""
        # Setup
        mock_sandbox_spec_service.get_sandbox_spec.return_value = None
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])

        # Execute & Verify
        with pytest.raises(ValueError, match='Sandbox Spec not found'):
            await remote_sandbox_service.start_sandbox('non-existent-spec')

    @pytest.mark.asyncio
    async def test_start_sandbox_with_sandbox_id(
        self, remote_sandbox_service, mock_sandbox_spec_service
    ):
        """Test starting sandbox with a specified sandbox_id."""
        # Setup
        mock_response = MagicMock()
        mock_response.json.return_value = create_runtime_data(
            session_id='custom_sandbox_id'
        )
        remote_sandbox_service.httpx_client.request.return_value = mock_response
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])

        # Mock database operations
        remote_sandbox_service.db_session.add = MagicMock()
        remote_sandbox_service.db_session.commit = AsyncMock()

        # Execute with custom sandbox_id - should not need base62 encoding
        sandbox_info = await remote_sandbox_service.start_sandbox(
            sandbox_id='custom_sandbox_id'
        )

        # Verify the custom sandbox_id is used
        assert sandbox_info.id == 'custom_sandbox_id'
        # Verify the stored sandbox used the custom ID
        add_call_args = remote_sandbox_service.db_session.add.call_args[0][0]
        assert add_call_args.id == 'custom_sandbox_id'

    @pytest.mark.asyncio
    async def test_start_sandbox_http_error(self, remote_sandbox_service):
        """Test sandbox start with HTTP error."""
        # Setup
        remote_sandbox_service.httpx_client.request.side_effect = httpx.HTTPError(
            'API Error'
        )
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])
        remote_sandbox_service.db_session.add = MagicMock()
        remote_sandbox_service.db_session.commit = AsyncMock()

        # Execute & Verify
        with patch('base62.encodebytes', return_value='test-sandbox-123'):
            with pytest.raises(SandboxError, match='Failed to start sandbox'):
                await remote_sandbox_service.start_sandbox()

    @pytest.mark.asyncio
    async def test_start_sandbox_with_sysbox_runtime(self, remote_sandbox_service):
        """Test sandbox start with sysbox runtime class."""
        # Setup
        remote_sandbox_service.runtime_class = 'sysbox'
        mock_response = MagicMock()
        mock_response.json.return_value = create_runtime_data()
        remote_sandbox_service.httpx_client.request.return_value = mock_response
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])
        remote_sandbox_service.db_session.add = MagicMock()
        remote_sandbox_service.db_session.commit = AsyncMock()

        # Execute
        with patch('base62.encodebytes', return_value='test-sandbox-123'):
            await remote_sandbox_service.start_sandbox()

        # Verify runtime_class is included in request
        call_args = remote_sandbox_service.httpx_client.request.call_args
        request_data = call_args[1]['json']
        assert request_data['runtime_class'] == 'sysbox-runc'

    @pytest.mark.asyncio
    async def test_resume_sandbox_success(self, remote_sandbox_service):
        """Test successful sandbox resume."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data()

        remote_sandbox_service._get_stored_sandbox = AsyncMock(
            return_value=stored_sandbox
        )
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'session_api_key': 'new-session-key-123'}
        remote_sandbox_service.httpx_client.request.return_value = mock_response

        # Execute
        result = await remote_sandbox_service.resume_sandbox('test-sandbox-123')

        # Verify
        assert result is True
        remote_sandbox_service.pause_old_sandboxes.assert_called_once_with(9)
        remote_sandbox_service.httpx_client.request.assert_called_once_with(
            'POST',
            'https://api.example.com/resume',
            headers={'X-API-Key': 'test-api-key'},
            json={'runtime_id': 'runtime-456'},
        )

    @pytest.mark.asyncio
    async def test_resume_sandbox_not_found(self, remote_sandbox_service):
        """Test resuming non-existent sandbox."""
        # Setup
        remote_sandbox_service._get_stored_sandbox = AsyncMock(return_value=None)
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])

        # Execute
        result = await remote_sandbox_service.resume_sandbox('non-existent')

        # Verify
        assert result is False

    @pytest.mark.asyncio
    async def test_resume_sandbox_runtime_not_found(self, remote_sandbox_service):
        """Test resuming sandbox when runtime returns 404."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data()

        remote_sandbox_service._get_stored_sandbox = AsyncMock(
            return_value=stored_sandbox
        )
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])

        mock_response = MagicMock()
        mock_response.status_code = 404
        remote_sandbox_service.httpx_client.request.return_value = mock_response

        # Execute
        result = await remote_sandbox_service.resume_sandbox('test-sandbox-123')

        # Verify
        assert result is False

    @pytest.mark.asyncio
    async def test_pause_sandbox_success(self, remote_sandbox_service):
        """Test successful sandbox pause."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data()

        remote_sandbox_service._get_stored_sandbox = AsyncMock(
            return_value=stored_sandbox
        )
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)

        mock_response = MagicMock()
        mock_response.status_code = 200
        remote_sandbox_service.httpx_client.request.return_value = mock_response

        # Execute
        result = await remote_sandbox_service.pause_sandbox('test-sandbox-123')

        # Verify
        assert result is True
        remote_sandbox_service.httpx_client.request.assert_called_once_with(
            'POST',
            'https://api.example.com/pause',
            headers={'X-API-Key': 'test-api-key'},
            json={'runtime_id': 'runtime-456'},
        )

    @pytest.mark.asyncio
    async def test_delete_sandbox_success(self, remote_sandbox_service):
        """Test successful sandbox deletion."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data()

        remote_sandbox_service._get_stored_sandbox = AsyncMock(
            return_value=stored_sandbox
        )
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)
        remote_sandbox_service.db_session.delete = AsyncMock()
        remote_sandbox_service.db_session.commit = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        remote_sandbox_service.httpx_client.request.return_value = mock_response

        # Execute
        result = await remote_sandbox_service.delete_sandbox('test-sandbox-123')

        # Verify
        assert result is True
        remote_sandbox_service.db_session.delete.assert_called_once_with(stored_sandbox)
        remote_sandbox_service.db_session.commit.assert_not_called()
        remote_sandbox_service.httpx_client.request.assert_called_once_with(
            'POST',
            'https://api.example.com/stop',
            headers={'X-API-Key': 'test-api-key'},
            json={'runtime_id': 'runtime-456'},
        )

    @pytest.mark.asyncio
    async def test_delete_sandbox_runtime_not_found_ignored(
        self, remote_sandbox_service
    ):
        """Test sandbox deletion when runtime returns 404 (should be ignored)."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data()

        remote_sandbox_service._get_stored_sandbox = AsyncMock(
            return_value=stored_sandbox
        )
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)
        remote_sandbox_service.db_session.delete = AsyncMock()
        remote_sandbox_service.db_session.commit = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 404
        remote_sandbox_service.httpx_client.request.return_value = mock_response

        # Execute
        result = await remote_sandbox_service.delete_sandbox('test-sandbox-123')

        # Verify
        assert result is True  # 404 should be ignored for delete operations


class TestSandboxSearch:
    """Test cases for sandbox search and retrieval."""

    @pytest.mark.asyncio
    async def test_search_sandboxes_basic(self, remote_sandbox_service):
        """Test basic sandbox search functionality."""
        # Setup
        stored_sandboxes = [
            create_stored_sandbox('sb1'),
            create_stored_sandbox('sb2'),
        ]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = stored_sandboxes
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        remote_sandbox_service.db_session.execute = AsyncMock(return_value=mock_result)

        # Mock the batch endpoint response
        mock_batch_response = MagicMock()
        mock_batch_response.raise_for_status.return_value = None
        mock_batch_response.json.return_value = {
            'runtimes': [
                create_runtime_data('sb1'),
                create_runtime_data('sb2'),
            ]
        }
        remote_sandbox_service.httpx_client.request = AsyncMock(
            return_value=mock_batch_response
        )

        # Execute
        result = await remote_sandbox_service.search_sandboxes()

        # Verify
        assert len(result.items) == 2
        assert result.next_page_id is None
        assert result.items[0].id == 'sb1'
        assert result.items[1].id == 'sb2'

        # Verify that the batch endpoint was called
        remote_sandbox_service.httpx_client.request.assert_called_once_with(
            'GET',
            'https://api.example.com/sessions/batch',
            headers={'X-API-Key': 'test-api-key'},
            params=[('ids', 'sb1'), ('ids', 'sb2')],
        )

    @pytest.mark.asyncio
    async def test_search_sandboxes_with_pagination(self, remote_sandbox_service):
        """Test sandbox search with pagination."""
        # Setup - return limit + 1 items to trigger pagination
        stored_sandboxes = [
            create_stored_sandbox(f'sb{i}') for i in range(6)
        ]  # limit=5, so 6 items

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = stored_sandboxes
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        remote_sandbox_service.db_session.execute = AsyncMock(return_value=mock_result)

        # Mock the batch endpoint response
        mock_batch_response = MagicMock()
        mock_batch_response.raise_for_status.return_value = None
        mock_batch_response.json.return_value = {
            'runtimes': [create_runtime_data(f'sb{i}') for i in range(6)]
        }
        remote_sandbox_service.httpx_client.request = AsyncMock(
            return_value=mock_batch_response
        )

        # Execute
        result = await remote_sandbox_service.search_sandboxes(limit=5)

        # Verify
        assert len(result.items) == 5  # Should be limited to 5
        assert result.next_page_id == '5'  # Next page offset

    @pytest.mark.asyncio
    async def test_search_sandboxes_with_page_id(self, remote_sandbox_service):
        """Test sandbox search with page_id offset."""
        # Setup
        stored_sandboxes = [create_stored_sandbox('sb1')]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = stored_sandboxes
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        remote_sandbox_service.db_session.execute = AsyncMock(return_value=mock_result)

        # Mock the batch endpoint response
        mock_batch_response = MagicMock()
        mock_batch_response.raise_for_status.return_value = None
        mock_batch_response.json.return_value = {
            'runtimes': [create_runtime_data('sb1')]
        }
        remote_sandbox_service.httpx_client.request = AsyncMock(
            return_value=mock_batch_response
        )

        # Execute
        await remote_sandbox_service.search_sandboxes(page_id='10', limit=5)

        # Verify that offset was applied to the query
        # Note: We can't easily verify the exact SQL query, but we can verify the method was called
        remote_sandbox_service.db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_runtimes_batch_success(self, remote_sandbox_service):
        """Test successful batch runtime retrieval."""
        # Setup
        sandboxes = [
            create_stored_sandbox(sandbox_id='sb1'),
            create_stored_sandbox(sandbox_id='sb2'),
            create_stored_sandbox(sandbox_id='sb3'),
        ]
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            create_runtime_data('sb1'),
            create_runtime_data('sb2'),
            create_runtime_data('sb3'),
        ]
        remote_sandbox_service.httpx_client.request = AsyncMock(
            return_value=mock_response
        )

        # Execute
        result = await remote_sandbox_service._get_runtimes_batch(sandboxes)

        # Verify
        assert len(result) == 3
        assert 'sb1' in result
        assert 'sb2' in result
        assert 'sb3' in result
        assert result['sb1']['session_id'] == 'sb1'

        # Verify the correct API call was made
        remote_sandbox_service.httpx_client.request.assert_called_once_with(
            'GET',
            'https://api.example.com/sessions/batch',
            headers={'X-API-Key': 'test-api-key'},
            params=[('ids', 'sb1'), ('ids', 'sb2'), ('ids', 'sb3')],
        )

    @pytest.mark.asyncio
    async def test_get_runtimes_batch_empty_list(self, remote_sandbox_service):
        """Test batch runtime retrieval with empty sandbox list."""
        # Execute
        result = await remote_sandbox_service._get_runtimes_batch([])

        # Verify
        assert result == {}
        # Verify no API call was made
        remote_sandbox_service.httpx_client.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_runtimes_batch_partial_results(self, remote_sandbox_service):
        """Test batch runtime retrieval with partial results (some sandboxes not found)."""
        # Setup
        sandboxes = [
            create_stored_sandbox(sandbox_id='sb1'),
            create_stored_sandbox(sandbox_id='sb2'),
            create_stored_sandbox(sandbox_id='sb3'),
        ]
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            create_runtime_data('sb1'),
            create_runtime_data('sb3'),
            # sb2 is missing from the response
        ]
        remote_sandbox_service.httpx_client.request = AsyncMock(
            return_value=mock_response
        )

        # Execute
        result = await remote_sandbox_service._get_runtimes_batch(sandboxes)

        # Verify
        assert len(result) == 2
        assert 'sb1' in result
        assert 'sb2' not in result  # Missing from response
        assert 'sb3' in result

    @pytest.mark.asyncio
    async def test_get_sandbox_exists(self, remote_sandbox_service):
        """Test getting an existing sandbox."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        remote_sandbox_service._get_stored_sandbox = AsyncMock(
            return_value=stored_sandbox
        )
        remote_sandbox_service._get_runtime = AsyncMock(
            return_value=create_runtime_data()
        )
        remote_sandbox_service._to_sandbox_info = MagicMock(
            return_value=SandboxInfo(
                id='test-sandbox-123',
                created_by_user_id='test-user-123',
                sandbox_spec_id='test-image:latest',
                status=SandboxStatus.RUNNING,
                session_api_key='test-key',
                created_at=stored_sandbox.created_at,
            )
        )

        # Execute
        result = await remote_sandbox_service.get_sandbox('test-sandbox-123')

        # Verify
        assert result is not None
        assert result.id == 'test-sandbox-123'
        remote_sandbox_service._get_stored_sandbox.assert_called_once_with(
            'test-sandbox-123'
        )

    @pytest.mark.asyncio
    async def test_get_sandbox_not_exists(self, remote_sandbox_service):
        """Test getting a non-existent sandbox."""
        # Setup
        remote_sandbox_service._get_stored_sandbox = AsyncMock(return_value=None)

        # Execute
        result = await remote_sandbox_service.get_sandbox('non-existent')

        # Verify
        assert result is None


class TestUserSecurity:
    """Test cases for user-scoped operations and security."""

    @pytest.mark.asyncio
    async def test_secure_select_with_user_id(self, remote_sandbox_service):
        """Test that _secure_select filters by user ID."""
        # Setup
        remote_sandbox_service.user_context.get_user_id.return_value = 'test-user-123'

        # Execute
        await remote_sandbox_service._secure_select()

        # Verify
        # Note: We can't easily test the exact SQL query structure, but we can verify
        # that get_user_id was called, which means user filtering should be applied
        remote_sandbox_service.user_context.get_user_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_secure_select_without_user_id(self, remote_sandbox_service):
        """Test that _secure_select works when user ID is None."""
        # Setup
        remote_sandbox_service.user_context.get_user_id.return_value = None

        # Execute
        await remote_sandbox_service._secure_select()

        # Verify
        remote_sandbox_service.user_context.get_user_id.assert_called_once()


class TestErrorHandling:
    """Test cases for error handling scenarios."""

    @pytest.mark.asyncio
    async def test_resume_sandbox_http_error(self, remote_sandbox_service):
        """Test resume sandbox with HTTP error."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data()

        remote_sandbox_service._get_stored_sandbox = AsyncMock(
            return_value=stored_sandbox
        )
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)
        remote_sandbox_service.pause_old_sandboxes = AsyncMock(return_value=[])
        remote_sandbox_service.httpx_client.request.side_effect = httpx.HTTPError(
            'API Error'
        )

        # Execute
        result = await remote_sandbox_service.resume_sandbox('test-sandbox-123')

        # Verify
        assert result is False

    @pytest.mark.asyncio
    async def test_pause_sandbox_http_error(self, remote_sandbox_service):
        """Test pause sandbox with HTTP error."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data()

        remote_sandbox_service._get_stored_sandbox = AsyncMock(
            return_value=stored_sandbox
        )
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)
        remote_sandbox_service.httpx_client.request.side_effect = httpx.HTTPError(
            'API Error'
        )

        # Execute
        result = await remote_sandbox_service.pause_sandbox('test-sandbox-123')

        # Verify
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_sandbox_http_error(self, remote_sandbox_service):
        """Test delete sandbox with HTTP error."""
        # Setup
        stored_sandbox = create_stored_sandbox()
        runtime_data = create_runtime_data()

        remote_sandbox_service._get_stored_sandbox = AsyncMock(
            return_value=stored_sandbox
        )
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)
        remote_sandbox_service.db_session.delete = AsyncMock()
        remote_sandbox_service.db_session.commit = AsyncMock()
        remote_sandbox_service.httpx_client.request.side_effect = httpx.HTTPError(
            'API Error'
        )

        # Execute
        result = await remote_sandbox_service.delete_sandbox('test-sandbox-123')

        # Verify
        assert result is False


class TestGetSandboxBySessionApiKey:
    """Test cases for get_sandbox_by_session_api_key functionality."""

    @pytest.mark.asyncio
    async def test_get_sandbox_by_session_api_key_with_hash(
        self, remote_sandbox_service
    ):
        """Test finding sandbox by session API key using stored hash."""
        from openhands.app_server.sandbox.remote_sandbox_service import (
            _hash_session_api_key,
        )

        # Setup
        session_api_key = 'test-session-key'
        expected_hash = _hash_session_api_key(session_api_key)
        stored_sandbox = create_stored_sandbox(session_api_key_hash=expected_hash)
        runtime_data = create_runtime_data(session_api_key=session_api_key)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = stored_sandbox
        remote_sandbox_service.db_session.execute = AsyncMock(return_value=mock_result)
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)
        remote_sandbox_service.user_context.get_user_id.return_value = 'test-user-123'

        # Execute
        result = await remote_sandbox_service.get_sandbox_by_session_api_key(
            session_api_key
        )

        # Verify
        assert result is not None
        assert result.id == 'test-sandbox-123'
        assert result.session_api_key == session_api_key

    @pytest.mark.asyncio
    async def test_get_sandbox_by_session_api_key_not_found(
        self, remote_sandbox_service
    ):
        """Test finding sandbox when no matching hash exists and legacy fallback fails."""
        # Setup - no hash match
        mock_result_no_hash = MagicMock()
        mock_result_no_hash.scalar_one_or_none.return_value = None

        # Setup - legacy fallback: /list API fails, then no stored sandboxes
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception('API error')
        remote_sandbox_service.httpx_client.request = AsyncMock(
            return_value=mock_response
        )

        mock_result_legacy = MagicMock()
        mock_result_legacy.scalars.return_value.all.return_value = []

        remote_sandbox_service.db_session.execute = AsyncMock(
            side_effect=[mock_result_no_hash, mock_result_legacy]
        )
        remote_sandbox_service.user_context.get_user_id.return_value = 'test-user-123'

        # Execute
        result = await remote_sandbox_service.get_sandbox_by_session_api_key(
            'unknown-key'
        )

        # Verify
        assert result is None

    @pytest.mark.asyncio
    async def test_get_sandbox_by_session_api_key_legacy_via_list_api(
        self, remote_sandbox_service
    ):
        """Test legacy fallback finding sandbox via /list API and backfilling hash."""
        from openhands.app_server.sandbox.remote_sandbox_service import (
            _hash_session_api_key,
        )

        # Setup
        session_api_key = 'test-session-key'
        stored_sandbox = create_stored_sandbox(
            session_api_key_hash=None
        )  # Legacy sandbox
        runtime_data = create_runtime_data(session_api_key=session_api_key)

        # First call returns None (no hash match)
        mock_result_no_match = MagicMock()
        mock_result_no_match.scalar_one_or_none.return_value = None

        # Legacy fallback: /list API returns the runtime
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {'runtimes': [runtime_data]}
        remote_sandbox_service.httpx_client.request = AsyncMock(
            return_value=mock_response
        )

        # Query for sandbox by session_id returns the stored sandbox
        mock_result_sandbox = MagicMock()
        mock_result_sandbox.scalar_one_or_none.return_value = stored_sandbox

        remote_sandbox_service.db_session.execute = AsyncMock(
            side_effect=[mock_result_no_match, mock_result_sandbox]
        )
        remote_sandbox_service.user_context.get_user_id.return_value = 'test-user-123'

        # Execute
        result = await remote_sandbox_service.get_sandbox_by_session_api_key(
            session_api_key
        )

        # Verify
        assert result is not None
        assert result.id == 'test-sandbox-123'
        # Verify the hash was backfilled
        expected_hash = _hash_session_api_key(session_api_key)
        assert stored_sandbox.session_api_key_hash == expected_hash

    @pytest.mark.asyncio
    async def test_get_sandbox_by_session_api_key_legacy_via_runtime_check(
        self, remote_sandbox_service
    ):
        """Test legacy fallback checking each sandbox's runtime when /list API fails."""
        from openhands.app_server.sandbox.remote_sandbox_service import (
            _hash_session_api_key,
        )

        # Setup
        session_api_key = 'test-session-key'
        stored_sandbox = create_stored_sandbox(
            session_api_key_hash=None
        )  # Legacy sandbox
        runtime_data = create_runtime_data(session_api_key=session_api_key)

        # First call returns None (no hash match)
        mock_result_no_match = MagicMock()
        mock_result_no_match.scalar_one_or_none.return_value = None

        # Legacy fallback: /list API fails
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception('API error')
        remote_sandbox_service.httpx_client.request = AsyncMock(
            return_value=mock_response
        )

        # Get all stored sandboxes returns the legacy sandbox
        mock_result_all = MagicMock()
        mock_result_all.scalars.return_value.all.return_value = [stored_sandbox]

        remote_sandbox_service.db_session.execute = AsyncMock(
            side_effect=[mock_result_no_match, mock_result_all]
        )
        remote_sandbox_service._get_runtime = AsyncMock(return_value=runtime_data)
        remote_sandbox_service.user_context.get_user_id.return_value = 'test-user-123'

        # Execute
        result = await remote_sandbox_service.get_sandbox_by_session_api_key(
            session_api_key
        )

        # Verify
        assert result is not None
        assert result.id == 'test-sandbox-123'
        # Verify the hash was backfilled
        expected_hash = _hash_session_api_key(session_api_key)
        assert stored_sandbox.session_api_key_hash == expected_hash

    @pytest.mark.asyncio
    async def test_get_sandbox_by_session_api_key_runtime_error(
        self, remote_sandbox_service
    ):
        """Test handling runtime error when getting sandbox."""
        from openhands.app_server.sandbox.remote_sandbox_service import (
            _hash_session_api_key,
        )

        # Setup
        session_api_key = 'test-session-key'
        expected_hash = _hash_session_api_key(session_api_key)
        stored_sandbox = create_stored_sandbox(session_api_key_hash=expected_hash)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = stored_sandbox
        remote_sandbox_service.db_session.execute = AsyncMock(return_value=mock_result)
        remote_sandbox_service._get_runtime = AsyncMock(
            side_effect=Exception('Runtime error')
        )
        remote_sandbox_service.user_context.get_user_id.return_value = 'test-user-123'

        # Execute
        result = await remote_sandbox_service.get_sandbox_by_session_api_key(
            session_api_key
        )

        # Verify - should still return sandbox info, just with None runtime
        assert result is not None
        assert result.id == 'test-sandbox-123'
        assert result.status == SandboxStatus.MISSING  # No runtime means MISSING


class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_build_service_url_subdomain_mode(self):
        """Test _build_service_url function with subdomain-based routing."""
        from openhands.app_server.sandbox.remote_sandbox_service import (
            _build_service_url,
        )

        # Test HTTPS URL with path (subdomain mode)
        result = _build_service_url(
            'https://sandbox.example.com/path', 'vscode', 'runtime-123'
        )
        assert result == 'https://vscode-sandbox.example.com/path'

        # Test HTTP URL without path (subdomain mode)
        result = _build_service_url(
            'http://localhost:8000', 'work-1', 'different-runtime'
        )
        assert result == 'http://work-1-localhost:8000/'

        # Test URL with empty path (subdomain mode)
        result = _build_service_url('https://sandbox.example.com', 'work-2', 'some-id')
        assert result == 'https://work-2-sandbox.example.com/'

    def test_build_service_url_path_mode(self):
        """Test _build_service_url function with path-based routing."""
        from openhands.app_server.sandbox.remote_sandbox_service import (
            _build_service_url,
        )

        # Test path-based routing where URL path starts with /{runtime_id}
        result = _build_service_url(
            'https://sandbox.example.com/runtime-123', 'vscode', 'runtime-123'
        )
        assert result == 'https://sandbox.example.com/runtime-123/vscode'

        # Test path-based routing with work-1
        result = _build_service_url(
            'https://sandbox.example.com/my-runtime-id', 'work-1', 'my-runtime-id'
        )
        assert result == 'https://sandbox.example.com/my-runtime-id/work-1'

        # Test path-based routing with work-2
        result = _build_service_url(
            'http://localhost:8080/abc-xyz-123', 'work-2', 'abc-xyz-123'
        )
        assert result == 'http://localhost:8080/abc-xyz-123/work-2'

    def test_hash_session_api_key(self):
        """Test _hash_session_api_key function."""
        from openhands.app_server.sandbox.remote_sandbox_service import (
            _hash_session_api_key,
        )

        # Test that same input always produces same hash
        key = 'test-session-api-key'
        hash1 = _hash_session_api_key(key)
        hash2 = _hash_session_api_key(key)
        assert hash1 == hash2

        # Test that different inputs produce different hashes
        key2 = 'another-session-api-key'
        hash3 = _hash_session_api_key(key2)
        assert hash1 != hash3

        # Test that hash is a 64-character hex string (SHA-256)
        assert len(hash1) == 64
        assert all(c in '0123456789abcdef' for c in hash1)


class TestConstants:
    """Test cases for constants and mappings."""

    def test_status_mapping_completeness(self):
        """Test that STATUS_MAPPING covers expected statuses."""
        expected_statuses = ['running', 'paused', 'stopped', 'starting', 'error']
        for status in expected_statuses:
            assert status in STATUS_MAPPING, f'Missing status: {status}'

    def test_environment_variable_constants(self):
        """Test that environment variable constants are defined."""
        assert WEBHOOK_CALLBACK_VARIABLE == 'OH_WEBHOOKS_0_BASE_URL'
        assert ALLOW_CORS_ORIGINS_VARIABLE == 'OH_ALLOW_CORS_ORIGINS_0'


@pytest.fixture
def remote_sandbox_service_v2(
    mock_sandbox_spec_service, mock_user_context, mock_httpx_client, mock_db_session
):
    """RemoteSandboxService with a *distinct* Runtime API V2 endpoint configured."""
    return RemoteSandboxService(
        sandbox_spec_service=mock_sandbox_spec_service,
        api_url='https://api.example.com',
        api_key='test-api-key',
        web_url='https://web.example.com',
        resource_factor=1,
        runtime_class='gvisor',
        start_sandbox_timeout=120,
        max_num_sandboxes=10,
        user_context=mock_user_context,
        httpx_client=mock_httpx_client,
        db_session=mock_db_session,
        api_url_v2='https://v2.example.com',
        api_key_v2='v2-api-key',
    )


def create_stored_sandbox_v2(
    sandbox_template: str = 'python-gvisor', **kwargs: Any
) -> StoredRemoteSandbox:
    """Helper: a StoredRemoteSandbox marked as V2 (non-null sandbox_template)."""
    stored = create_stored_sandbox(**kwargs)
    stored.sandbox_template = sandbox_template
    return stored


class TestRuntimeApiV2:
    """Runtime API V2 opt-in: endpoint routing, V2 start, hash backfill,
    mixed-fleet batch, and version-aware /list."""

    # ── Endpoint resolution / version discriminator ──────────────────

    def test_endpoint_v1(self, remote_sandbox_service):
        assert remote_sandbox_service._endpoint(False) == (
            'https://api.example.com',
            'test-api-key',
        )

    def test_endpoint_v2_falls_back_to_v1_when_unset(self, remote_sandbox_service):
        # The default fixture leaves api_url_v2/api_key_v2 as None.
        assert remote_sandbox_service._endpoint(True) == (
            'https://api.example.com',
            'test-api-key',
        )

    def test_endpoint_v2_uses_distinct_url_and_key(self, remote_sandbox_service_v2):
        assert remote_sandbox_service_v2._endpoint(True) == (
            'https://v2.example.com',
            'v2-api-key',
        )
        assert remote_sandbox_service_v2._endpoint(False) == (
            'https://api.example.com',
            'test-api-key',
        )

    def test_is_v2_discriminator(self):
        assert RemoteSandboxService._is_v2(create_stored_sandbox_v2()) is True
        assert RemoteSandboxService._is_v2(create_stored_sandbox()) is False

    # ── V2 start ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_start_sandbox_v2_posts_template_to_v2_endpoint(
        self, remote_sandbox_service_v2
    ):
        """V2 start sends {sandbox_template, session_id} to the V2 endpoint with
        the V2 key, omits the V1 workload body, marks the row V2, and tolerates a
        null session_api_key."""
        svc = remote_sandbox_service_v2
        mock_response = MagicMock()
        # V2 /start returns session_api_key=None (key arrives via status poll).
        mock_response.json.return_value = create_runtime_data(
            session_id='sb-v2', status='starting', session_api_key=None
        )
        svc.httpx_client.request.return_value = mock_response
        svc.pause_old_sandboxes = AsyncMock(return_value=[])
        svc.db_session.add = MagicMock()

        sandbox_info = await svc.start_sandbox(
            sandbox_id='sb-v2',
            runtime_api_version='v2',
            sandbox_template='python-gvisor',
        )

        call_args = svc.httpx_client.request.call_args
        assert call_args[0] == ('POST', 'https://v2.example.com/start')
        assert call_args[1]['headers'] == {'X-API-Key': 'v2-api-key'}
        body = call_args[1]['json']
        assert body == {'sandbox_template': 'python-gvisor', 'session_id': 'sb-v2'}
        assert 'image' not in body and 'command' not in body

        stored = svc.db_session.add.call_args[0][0]
        assert stored.sandbox_template == 'python-gvisor'
        # Null key tolerated: no hash stored at start.
        assert stored.session_api_key_hash is None
        assert sandbox_info.id == 'sb-v2'

    @pytest.mark.asyncio
    async def test_start_sandbox_v2_without_template_falls_back_to_v1(
        self, remote_sandbox_service_v2
    ):
        """Defensive: V2 requested without a template posts the V1 body to the V1
        endpoint and leaves the row unmarked (so its lifecycle stays V1)."""
        svc = remote_sandbox_service_v2
        mock_response = MagicMock()
        mock_response.json.return_value = create_runtime_data(session_id='sb1')
        svc.httpx_client.request.return_value = mock_response
        svc.pause_old_sandboxes = AsyncMock(return_value=[])
        svc.db_session.add = MagicMock()

        await svc.start_sandbox(
            sandbox_id='sb1',
            runtime_api_version='v2',
            sandbox_template=None,
        )

        call_args = svc.httpx_client.request.call_args
        assert call_args[0] == ('POST', 'https://api.example.com/start')
        assert call_args[1]['headers'] == {'X-API-Key': 'test-api-key'}
        body = call_args[1]['json']
        assert 'image' in body
        assert 'sandbox_template' not in body
        stored = svc.db_session.add.call_args[0][0]
        assert stored.sandbox_template is None

    @pytest.mark.asyncio
    async def test_start_sandbox_v1_unchanged_by_default(
        self, remote_sandbox_service_v2
    ):
        """With no version specified, start is identical to V1: V1 body, V1
        endpoint, unmarked row — even when a V2 endpoint is configured."""
        svc = remote_sandbox_service_v2
        mock_response = MagicMock()
        mock_response.json.return_value = create_runtime_data(session_id='sb1')
        svc.httpx_client.request.return_value = mock_response
        svc.pause_old_sandboxes = AsyncMock(return_value=[])
        svc.db_session.add = MagicMock()

        await svc.start_sandbox(sandbox_id='sb1')

        call_args = svc.httpx_client.request.call_args
        assert call_args[0][1] == 'https://api.example.com/start'
        assert 'image' in call_args[1]['json']
        assert svc.db_session.add.call_args[0][0].sandbox_template is None

    # ── Key-from-poll lazy hash backfill ─────────────────────────────

    @pytest.mark.asyncio
    async def test_get_sandbox_v2_backfills_hash_and_routes_v2(
        self, remote_sandbox_service_v2
    ):
        """get_sandbox on a V2 row routes to the V2 endpoint and backfills the
        session_api_key hash once the key appears in the poll response."""
        from openhands.app_server.sandbox.remote_sandbox_service import (
            _hash_session_api_key,
        )

        svc = remote_sandbox_service_v2
        stored = create_stored_sandbox_v2(sandbox_id='sb-v2', session_api_key_hash=None)
        svc._get_stored_sandbox = AsyncMock(return_value=stored)
        mock_response = MagicMock()
        mock_response.json.return_value = create_runtime_data(
            session_id='sb-v2', status='running', session_api_key='the-key'
        )
        svc.httpx_client.request.return_value = mock_response

        await svc.get_sandbox('sb-v2')

        call_args = svc.httpx_client.request.call_args
        assert call_args[0][1] == 'https://v2.example.com/sessions/sb-v2'
        assert call_args[1]['headers'] == {'X-API-Key': 'v2-api-key'}
        assert stored.session_api_key_hash == _hash_session_api_key('the-key')

    @pytest.mark.asyncio
    async def test_get_sandbox_v1_does_not_overwrite_existing_hash(
        self, remote_sandbox_service
    ):
        """Backfill only fills a missing hash; an existing V1 hash is untouched."""
        svc = remote_sandbox_service
        stored = create_stored_sandbox(
            sandbox_id='sb1', session_api_key_hash='preexisting'
        )
        svc._get_stored_sandbox = AsyncMock(return_value=stored)
        mock_response = MagicMock()
        mock_response.json.return_value = create_runtime_data(
            session_id='sb1', status='running', session_api_key='new-key'
        )
        svc.httpx_client.request.return_value = mock_response

        await svc.get_sandbox('sb1')

        assert stored.session_api_key_hash == 'preexisting'

    # ── Mixed-fleet batch + version-aware /list ──────────────────────

    @pytest.mark.asyncio
    async def test_get_runtimes_batch_splits_by_version(
        self, remote_sandbox_service_v2
    ):
        """A mixed list of stored sandboxes is queried per-endpoint and merged."""
        svc = remote_sandbox_service_v2
        v1a = create_stored_sandbox(sandbox_id='v1a')
        v2a = create_stored_sandbox_v2(sandbox_id='v2a')

        def fake_request(method, url, headers=None, params=None):
            ids = [v for (k, v) in (params or []) if k == 'ids']
            resp = MagicMock()
            resp.json.return_value = [
                create_runtime_data(session_id=i, status='running') for i in ids
            ]
            return resp

        svc.httpx_client.request = AsyncMock(side_effect=fake_request)

        result = await svc._get_runtimes_batch([v1a, v2a])

        assert set(result.keys()) == {'v1a', 'v2a'}
        for call in svc.httpx_client.request.call_args_list:
            url = call.args[1]
            ids = [v for (k, v) in call.kwargs['params'] if k == 'ids']
            if 'v2.example.com' in url:
                assert ids == ['v2a']
                assert call.kwargs['headers'] == {'X-API-Key': 'v2-api-key'}
            else:
                assert url == 'https://api.example.com/sessions/batch'
                assert ids == ['v1a']
                assert call.kwargs['headers'] == {'X-API-Key': 'test-api-key'}

    @pytest.mark.asyncio
    async def test_list_running_session_ids_routes_by_version(
        self, remote_sandbox_service_v2
    ):
        svc = remote_sandbox_service_v2
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'runtimes': [
                {'session_id': 'a'},
                {'session_id': 'b'},
                {'session_id': None},  # dropped
            ]
        }
        svc.httpx_client.request.return_value = mock_response

        ids = await svc._list_running_session_ids(is_v2=True)

        assert ids == {'a', 'b'}
        call_args = svc.httpx_client.request.call_args
        assert call_args[0][1] == 'https://v2.example.com/list'
        assert call_args[1]['headers'] == {'X-API-Key': 'v2-api-key'}

    @pytest.mark.asyncio
    async def test_pause_old_sandboxes_lists_both_endpoints_when_v2_configured(
        self, remote_sandbox_service_v2
    ):
        """With a distinct V2 URL, the cleanup sweep lists both fleets so a V2
        sandbox isn't invisible to a V1-only /list."""
        svc = remote_sandbox_service_v2
        seen: list[bool] = []

        async def fake_list(is_v2: bool):
            seen.append(is_v2)
            return set()

        svc._list_running_session_ids = AsyncMock(side_effect=fake_list)
        svc._secure_select = AsyncMock(return_value=MagicMock())
        svc.db_session.execute = AsyncMock(return_value=[])

        await svc.pause_old_sandboxes(5)

        assert seen == [False, True]

    @pytest.mark.asyncio
    async def test_pause_old_sandboxes_single_list_when_v2_not_configured(
        self, remote_sandbox_service
    ):
        """V1-only deployments issue exactly one /list — behaviour unchanged."""
        svc = remote_sandbox_service  # api_url_v2 is None -> V2 falls back to V1
        seen: list[bool] = []

        async def fake_list(is_v2: bool):
            seen.append(is_v2)
            return set()

        svc._list_running_session_ids = AsyncMock(side_effect=fake_list)
        svc._secure_select = AsyncMock(return_value=MagicMock())
        svc.db_session.execute = AsyncMock(return_value=[])

        await svc.pause_old_sandboxes(5)

        assert seen == [False]

    # ── Lifecycle routing for an existing V2 sandbox ─────────────────

    @pytest.mark.asyncio
    async def test_resume_sandbox_v2_routes_to_v2_endpoint(
        self, remote_sandbox_service_v2
    ):
        svc = remote_sandbox_service_v2
        stored = create_stored_sandbox_v2(sandbox_id='sb-v2')
        svc._get_stored_sandbox = AsyncMock(return_value=stored)
        svc._get_runtime = AsyncMock(
            return_value=create_runtime_data(session_id='sb-v2')
        )
        svc.pause_old_sandboxes = AsyncMock(return_value=[])
        resume_response = MagicMock()
        resume_response.status_code = 200
        resume_response.json.return_value = {'session_api_key': 'stable-key'}
        svc.httpx_client.request.return_value = resume_response

        result = await svc.resume_sandbox('sb-v2')

        assert result is True
        # _get_runtime told to use V2; /resume sent to the V2 endpoint.
        svc._get_runtime.assert_awaited_once_with('sb-v2', is_v2=True)
        call_args = svc.httpx_client.request.call_args
        assert call_args[0][1] == 'https://v2.example.com/resume'
        assert call_args[1]['headers'] == {'X-API-Key': 'v2-api-key'}
