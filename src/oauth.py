from google_auth_oauthlib.flow import Flow
from config import settings
import requests
from fastapi import HTTPException, status
from oauthlib.oauth2 import WebApplicationClient
from urllib.parse import urlparse, parse_qs
import logging

logger = logging.getLogger(__name__)
#remove this once you get HTTPS working 11 and 12 lines are testing only
import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

flow = Flow.from_client_secrets_file(
    client_secrets_file="../client_secret_g.json",
    redirect_uri=settings.REDIRECT_URL,
    scopes=["https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "openid"]
)

def auth_callback(url:str=None):
    if not url:
        return "callback failed no link provided"
    try:
        authorization_response = str(url)
        logger.info(f"Authorization response: {authorization_response}")
        flow.fetch_token(authorization_response=authorization_response) 
        credentials = flow.credentials
        logger.info(f"Credentials: {credentials}")
        user_info_response = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"}
        )
        user_info = user_info_response.json()
        logger.info(f"User info: {user_info}")
        # Process and store user information in PostgreSQL
        return {"message": "Authentication successful", "user": user_info, "provider":"Google"}
    except Exception as e:
        return {"message": "bad request", "error": e}
        

class JiraOAuth:
    def __init__(self):
        self.client_id = settings.JIRA_CLIENT_ID
        self.client_secret = settings.JIRA_CLIENT_SECRET
        self.redirect_uri = settings.JIRA_REDIRECT_URI
        logger.info(f"JiraOAuth initialized with redirect_uri: {self.redirect_uri}")
        self.oauth2_client = WebApplicationClient(self.client_id)

    async def get_authorization_url(self):
        """Generate authorization URL for Jira OAuth"""
        try:
            result = self.oauth2_client.prepare_authorization_request(
                "https://auth.atlassian.com/authorize",
                redirect_url=self.redirect_uri,
                scope=[
                    "read:jira-user",
                    "read:jira-work",
                    "write:jira-work",
                    "offline_access",
                    "read:me",
                    "read:account"
                ],
                audience="api.atlassian.com",
                prompt="consent"
            )
            
            auth_url = result[0]
            parsed_url = urlparse(auth_url)
            query_params = parse_qs(parsed_url.query)
            state = query_params.get('state', [None])[0]
            
            logger.info(f"Generated auth URL: {auth_url}")
            logger.info(f"Generated state: {state}")
            
            return auth_url, state
        except Exception as e:
            logger.error(f"Error generating authorization URL: {str(e)}")
            raise

    async def get_access_token(self, code: str):
        """Exchange authorization code for access token"""
        try:
            token_url = "https://auth.atlassian.com/oauth/token"
            
            # Prepare token request with proper authorization code format
            body = {
                'grant_type': 'authorization_code',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': code,
                'redirect_uri': self.redirect_uri
            }
            
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            logger.info(f"Making token request to: {token_url}")
            logger.info(f"With headers: {headers}")
            logger.info(f"With body: {body}")
            
            response = requests.post(
                token_url,
                json=body,  # Use json parameter instead of data
                headers=headers,
                verify=True  # Ensure SSL verification is enabled
            )
            
            logger.info(f"Token response status: {response.status_code}")
            logger.info(f"Token response: {response.text}")
            
            if response.status_code != 200:
                error_detail = response.json() if response.text else "No error details provided"
                raise Exception(f"Token request failed: {error_detail}")
                
            return response.json()
            
        except Exception as e:
            logger.error(f"Failed to get access token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get access token: {str(e)}"
            )