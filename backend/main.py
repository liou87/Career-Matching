from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine
import models
from routers import profile, jobs, analysis

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Job Helper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(analysis.router)


@app.get("/")
def root():
    return {"status": "ok", "message": "Job Helper API running"}
