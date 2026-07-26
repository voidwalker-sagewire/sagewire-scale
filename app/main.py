from fastapi import FastAPI

app = FastAPI(
    title="SageWire Scale Service",
    description="Hardware-independent weighing infrastructure for the SageWire platform.",
    version="0.1.0"
)


@app.get("/")
def root():
    return {
        "service": "sagewire-scale",
        "status": "online",
        "version": "0.1.0"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/version")
def version():
    return {
        "version": "0.1.0"
    }


@app.get("/info")
def info():
    return {
        "service": "SageWire Scale Service",
        "purpose": "Hardware-independent weighing infrastructure",
        "database": "/data/scale.db",
        "status": "Under Development"
    }
