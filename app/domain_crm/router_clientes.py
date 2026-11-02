from fastapi import APIRouter, Request, Depends, Form, Response, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import json
import csv
import hashlib
import hmac
import io
import re
import time
import uuid
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.core.database import get_db
from app.domain_crm import crud_clientes
from app.core import models
from app.core.auth_deps import CurrentUser, verificar_login
from app.core.security import SECRET_KEY

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=[str(BASE_DIR / "app" / "templates"), str(BASE_DIR / "templates")])

router = APIRouter(prefix="/admin", tags=["crm_clientes"])
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 5000


def _normalizar_encabezado(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", value)


def _leer_archivo_clientes(filename, content):
    suffix = (filename or "").lower().rsplit(".", 1)[-1]
    if suffix not in {"csv", "xlsx"}:
        raise ValueError("Formato no compatible. Sube un archivo .CSV o .XLSX.")
    if not content or len(content) > MAX_IMPORT_BYTES:
        raise ValueError("El archivo está vacío o supera el límite de 5 MB.")
    if suffix == "xlsx":
        import openpyxl
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            matrix = []
            for index, row in enumerate(sheet.iter_rows(values_only=True, max_col=50)):
                if index > MAX_IMPORT_ROWS + 1:
                    raise ValueError(f"El archivo supera el máximo de {MAX_IMPORT_ROWS} clientes por importación.")
                matrix.append(row)
            workbook.close()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("No se pudo leer el Excel. Revisa que sea un .XLSX válido.") from exc
    else:
        decoded = None
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                decoded = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=";,\t,") if decoded else csv.excel
        except csv.Error:
            dialect = csv.excel
        matrix = []
        for index, row in enumerate(csv.reader(io.StringIO(decoded or ""), dialect)):
            if index > MAX_IMPORT_ROWS + 1:
                raise ValueError(f"El archivo supera el máximo de {MAX_IMPORT_ROWS} clientes por importación.")
            matrix.append(row)
    if not matrix or not matrix[0]:
        raise ValueError("El archivo no contiene encabezados.")
    headers = [_normalizar_encabezado(value) for value in matrix[0]]
    aliases = {
        "rut": {"rut", "documento", "identificacion", "dni", "cedula", "nrodocumento"},
        "nombre": {"nombre", "nombres", "firstname", "firstName".lower()},
        "apellido": {"apellido", "apellidos", "lastname", "surname"},
        "telefono": {"telefono", "celular", "movil", "phone", "phonenumber"},
        "correo": {"correo", "email", "mail", "emailaddress"},
    }
    indexes = {field: next((i for i, header in enumerate(headers) if header in names), None) for field, names in aliases.items()}
    if indexes["nombre"] is None:
        raise ValueError("No encontramos una columna de nombre. Revisa los encabezados del archivo.")
    parsed, errors = [], []
    for number, row in enumerate(matrix[1:], start=2):
        if not row or not any(str(value or "").strip() for value in row):
            continue
        if len(parsed) >= MAX_IMPORT_ROWS:
            raise ValueError(f"El archivo supera el máximo de {MAX_IMPORT_ROWS} clientes por importación.")
        def value(field):
            index = indexes[field]
            return str(row[index] or "").strip() if index is not None and index < len(row) else ""
        name = value("nombre")
        if not name:
            errors.append(f"Fila {number}: falta el nombre.")
            continue
        email = value("correo").lower()
        phone = value("telefono")
        if not email and not phone:
            errors.append(f"Fila {number}: falta correo y teléfono.")
            continue
        # El esquema actual requiere identificador. Para clientes sin RUT se usa
        # una referencia de importación estable, no un RUT ficticio visible.
        rut = value("rut")
        if not rut:
            key = email or phone
            rut = "IMP-" + hashlib.sha256(key.casefold().encode("utf-8")).hexdigest()[:24]
        parts = name.split()
        apellido_archivo = value("apellido")
        parsed.append({"rut": rut, "nombre": parts[0], "apellido": " ".join([*parts[1:], apellido_archivo]).strip() or "-",
                       "telefono": phone or "No informado", "correo": email or "sin-correo@importacion.norem"})
    if not parsed and errors:
        raise ValueError("No hay filas válidas para importar. " + " ".join(errors[:3]))
    return parsed, errors


def _render_import(request, cred, preview=None, error=None, result=None):
    return templates.TemplateResponse("admin/importar_clientes.html", {
        "request": request, "current_user": cred, "preview": preview,
        "error": error, "result": result,
    })


def _exigir_admin_tenant(cred):
    if cred.tenant_id == "default" or cred.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo el administrador de una cuenta de cliente puede importar datos.")


def _crear_token_previsualizacion(tenant_id, content):
    timestamp = str(int(time.time()))
    digest = hashlib.sha256(content).hexdigest()
    message = f"{tenant_id}:{digest}:{timestamp}".encode()
    signature = hmac.new(SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()
    return f"{timestamp}.{digest}.{signature}"


def _validar_token_previsualizacion(token, tenant_id, content):
    try:
        timestamp, digest, signature = token.split(".", 2)
        age = int(time.time()) - int(timestamp)
    except (ValueError, AttributeError):
        return False
    actual_digest = hashlib.sha256(content).hexdigest()
    expected = hmac.new(SECRET_KEY.encode(), f"{tenant_id}:{digest}:{timestamp}".encode(), hashlib.sha256).hexdigest()
    return 0 <= age <= 1800 and hmac.compare_digest(digest, actual_digest) and hmac.compare_digest(signature, expected)


TIPOS_CAMPO_CLIENTE = {"text", "textarea", "number", "date", "select", "checkbox"}


def _opciones_campo(campo):
    try:
        opciones = json.loads(campo.opciones_json or "[]")
        return [str(opcion) for opcion in opciones if str(opcion).strip()]
    except (TypeError, ValueError):
        return []


def _timeline_procesado(db, cliente_id, tenant_id):
    eventos = []
    for evt in crud_clientes.get_timeline(db=db, cliente_id=cliente_id, tenant_id=tenant_id):
        meta = {}
        if evt.metadata_json:
            try:
                meta = json.loads(evt.metadata_json)
            except (TypeError, ValueError):
                pass
        eventos.append({"id": evt.id, "tipo": evt.tipo_evento, "fecha": evt.creado_en, "meta": meta})
    return eventos


def _render_ficha_cliente(request, db, cred, cliente, error=None, valores_temporales=None):
    timeline = _timeline_procesado(db, cliente.id, cred.tenant_id)
    campos = db.query(models.CampoCliente).filter(
        models.CampoCliente.tenant_id == cred.tenant_id,
        models.CampoCliente.activo.is_(True),
    ).order_by(models.CampoCliente.orden, models.CampoCliente.id).all()
    valores_guardados = {
        fila.campo_id: fila.valor
        for fila in db.query(models.ValorCampoCliente).filter(
            models.ValorCampoCliente.tenant_id == cred.tenant_id,
            models.ValorCampoCliente.cliente_id == cliente.id,
            models.ValorCampoCliente.campo_id.in_([campo.id for campo in campos]),
        ).all()
    } if campos else {}
    campos_vista = []
    for campo in campos:
        valor = (valores_temporales or {}).get(campo.id, valores_guardados.get(campo.id, ""))
        campos_vista.append({"campo": campo, "valor": valor, "opciones": _opciones_campo(campo)})
    return templates.TemplateResponse("admin/crm_ficha.html", {
        "request": request, "cliente": cliente, "timeline": timeline,
        "current_user": cred, "campos_personalizados": campos_vista,
        "error_campos": error,
    })

@router.get("/clientes", response_class=HTMLResponse)
async def ver_directorio_clientes(request: Request, search: str = None, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    clientes = crud_clientes.get_clientes(db=db, tenant_id=cred.tenant_id, search=search)
    return templates.TemplateResponse("admin/crm_clientes.html", {
        "request": request,
        "clientes": clientes,
        "search": search,
        "current_user": cred
    })


@router.get("/clientes/importar", response_class=HTMLResponse)
async def pagina_importar_clientes(request: Request, cred: CurrentUser = Depends(verificar_login)):
    _exigir_admin_tenant(cred)
    return _render_import(request, cred)


@router.get("/clientes/campos", response_class=HTMLResponse)
async def configurar_campos_ficha_cliente(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    _exigir_admin_tenant(cred)
    campos = db.query(models.CampoCliente).filter(
        models.CampoCliente.tenant_id == cred.tenant_id
    ).order_by(models.CampoCliente.orden, models.CampoCliente.id).all()
    return templates.TemplateResponse("admin/crm_campos_cliente.html", {
        "request": request, "current_user": cred, "campos": campos,
        "tipos": TIPOS_CAMPO_CLIENTE,
    })


@router.post("/clientes/campos")
async def crear_campo_ficha_cliente(
    etiqueta: str = Form(...), tipo: str = Form("text"), opciones: str = Form(""),
    requerido: Optional[str] = Form(None), db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login),
):
    _exigir_admin_tenant(cred)
    etiqueta = etiqueta.strip()
    if not etiqueta or len(etiqueta) > 120 or tipo not in TIPOS_CAMPO_CLIENTE:
        raise HTTPException(status_code=400, detail="Revisa el nombre y tipo del campo.")
    opciones_limpias = list(dict.fromkeys(linea.strip() for linea in opciones.splitlines() if linea.strip()))
    if tipo == "select" and (len(opciones_limpias) < 2 or len(opciones_limpias) > 30 or any(len(item) > 100 for item in opciones_limpias)):
        raise HTTPException(status_code=400, detail="Un campo de selección necesita entre 2 y 30 opciones, de hasta 100 caracteres.")
    activos = db.query(models.CampoCliente).filter(
        models.CampoCliente.tenant_id == cred.tenant_id,
        models.CampoCliente.activo.is_(True),
    ).count()
    if activos >= 20:
        raise HTTPException(status_code=400, detail="Cada ficha puede tener hasta 20 campos personalizados activos.")
    campo = models.CampoCliente(
        tenant_id=cred.tenant_id, clave=uuid.uuid4().hex, etiqueta=etiqueta,
        tipo=tipo, opciones_json=json.dumps(opciones_limpias, ensure_ascii=False) if tipo == "select" else None,
        requerido=requerido == "1", activo=True, orden=activos,
    )
    db.add(campo)
    db.commit()
    return RedirectResponse("/admin/clientes/campos?creado=1", status_code=303)


@router.post("/clientes/campos/{campo_id}/desactivar")
async def desactivar_campo_ficha_cliente(campo_id: int, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    _exigir_admin_tenant(cred)
    campo = db.query(models.CampoCliente).filter(
        models.CampoCliente.id == campo_id,
        models.CampoCliente.tenant_id == cred.tenant_id,
    ).first()
    if not campo:
        raise HTTPException(status_code=404, detail="Campo no encontrado.")
    campo.activo = False
    db.commit()
    return RedirectResponse("/admin/clientes/campos?desactivado=1", status_code=303)


@router.post("/clientes/importar/vista-previa", response_class=HTMLResponse)
async def vista_previa_importacion(request: Request, archivo: UploadFile = File(...), cred: CurrentUser = Depends(verificar_login)):
    _exigir_admin_tenant(cred)
    try:
        content = await archivo.read(MAX_IMPORT_BYTES + 1)
        rows, errors = _leer_archivo_clientes(archivo.filename, content)
        return _render_import(request, cred, preview={"rows": rows, "errors": errors[:20], "invalid_count": len(errors), "filename": archivo.filename, "token": _crear_token_previsualizacion(cred.tenant_id, content)})
    except ValueError as exc:
        return _render_import(request, cred, error=str(exc))


@router.post("/clientes/importar/confirmar", response_class=HTMLResponse)
async def confirmar_importacion(request: Request, archivo: UploadFile = File(...), preview_token: str = Form(...), db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    _exigir_admin_tenant(cred)
    try:
        content = await archivo.read(MAX_IMPORT_BYTES + 1)
        if not _validar_token_previsualizacion(preview_token, cred.tenant_id, content):
            raise ValueError("La confirmación caducó o el archivo no coincide con la vista previa. Vuelve a revisarlo.")
        rows, errors = _leer_archivo_clientes(archivo.filename, content)
        existing = db.query(models.Cliente).filter(models.Cliente.tenant_id == cred.tenant_id).all()
        existing_ruts = {c.rut.strip().casefold() for c in existing if c.rut}
        existing_emails = {c.correo.strip().casefold() for c in existing if c.correo and "@importacion.norem" not in c.correo}
        seen_keys, seen_ruts, new_clients, skipped = set(), set(), [], 0
        for row in rows:
            email_key = row["correo"].casefold() if "@importacion.norem" not in row["correo"] else ""
            rut_key = row["rut"].strip().casefold()
            key = email_key or rut_key
            if rut_key in existing_ruts or rut_key in seen_ruts or (email_key and email_key in existing_emails) or key in seen_keys:
                skipped += 1
                continue
            seen_keys.add(key)
            seen_ruts.add(rut_key)
            new_clients.append(models.Cliente(tenant_id=cred.tenant_id, **row))
        db.add_all(new_clients)
        db.commit()
        result = {"imported": len(new_clients), "skipped": skipped, "invalid": len(errors)}
        return _render_import(request, cred, result=result)
    except ValueError as exc:
        db.rollback()
        return _render_import(request, cred, error=str(exc))
    except Exception:
        db.rollback()
        raise

@router.get("/clientes/{cliente_id}", response_class=HTMLResponse)
async def ver_ficha_cliente(request: Request, cliente_id: int, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    cliente = crud_clientes.get_cliente(db=db, cliente_id=cliente_id, tenant_id=cred.tenant_id)
    if not cliente:
        return RedirectResponse(url="/admin/clientes", status_code=303)
    return _render_ficha_cliente(request, db, cred, cliente)


@router.post("/clientes/{cliente_id}/campos")
async def guardar_campos_ficha_cliente(
    request: Request, cliente_id: int, db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login),
):
    cliente = crud_clientes.get_cliente(db=db, cliente_id=cliente_id, tenant_id=cred.tenant_id)
    if not cliente:
        return RedirectResponse(url="/admin/clientes", status_code=303)
    form = await request.form()
    campos = db.query(models.CampoCliente).filter(
        models.CampoCliente.tenant_id == cred.tenant_id,
        models.CampoCliente.activo.is_(True),
    ).order_by(models.CampoCliente.orden, models.CampoCliente.id).all()
    temporales, errores, cambios = {}, [], []
    existentes = {
        valor.campo_id: valor
        for valor in db.query(models.ValorCampoCliente).filter(
            models.ValorCampoCliente.tenant_id == cred.tenant_id,
            models.ValorCampoCliente.cliente_id == cliente.id,
            models.ValorCampoCliente.campo_id.in_([campo.id for campo in campos]),
        ).all()
    } if campos else {}

    for campo in campos:
        valor = "1" if campo.tipo == "checkbox" and form.get(f"campo_{campo.id}") == "1" else (
            "0" if campo.tipo == "checkbox" else str(form.get(f"campo_{campo.id}", "")).strip()
        )
        temporales[campo.id] = valor
        if campo.requerido and valor in {"", "0"}:
            errores.append(f"{campo.etiqueta} es obligatorio.")
            continue
        if len(valor) > (4000 if campo.tipo == "textarea" else 500):
            errores.append(f"{campo.etiqueta} supera el máximo permitido.")
            continue
        if campo.tipo == "number" and valor:
            try:
                Decimal(valor)
            except InvalidOperation:
                errores.append(f"{campo.etiqueta} debe ser numérico.")
                continue
        if campo.tipo == "date" and valor:
            try:
                date.fromisoformat(valor)
            except ValueError:
                errores.append(f"{campo.etiqueta} debe ser una fecha válida.")
                continue
        if campo.tipo == "select" and valor and valor not in _opciones_campo(campo):
            errores.append(f"Selecciona una opción válida para {campo.etiqueta}.")
            continue
        cambios.append((campo, valor, existentes.get(campo.id)))

    if errores:
        return _render_ficha_cliente(request, db, cred, cliente, error=" ".join(errores), valores_temporales=temporales)

    for campo, valor, existente in cambios:
        if existente:
            existente.valor = valor
        elif valor not in {"", "0"}:
            db.add(models.ValorCampoCliente(
                tenant_id=cred.tenant_id, cliente_id=cliente.id,
                campo_id=campo.id, valor=valor,
            ))
    db.commit()
    return RedirectResponse(url=f"/admin/clientes/{cliente.id}?campos_guardados=1", status_code=303)

@router.post("/clientes/{cliente_id}/notas")
async def agregar_nota_timeline(request: Request, cliente_id: int, texto_nota: str = Form(...), db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    crud_clientes.add_timeline_nota(db=db, cliente_id=cliente_id, tenant_id=cred.tenant_id, nota=texto_nota)
    return RedirectResponse(url=f"/admin/clientes/{cliente_id}", status_code=303)
