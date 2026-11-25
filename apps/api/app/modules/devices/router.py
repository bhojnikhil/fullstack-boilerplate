from fastapi import APIRouter, Response, status

from app.core import API_PREFIX
from app.core.db import RequestSession
from app.core.errors import ErrorEnvelope
from app.modules.auth.dependencies import CurrentUser
from app.modules.devices.schemas import DeviceRegister, DeviceResponse, DeviceUnregister
from app.modules.devices.service import register_device, unregister_device

router = APIRouter(
    prefix=f"{API_PREFIX}/devices",
    tags=["devices"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403)},
)


@router.post("")
async def register(data: DeviceRegister, user: CurrentUser, db: RequestSession) -> DeviceResponse:
    """Register (or refresh) this installation's Expo push token for the signed-in user."""
    device = await register_device(
        db, user.id, data.expo_push_token, data.platform, data.app_version
    )
    return DeviceResponse.model_validate(device)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unregister(data: DeviceUnregister, user: CurrentUser, db: RequestSession) -> Response:
    """Stop pushes to this token (call on sign-out). Unknown tokens are not an error."""
    await unregister_device(db, user.id, data.expo_push_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
