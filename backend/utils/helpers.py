from datetime import datetime

from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse
from .constants import (
    TIMESTAMP_FORMAT,
    CURRENT_TIME,
)
from datetime import datetime
import jwt
import pytz
from weasyprint import HTML
from io import BytesIO
from .supabaseClient import supabase


def response_content(
    msg: str = "",
    data: dict = dict(),
    success_type: bool = True,
    error_type: bool = False,
    status_code: int = 200,
):
    return {
        "success": success_type,
        "status": status_code,
        "error": error_type,
        "messages": msg,
        "result": data,
        "serverdatetime": datetime.now().strftime(TIMESTAMP_FORMAT),
        "db_version": 1.0,
    }


def success_response(
    msg: str = "",
    data: dict = dict(),
    status_code: int = 200,
    different_response: bool = False,
    another_response: dict = dict(),
):
    if different_response:
        return JSONResponse(content=another_response, status_code=status_code)

    return JSONResponse(
        content=response_content(msg=msg, data=data, status_code=status_code),
        status_code=status_code,
    )


def failure_response(
    msg: str = "",
    data: dict = dict(),
    status_code: int = 400,
    different_response: bool = False,
    another_response: dict = dict(),
):
    if different_response:
        return JSONResponse(content=another_response, status_code=status_code)

    return JSONResponse(
        content=response_content(
            msg=msg,
            data=data,
            success_type=False,
            error_type=True,
            status_code=status_code,
        ),
        status_code=status_code,
    )


def convertDatetimeObjectToStr(value: datetime):
    try:
        return value.isoformat()
    except Exception as e:
        print(e)
        return value


def convertDOB(value: str) -> str:
    try:
        return datetime.strptime(value, "%d-%m-%Y").strftime("%Y-%m-%d")
    except Exception as e:
        print("DOB exception", e)
        return value


def verify_token(access_token: str):
    token = access_token
    try:
        token_data = supabase.auth.get_user(access_token)

        return dict({"decoded_token": token_data, "token": token})
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    except Exception as e:
        print(e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


async def get_current_user(request: Request):
    return request.state.user["sub"]


def convertDateToProperFormat(string_date: str):
    if "." in string_date:
        date_part, tz_part = string_date.split("+")
        time_part, frac = date_part.split(".")
        frac = (frac + "000000")[:6]  # pad to 6 digits
        s_fixed = f"{time_part}.{frac}+{tz_part}"
    else:
        s_fixed = string_date

    return (
        datetime.fromisoformat(s_fixed)
        .astimezone(pytz.timezone("Asia/Kolkata"))
        .strftime(TIMESTAMP_FORMAT)
    )


def createPdf(data, templates, template_to_choose):
    try:
        print(f"Creating PDF with template: {template_to_choose}")
        context = {
            **data,
            "date": CURRENT_TIME.strftime(TIMESTAMP_FORMAT),
            "current_year": CURRENT_TIME.year,
        }

        template = templates.get_template(template_to_choose)

        print("Template loaded successfully")

        html_content = template.render(context)
        print("HTML content rendered successfully")

        pdf_bytes = BytesIO()
        HTML(string=html_content).write_pdf(pdf_bytes)
        print("PDF generation completed")

        pdf_bytes.seek(0)
        return pdf_bytes.getvalue()

    except Exception as e:
        print(f"Error in createPdf: {str(e)}")
        print(f"Template: {template_to_choose}")
        raise e
