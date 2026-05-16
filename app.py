import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()


def load_env_file():
    env_path = Path(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )


def get_required_env(name: str):
    value = os.getenv(name)
    if value:
        return value

    return None


def call_azure_function(url: str, method: str, payload=None):
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    azure_request = UrlRequest(url, data=data, headers=headers, method=method)

    try:
        with urlopen(azure_request, timeout=20) as azure_response:
            body = azure_response.read()
            content_type = azure_response.headers.get("content-type", "application/json")

            return Response(
                content=body,
                status_code=azure_response.status,
                media_type=content_type.split(";")[0],
            )
    except HTTPError as error:
        body = error.read()
        content_type = error.headers.get("content-type", "text/plain")

        return Response(
            content=body,
            status_code=error.code,
            media_type=content_type.split(";")[0],
        )
    except URLError as error:
        return JSONResponse(
            {"message": f"Could not reach Azure Function: {error.reason}"},
            status_code=502,
        )


@app.post("/api/orders")
async def submit_order(request: Request):
    order_trigger_url = get_required_env("ORDER_TRIGGER_URL")
    if not order_trigger_url:
        return JSONResponse(
            {"message": "ORDER_TRIGGER_URL is not configured"},
            status_code=500,
        )

    payload = await request.json()
    return call_azure_function(order_trigger_url, "POST", payload)


@app.get("/api/summary")
def fetch_summary():
    summary_trigger_url = get_required_env("SUMMARY_TRIGGER_URL")
    if not summary_trigger_url:
        return JSONResponse(
            {"message": "SUMMARY_TRIGGER_URL is not configured"},
            status_code=500,
        )

    return call_azure_function(summary_trigger_url, "GET")
