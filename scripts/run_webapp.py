import uvicorn

if __name__ == "__main__":
    uvicorn.run("murdoku.webapp:app", host="127.0.0.1", port=8420, reload=False)
