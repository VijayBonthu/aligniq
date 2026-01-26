import requests
from utils.logger import logger
from fastapi import HTTPException, status, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer



async def get_jira_user_info(jira_access_token:str):
        """Get Jira user information using access token"""
        try:
            headers = {
                "Authorization": f"Bearer {jira_access_token}",
                "Accept": "application/json"
            }
            logger.info(f"creating header for Jira: {headers}")
            
            # Get user info from Atlassian
            response = requests.get(
                "https://api.atlassian.com/me",
                headers=headers
            )
            
            logger.info(f"User info response status: {response.status_code}")
            logger.info(f"User info response: {response.text}")
            
            if response.status_code != 200:
                raise Exception(f"Failed to get user info: {response.text}")
                
            user_info = response.json()
            return {
                "account_id": user_info.get("account_id"),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "picture": user_info.get("picture"),
                "account_type": user_info.get("account_type")
            }
            
        except Exception as e:
            logger.error(f"Failed to get user info: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get user info: {str(e)}"
            )