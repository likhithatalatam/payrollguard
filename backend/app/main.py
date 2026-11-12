from fastapi import FastAPI

app = FastAPI(
    title="PayrollGuard",
    description="Payroll validation, exception management and reconciliation system",
    version="1.0.0"
)

@app.get("/")
def home():
    return {
        "message": "Welcome to PayrollGuard",
        "status": "running"
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }