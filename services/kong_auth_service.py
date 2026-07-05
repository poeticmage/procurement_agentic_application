import logging

import httpx

logger = logging.getLogger(__name__)


class KongAuthError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def verify_kong_token(token: str, *, kong_admin_url: str) -> None:
    url = f"{kong_admin_url.rstrip('/')}/oauth2_tokens/{token}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
    except httpx.RequestError as exc:
        logger.error("kong_connection_error error=%s", exc)
        raise KongAuthError(500, f"Failed to connect to Kong: {exc}") from exc

    if response.status_code != 200:
        logger.warning(
            "kong_token_invalid status=%s body=%s",
            response.status_code,
            response.text[:200],
        )
        raise KongAuthError(403, "Invalid or expired token")

    try:
        token_data = response.json()
        user_id = token_data["authenticated_userid"]
    except (KeyError, ValueError, TypeError) as exc:
        logger.error("kong_token_malformed error=%s", exc)
        raise KongAuthError(500, f"Invalid token structure from Kong: {exc}") from exc

    logger.info("kong_token_verified user_id=%s", user_id)
    return user_id