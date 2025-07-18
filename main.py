from fastapi import FastAPI, Response, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from utils.helpers import (
    failure_response,
    verify_token,
    success_response,
    convertDateToProperFormat,
    createPdf,
)

# from mangum import Mangum
from fastapi.templating import Jinja2Templates
from utils.supabaseClient import supabase
from utils.constants import (
    SUPABASE_TABLES,
    CURRENT_TIME,
)
from datetime import timedelta, datetime
from utils.schema import UserLoginSchema
import re


# Initialize logging

app = FastAPI()
origins = ["*"]
# handler = Mangum(app)
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def jwt_middleware(request: Request, call_next):
    excluded_paths = [
        "/open-route",
        "/docs",
        "/openapi.json",
        "/",
        "/env-check",
        "/v1/register",
        "/login",
    ]  # Add paths to exclude from JWT check

    wildcard_excluded_paths = [
        "/static/*",
        # "/dispatch-invoice/*",
    ]  # Add wild path to exclude from jwt check

    if request.method.lower() == "options":
        return await call_next(request)

    auth_header = request.headers.get("Authorization")

    if request.url.path in excluded_paths:
        return await call_next(request)

    if any(re.match(pattern, request.url.path) for pattern in wildcard_excluded_paths):
        return await call_next(request)

    if auth_header is None or not auth_header.startswith("Bearer "):
        return failure_response("Access denied", {}, 401)

    token = auth_header.split(" ")[1]
    try:
        user = verify_token(token)
        request.state.user = user["decoded_token"]
    except HTTPException as e:
        return failure_response(e.detail, status_code=e.status_code)

    response = await call_next(request)
    return response


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/stats")
async def get_stats():
    try:
        # print(await pgConn.fetch("SELECT 1"))
        # Get current month's orders
        current_month = CURRENT_TIME.strftime("%Y-%m")
        # print(current_month)
        current_month_orders = (
            supabase.table(SUPABASE_TABLES["orders"])
            .select("*", count="exact")
            .gte("created_at", datetime.strptime(f"{current_month}-01", "%Y-%m-%d"))
            .lt(
                "created_at",
                (
                    datetime.strptime(f"{current_month}-01", "%Y-%m-%d")
                    + timedelta(days=32)
                ).replace(day=1),
            )
            .execute()
        )
        # print(current_month_orders)

        # Get previous month's orders
        previous_month = (CURRENT_TIME.replace(day=1) - timedelta(days=1)).strftime(
            "%Y-%m"
        )
        # print(previous_month)
        previous_month_orders = (
            supabase.table(SUPABASE_TABLES["orders"])
            .select("*", count="exact")
            .gte("created_at", datetime.strptime(f"{previous_month}-01", "%Y-%m-%d"))
            .lt(
                "created_at",
                (
                    datetime.strptime(f"{previous_month}-01", "%Y-%m-%d")
                    + timedelta(days=32)
                ).replace(day=1),
            )
            .execute()
        )

        # Calculate stats
        current_month_total = sum(
            order["total_value"] for order in current_month_orders.data
        )
        previous_month_total = sum(
            order["total_value"] for order in previous_month_orders.data
        )

        current_month_count = current_month_orders.count
        previous_month_count = previous_month_orders.count

        # Calculate percentage changes
        revenue_change_percent = (
            ((current_month_total - previous_month_total) / previous_month_total * 100)
            if previous_month_total > 0
            else 0
        )
        order_count_change_percent = (
            ((current_month_count - previous_month_count) / previous_month_count * 100)
            if previous_month_count > 0
            else 0
        )

        stats = {
            "current_month": {
                "total_orders": current_month_count,
                "total_revenue": current_month_total,
            },
            "previous_month": {
                "total_orders": previous_month_count,
                "total_revenue": previous_month_total,
            },
            "changes": {
                "revenue_change_percent": round(revenue_change_percent, 2),
                "order_count_change_percent": round(order_count_change_percent, 2),
            },
        }

        return success_response("Stats fetched successfully", stats, 200)
    except Exception as e:
        print(e)
        return failure_response(str(e), {}, 500)


@app.post("/login")
async def login(data: UserLoginSchema):
    try:
        data = supabase.auth.sign_in_with_password(
            credentials={"email": data.email, "password": data.password}
        )

        access_token = data.session.access_token
        refresh_token = data.session.refresh_token
        token_type = data.session.token_type
        identity_data = data.user.identities[0].identity_data
        user_data = {
            **identity_data,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": token_type,
        }

        return success_response("Login successful", user_data, 200)
    except Exception as e:
        print(e)
        return failure_response(str(e), {}, 500)


@app.get("/invoice/{order_id}")
async def generate_pdf(
    order_id: str,
):
    # print("Generating invoice for order_id: ", SUPABASE_URL, SUPABASE_ANON_KEY)
    try:
        order = (
            supabase.table(SUPABASE_TABLES.orders)
            .select(
                f"""*,
                    {SUPABASE_TABLES.proforma_invoices}:{SUPABASE_TABLES.proforma_invoices}(*,
                    {SUPABASE_TABLES.proforma_additional_costs}:{SUPABASE_TABLES.proforma_additional_costs}(*),
                    {SUPABASE_TABLES.proforma_invoice_items}:{SUPABASE_TABLES.proforma_invoice_items}(*,
                    {SUPABASE_TABLES.products}:{SUPABASE_TABLES.products}(name,sku),
                    {SUPABASE_TABLES.thickness_master}:{SUPABASE_TABLES.thickness_master}(name,value,multiplier))),
                    {SUPABASE_TABLES.customers}:{SUPABASE_TABLES.customers}(name,company_name,gstin,phone,email)
                    )
                    """
            )
            .eq("id", order_id)
            .execute()
        )

        if len(order.data) == 0:
            return failure_response("Order not found", {}, 404)

        order_data = order.data[0]

        return success_response("Invoice generated successfully", order_data, 200)
    except Exception as e:
        print(e)
        return failure_response(str(e), {}, 500)
