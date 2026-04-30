import asyncio
import hashlib
import hmac
import os
from typing import cast

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from integrations.github.data_collector import GitHubDataCollector
from integrations.github.github_manager import GithubManager
from integrations.models import Message, SourceType
from pydantic import BaseModel
from server.auth.constants import (
    AUTOMATION_EVENT_FORWARDING_ENABLED,
    GITHUB_APP_WEBHOOK_SECRET,
)
from server.auth.saas_user_auth import SaasUserAuth
from server.auth.token_manager import TokenManager
from server.services.automation_event_service import AutomationEventService

from openhands.app_server.integrations.provider import ProviderType
from openhands.app_server.user_auth.user_auth import get_user_auth
from openhands.core.logger import openhands_logger as logger

# Environment variable to disable GitHub webhooks
GITHUB_WEBHOOKS_ENABLED = os.environ.get('GITHUB_WEBHOOKS_ENABLED', '1') in (
    '1',
    'true',
)
github_integration_router = APIRouter(prefix='/integration')
token_manager = TokenManager()
data_collector = GitHubDataCollector()
github_manager = GithubManager(token_manager, data_collector)
automation_event_service = AutomationEventService(token_manager)


def verify_github_signature(payload: bytes, signature: str):
    if not signature:
        raise HTTPException(
            status_code=403, detail='x-hub-signature-256 header is missing!'
        )

    expected_signature = (
        'sha256='
        + hmac.new(
            GITHUB_APP_WEBHOOK_SECRET.encode('utf-8'),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=403, detail="Request signatures didn't match!")


@github_integration_router.post('/github/events')
async def github_events(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
):
    # Check if GitHub webhooks are enabled
    if not GITHUB_WEBHOOKS_ENABLED:
        logger.info('GitHub webhooks disabled by GITHUB_WEBHOOKS_ENABLED env variable')
        return JSONResponse(
            status_code=200,
            content={'message': 'GitHub webhooks are currently disabled.'},
        )

    try:
        # Add timeout to prevent hanging on slow/stalled clients
        payload = await asyncio.wait_for(request.body(), timeout=15.0)
        verify_github_signature(payload, x_hub_signature_256)

        payload_data = await request.json()
        installation_id = payload_data.get('installation', {}).get('id')

        if not installation_id:
            return JSONResponse(
                status_code=400,
                content={'error': 'Installation ID is missing in the payload.'},
            )

        # Forward to automation service (fire-and-forget background task)
        if AUTOMATION_EVENT_FORWARDING_ENABLED:
            background_tasks.add_task(
                automation_event_service.forward_event,
                provider=ProviderType.GITHUB,
                payload=payload_data,
                installation_id=installation_id,
            )

        # Existing resolver bot processing
        message_payload = {'payload': payload_data, 'installation': installation_id}
        message = Message(source=SourceType.GITHUB, message=message_payload)
        await github_manager.receive_message(message)

        return JSONResponse(
            status_code=200,
            content={'message': 'GitHub events endpoint reached successfully.'},
        )
    except asyncio.TimeoutError:
        logger.warning('GitHub webhook request timed out waiting for request body')
        return JSONResponse(
            status_code=408,
            content={'error': 'Request timeout - client took too long to send data.'},
        )
    except Exception as e:
        logger.exception(f'Error processing GitHub event: {e}')
        return JSONResponse(status_code=400, content={'error': 'Invalid payload.'})


class GitHubTokenResponse(BaseModel):
    """Response model for the GitHub token endpoint."""

    access_token: str


@github_integration_router.get('/github/token')
async def get_github_token(request: Request) -> GitHubTokenResponse:
    """Get the GitHub access token for the authenticated user.

    This endpoint retrieves the user's GitHub OAuth token, refreshing it
    if necessary. The token can be used for GitHub API operations.

    Returns:
        GitHubTokenResponse containing the access token.

    Raises:
        HTTPException 401: If the user is not authenticated.
        HTTPException 404: If no GitHub token is available for the user.
    """
    user_auth = cast(SaasUserAuth, await get_user_auth(request))

    provider_tokens = await user_auth.get_provider_tokens()
    if not provider_tokens:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No provider tokens available for this user.',
        )

    github_token = provider_tokens.get(ProviderType.GITHUB)
    if not github_token or not github_token.token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No GitHub token available for this user.',
        )

    return GitHubTokenResponse(access_token=github_token.token.get_secret_value())
