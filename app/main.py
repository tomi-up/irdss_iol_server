from fastapi import FastAPI
from app.routers import referral, hospitals

# Initialize the FastAPI application gateway
app = FastAPI(
    title="IRDSS Interoperability Layer API",
    description="API Gateway for the Mindanao-wide Intelligent Referral Decision Support System.",
    version="1.0.0"
)

# Register the external routers that the LGU IT teams will call
app.include_router(referral.router)
app.include_router(hospitals.router)

# A simple health-check endpoint to verify the server is running
@app.get("/")
async def root():
    return {"message": "Welcome to the IRDSS Interoperability Layer API. The server is live and secure."}