"""Google OAuth flow and credential handling.

Tokens never reach the browser: they are stored in the local database and the
session cookie only carries the user's id.
"""

import logging

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

import config
import db

logger = logging.getLogger(__name__)

USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


def build_flow(redirect_uri):
    """Build the OAuth flow.

    Both /login and /callback use it: if the client config or the scopes drift
    apart between the two legs, Google rejects the code exchange.
    """
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": config.OAUTH_CLIENT_ID,
                "client_secret": config.OAUTH_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=config.SCOPES,
    )

    flow.redirect_uri = redirect_uri
    return flow


def fetch_email(credentials):
    """Ask Google for the email of the account that just granted access.

    Returns the lowercased email, or None if it could not be resolved.
    """
    try:
        response = requests.get(
            USERINFO_URL,
            headers={"Authorization": "Bearer " + credentials.token},
            timeout=10,
        )

        if response.status_code != 200:
            logger.warning("userinfo returned %s", response.status_code)
            return None

        email = response.json().get("email")
        return email.strip().lower() if email else None

    except Exception as e:
        logger.warning("Could not resolve the user's email: %s", e)
        return None


def credentials_for(user):
    """Rebuild the user's Google credentials from their database row.

    If the access token expired, it is refreshed and the new one is saved, so
    the refresh does not repeat on every request.

    Returns None when the user has no usable credentials, which is the signal
    to ask them to log in again.
    """
    if not user or not user["access_token"]:
        return None

    credentials = Credentials(
        token=user["access_token"],
        refresh_token=user["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.OAUTH_CLIENT_ID,
        client_secret=config.OAUTH_CLIENT_SECRET,
        scopes=config.SCOPES,
    )

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            db.save_access_token(user["id"], credentials.token)
        except Exception as e:
            logger.warning("Could not refresh the token for %s: %s", user["email"], e)
            return None

    return credentials
