from fastapi import FastAPI, Depends, Request
import uvicorn
from dotenv import load_dotenv
import models
from models import engine
from fastapi.middleware.cors import CORSMiddleware
from routers import authentication, services, third_party_integrations
from utils.logger import setup_logger
from utils.rate_limit import lifespan
from utils.middleware import CSRFMiddleware, RateLimitMiddleware

# Setup logging once at application startup
logger = setup_logger()

load_dotenv()

models.Base.metadata.create_all(bind=engine)

app = FastAPI(lifespan=lifespan)
# app = FastAPI()

origins = [ 
    
    # Add any other domains that need to access your API
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

#order matters since there will be taken in sequence.
# app.add_middleware(RateLimitMiddleware)
# app.add_middleware(CSRFMiddleware)      

app.include_router(authentication.router, prefix="/api/v1", tags=["authentication"])
app.include_router(services.router, prefix="/api/v1", tags=["services"])
app.include_router(third_party_integrations.router, prefix="/api/v1", tags=["third party integrations"])

@app.get("/")
async def home():
    return "Welcome to Oauth testing login page"  
    
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, log_level='info', reload=True, reload_excludes=["*.log"])