from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.routers import referral, hospitals

# Initialize the FastAPI application gateway
app = FastAPI(
    title="IRDSS Interoperability Layer API",
    description="API Gateway for the Mindanao-wide Intelligent Referral Decision Support System.",
    version="1.0.0"
)
origins = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:80",
    "http://127.0.0.1:80",
    "http://localhost:63343",  # Your IDE preview port if you use it
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # " * " allows ANY frontend origin to call your FastAPI backend cleanly!
    allow_credentials=True,
    allow_methods=["*"],  # Allows GET, POST, PATCH, OPTIONS, etc.
    allow_headers=["*"],  # Allows X-API-Key, Content-Type, etc.
)

# Register the external routers that the LGU IT teams will call
app.include_router(referral.router)
app.include_router(hospitals.router)

# A simple health-check endpoint to verify the server is running
@app.get("/")
async def root():
    return {"message": "Welcome to the IRDSS Interoperability Layer API. The server is live and secure."}
