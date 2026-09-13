from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


from app.risk import router as risk_router
from app.auth import router as auth_router


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "message": "CIVANTA-NER Backend is running!"
    }



app.include_router(risk_router)
app.include_router(auth_router)
