from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.deps import templates
from app.security import is_auth_bypassed, safe_next, verify_credentials

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "", error: str | None = None):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"next": safe_next(next), "error": error, "bypassed": is_auth_bypassed()},
    )


@router.post("/login")
def do_login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form(""),
):
    target = safe_next(next)
    if is_auth_bypassed():
        request.session["user"] = "dev"
        return RedirectResponse(url=target, status_code=303)
    if not verify_credentials(username, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"next": target, "error": "Credenziali non valide.", "bypassed": False},
            status_code=401,
        )
    request.session["user"] = username
    return RedirectResponse(url=target, status_code=303)


@router.post("/logout")
def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/healthz", response_class=HTMLResponse)
def healthz():
    return HTMLResponse("ok")
