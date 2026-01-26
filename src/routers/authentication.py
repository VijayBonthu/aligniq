from oauth import flow, auth_callback, JiraOAuth
from fastapi import Depends, HTTPException, Request, APIRouter, status, Header
from sqlalchemy.orm import Session
from models import get_db
from database_scripts import create_user,UserCreationError, get_user_details
from utils.token_generation import create_token, verify_password, TokenDecoder, validate_app_user, validate_token_incoming_requests, token_validator
from p_model_type import Registration_login_password, login_details
import logging
from jira_logic.jira_components import get_jira_user_info
from typing import Dict
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


logger = logging.getLogger(__name__)

router = APIRouter()

security = HTTPBearer()

auth_states = {}
@router.get("/auth/login")
async def login():
    result= flow.authorization_url(prompt="consent")

    auth_url = result[0] if isinstance(result, tuple) else result
    state = result[1] if isinstance(result, tuple) else None

    if state:
        auth_states[state] = True
    print(auth_url)
    return RedirectResponse(url=auth_url)

@router.get("/auth/callback", status_code=status.HTTP_200_OK)
async def callback(request: Request, db:Session=Depends(get_db)):
    # Extract the state from query parameters
    state = request.query_params.get("state")
    logger.info(f"State: {state}")
    if not state or state not in auth_states:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Link already expired, Try to login in again")
    try: 
        #Uses Google authentication to login
        logger.info(f"Request URL: {request.url}")
        response =auth_callback(url=request.url)
        logger.info(f"Response: {response}")
        if response.get("message") == "bad request":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Issue with your login, Please try again")
        user_data = response["user"]
    except UserCreationError as e:
        #add logging here to save it
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Something went wrong, it is not you, Please try after sometime")
    try:
        #create a record in DB if its the first time or get the details for jwt payload
        user = await create_user(user_data=user_data,provider=response['provider'], db=db)
        auth_states.pop(state,None)
        #add logging here to save it
    except UserCreationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Something went wrong, it is not you, Please try after sometime") 
    
    payload= {
        "id": user.user_id,
        "oauth_id": user.oauth_id,
        "verified_email":user.verified_email,
        "picture": user.picture,
        "provider": user.provider,
        "email":user.email_address
    }
     # creates JWT token
    token = create_token(user_data=payload)
    print(token)
    
    # Return HTML instead of JSON
    html_content = f"""
    <html>
    <head><title>Authentication Complete</title></head>
    <body>
        <h2>Authentication Successful!</h2>
        <p>You can close this window and return to the application.</p>
        
        <script>
            // Send token back to opener window
            if (window.opener) {{
                window.opener.postMessage(
                    {{ 
                        type: 'google_auth_success', 
                        access_token: '{token}'
                    }},
                    '*'  // In production, you should limit this to your app's origin
                );
                
                // Close this window after a delay
                setTimeout(() => window.close(), 3000);
            }}
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@router.post("/registration", status_code=status.HTTP_201_CREATED)
async def create_account(user_details:Registration_login_password, db:Session=Depends(get_db)):
    if not user_details:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Required details are not provided")
    try:
        user_details = user_details.__dict__
        user_details.update(
            {
                "id": None,
                "verified_email":False,
                "picture":None,
                "provider":"Local",
                "name":user_details["given_name"] + " " +user_details["family_name"]
            }
        )
        user = await create_user(user_data=user_details, provider="Local",db=db)
    except UserCreationError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Something went wrong, it is not you, Please try after sometime{e}")
    

    
    payload= {
        "id": user.user_id,
        "verified_email":user.verified_email,
        "picture": user.picture,
        "provider": user.provider,
        "email":user.email_address
    }

    token = create_token(user_data=payload)
    print(token)
    
    return {"access_token": token, "token_type": "bearer"} 

@router.post("/login", status_code=status.HTTP_200_OK)
def log_into_account(login_details:login_details, db:Session=Depends(get_db)):
    if not login_details:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please provide the details to login")
    try:
        user_details = get_user_details(email_address=login_details.email_address, db=db)
    except UserCreationError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record doesn't exists, please register to Login")

    checked_password = verify_password(password=login_details.password,hashed_password=user_details[6])
    if checked_password:
        payload= {
            "id": user_details[1],
            "verified_email":user_details[4],
            "provider": user_details[5],
            "email":user_details[0],
        }
        token = create_token(user_data=payload)
        print(token)
        return {"access_token": token, "token_type": "bearer"}
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
@router.get("/auth/jira/login")
async def jira_login(request: Request, current_user: dict = Depends(token_validator)):
    """Initiates Jira OAuth flow"""
    # Validate the token that was passed in the query param
    # if current_user:
    #     try:
    #         # Decode and validate the token
    #         validate_token_incoming_requests(token=token)
    #         # Verify this is a valid user token
    #         # ... your validation logic here ...
    #     except Exception as e:
    #         logger.error(f"Token validation error: {str(e)}")
    #         raise HTTPException(
    #             status_code=status.HTTP_401_UNAUTHORIZED,
    #             detail="Invalid or expired token"
    #         )
    # else:
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED,
    #         detail="Authentication token required"
    #     )
    # logger.info(f"Jira login endpoint called")
    # logger.info(f"Current user: {current_user}")
    # logger.info(f"Current user type: {request}")
    try:
        auth_url, state = await JiraOAuth().get_authorization_url()
        auth_states[state] = True
        logger.info(f"Auth states updated: {auth_states}")
        logger.info(f"authorization_url: {auth_url}")
        return {"url": auth_url}
    except Exception as e:
        logger.error(f"Error in jira_login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/auth/jira/callback")
async def jira_callback(
    request: Request, 
    db: Session = Depends(get_db)
):
    """Handle Jira OAuth callback"""
    
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    error = request.query_params.get("error")
    
    if error:
        logger.error(f"Authorization error: {error}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authorization failed: {error}"
        )
    
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state parameter"
        )

    if state not in auth_states:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid state"
        )
    
    auth_states.pop(state, None)
    
    try:
        # Get access token
        jira = JiraOAuth()
        token_response = await jira.get_access_token(code)
        logger.info(f"Token response: {token_response}")
        
        access_token = token_response["access_token"]
        refresh_token = token_response.get("refresh_token")

        # Get Jira user info
        user_info = await get_jira_user_info(access_token)
        logger.info(f"Jira user info: {user_info}")
        
        # Create payload without app_user_id for now
        payload = {
            "jira_access_token": access_token,
            "jira_refresh_token": refresh_token,
            "provider": "Jira",
            "jira_account_id": user_info.get("account_id"),
            "jira_email": user_info.get("email"),
            "jira_account_id": user_info.get("account_id"),
            "scope": token_response.get("scope", ""),
            "token_type": token_response.get("token_type", "Bearer")
        }
        
        jira_token = create_token(user_data=payload)

        if jira_token:
        
            html_content = f"""
        <html>
        <head><title>Authentication Complete</title></head>
        <body>
            <h2>Authentication Successful!</h2>
            <p>You can close this window and return to the application.</p>
            
            <script>
                // Send token back to opener window
                if (window.opener) {{
                    window.opener.postMessage(
                        {{ 
                            type: 'jira_auth_success', 
                            access_token: '{jira_token}'
                        }},
                        '*'  // In production, you should limit this to your app's origin
                    );
                    
                    // Close this window after a delay
                    setTimeout(() => window.close(), 3000);
                }}
            </script>
        </body>
        </html>
        """
        
            return HTMLResponse(content=html_content)
    except Exception as e:
            logger.error(f"Callback error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(e))
        

@router.get("/auth/jira/test")
async def test_jira_auth():
    """Test endpoint to verify Jira auth flow"""
    logger.info("Testing Jira auth flow")
    try:
        jira = JiraOAuth()
        auth_url, state = await jira.get_authorization_url()
        auth_states[state] = True
        
        logger.info(f"Test auth URL generated: {auth_url}")
        logger.info(f"Test state generated: {state}")
        logger.info(f"Current auth_states: {auth_states}")
        
        return {
            "authorization_url": auth_url,
            "state": state,
            "redirect_uri": jira.redirect_uri,
            "scopes": ["read:jira-user", "read:jira-work", "write:jira-work", "offline_access"]
        }
    except Exception as e:
        logger.error(f"Test endpoint error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
@router.get("/decode_token/{token}")
async def decode_token(token:str):
    token_decoder = TokenDecoder()
    return await token_decoder.decode_oauth_token(token=token)

@router.post("/validate_token")
async def validate_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    logger.info(f"inside validate_token: {credentials.credentials}")
    return await validate_app_user(credentials)


