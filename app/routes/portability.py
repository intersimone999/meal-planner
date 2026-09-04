import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.deps import get_session, templates
from app.portability import export_all, import_all

router = APIRouter(tags=["portability"])


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request):
    return templates.TemplateResponse(
        request, "portability.html", {"summary": None, "error": None}
    )


@router.post("/import", response_class=HTMLResponse)
def do_import(
    request: Request,
    file: UploadFile,
    session: Session = Depends(get_session),
):
    raw = file.file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return templates.TemplateResponse(
            request,
            "portability.html",
            {"summary": None, "error": f"File non è JSON valido: {e}"},
            status_code=400,
        )
    if not isinstance(data, dict):
        return templates.TemplateResponse(
            request,
            "portability.html",
            {"summary": None, "error": "Il JSON di primo livello deve essere un oggetto."},
            status_code=400,
        )
    summary = import_all(session, data)
    return templates.TemplateResponse(
        request, "portability.html", {"summary": summary, "error": None}
    )


@router.get("/export")
def do_export(session: Session = Depends(get_session)):
    data = export_all(session)
    body = json.dumps(data, ensure_ascii=False, indent=2)
    fname = f"meal-planner-{date.today().isoformat()}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
