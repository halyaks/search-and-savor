import os
from dotenv import load_dotenv
from fastapi import FastAPI
#from fastapi.middleware.cors import CORSMiddleware
from app.youtube_service import search_videos

load_dotenv()

app=FastAPI(
    title=os.getenv("APP_NAME","Search & Savor API"),
    version="1.0.0"
)
""" app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
) """
@app.get("/")
def root():
    return {
        "message": "Search & Savor API running"
    }

@app.get("/health")
def health():
    return {
        "status": "Healthy"
    }

@app.get("/search")
def search(
    dish: str,
    language: str
):
    return search_videos(
        dish,
        language
    )