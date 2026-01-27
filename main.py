from fastapi import FASTAPI

app =FASTAPI()

@app.get("/welcome")
def welcome():
    return {
        "message":"hello world"
    }
