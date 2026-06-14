"""How the connector authenticates **to the agentic-fs API** (not to the source).

A signer returns the extra headers a request needs. Source-side auth (reaching
S3 / Google Drive / SharePoint) lives inside each connector, not here. Two
signers ship today:

- ``NoAuth`` — local dev or an unauthenticated endpoint.
- ``SigV4Signer`` — the default AWS deployment, whose Function URL uses
  ``AWS_IAM`` auth. Needs the ``[aws]`` extra. Bearer-token (OAuth) auth arrives
  with the resource server.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RequestSigner(Protocol):
    def headers_for(self, *, method: str, url: str, body: bytes) -> dict[str, str]:
        """Headers to add so the API accepts the request (may be empty)."""
        ...


class NoAuth:
    def headers_for(self, *, method: str, url: str, body: bytes) -> dict[str, str]:
        return {}


class SigV4Signer:
    """Signs requests with AWS SigV4 for an ``AWS_IAM`` Lambda Function URL.

    Credentials come from the standard AWS chain (env, profile, role) unless
    passed explicitly. The signer is built once and reused across requests.
    """

    def __init__(self, *, region: str, service: str = "lambda", credentials: Any = None) -> None:
        try:
            from botocore.session import Session
        except ModuleNotFoundError as err:  # pragma: no cover - import guard
            raise RuntimeError(
                "SigV4 signing needs the optional extra: pip install 'afs-connector-sdk[aws]'"
            ) from err
        self._region = region
        self._service = service
        if credentials is None:
            credentials = Session().get_credentials()
        if credentials is None:
            raise RuntimeError(
                "no AWS credentials found — configure the standard AWS credential chain "
                "(env vars, a shared profile, or an instance/role)"
            )
        self._credentials = credentials

    def headers_for(self, *, method: str, url: str, body: bytes) -> dict[str, str]:
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest

        request = AWSRequest(method=method, url=url, data=body or b"")
        SigV4Auth(self._credentials, self._service, self._region).add_auth(request)
        return dict(request.headers)
