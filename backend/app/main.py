from fastapi import FastAPI

app = FastAPI(
    title="AI Sales Agent API",
    version="0.1.0",
)


@app.get("/")
async def root():
    return {
        "service": "AI Sales Agent API",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}