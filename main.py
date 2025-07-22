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
    RATE_TYPE,
)
from datetime import timedelta, datetime
from utils.schema import UserLoginSchema
import re


# Initialize logging

app = FastAPI()
origins = ["*"]
# handler = Mangum(app)
templates = Jinja2Templates(directory="template")

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
        company_details = (
            supabase.table(SUPABASE_TABLES.company_details)
            .select("*")
            .eq("id", 1)
            .execute()
        )

        if len(company_details.data) == 0:
            return failure_response("Company details not found", {}, 404)

        company_details = company_details.data[0]

        order = (
            supabase.table(SUPABASE_TABLES.orders)
            .select(
                f"""*,
                    {SUPABASE_TABLES.proforma_invoices}:{SUPABASE_TABLES.proforma_invoices}(*,
                    {SUPABASE_TABLES.proforma_additional_costs}:{SUPABASE_TABLES.proforma_additional_costs}(*,cost_type:{SUPABASE_TABLES.additional_costs_master}(name)),
                    {SUPABASE_TABLES.proforma_invoice_items}:{SUPABASE_TABLES.proforma_invoice_items}(*,
                    {SUPABASE_TABLES.products}:{SUPABASE_TABLES.products}(name,sku),
                    {SUPABASE_TABLES.thickness_master}:{SUPABASE_TABLES.thickness_master}(name,value,multiplier))),
                    {SUPABASE_TABLES.customers}:{SUPABASE_TABLES.customers}(name,company_name,gstin,phone,email,address,mobile,shipping_address)
                    )
                    """
            )
            .eq("id", order_id)
            .execute()
        )

        if len(order.data) == 0:
            return failure_response("Order not found", {}, 404)

        order_data = order.data[0]

        proforma_invoice = order_data["proforma_invoices"]
        customer = order_data["customers"]
        items = proforma_invoice.get("proforma_items", [])

        # Calculate totals
        total_qty = sum(item.get("quantity", 0) for item in items)
        total_weight = sum(item.get("weight", 0) for item in items)

        # Process items
        processed_items = [
            {
                "name": item.get("products", {}).get("name", ""),
                "weight": f'{item.get("weight", 0):.2f}',
                "width": item.get("size_width", ""),
                "height": item.get("size_height", ""),
                "qty": item.get("quantity", 0),
                "rate": item.get("rate", 0),
                "unit": item.get("unit", ""),
                "amount": item.get("amount", 0),
                "rate_type": RATE_TYPE[item.get("rate_type", "")],
                "size_width_fraction": item.get("size_width_fraction", ""),
                "size_height_fraction": item.get("size_height_fraction", ""),
                "thickness": item.get("thickness_master", {}).get("name", ""),
            }
            for item in items
        ]

        additional_costs = proforma_invoice.get("proforma_additional_costs", [])

        additional_costs_data = [
            {
                "name": cost.get("cost_type", {}).get("name", ""),
                "amount": cost.get("amount", 0),
            }
            for cost in additional_costs
        ]

        # Calculate GST
        is_gst = proforma_invoice.get("is_gst", False)
        total_gst = proforma_invoice.get("gst_amount", 0)
        cgst = total_gst / 2 if is_gst else 0
        sgst = total_gst / 2 if is_gst else 0

        # print("proforma_invoice.get('created_at')", processed_items)

        form_data = {
            "company_logo": company_details.get("logo"),
            "company_name": company_details.get("company_name"),
            "company_address": company_details.get("address"),
            "company_mobile": ", ".join(company_details.get("mobile_nos", [])),
            "company_email": company_details.get("email_id"),
            "company_gst": company_details.get("gst_no"),
            "company_pan": company_details.get("pan_no"),
            "proforma_no": proforma_invoice.get("pi_name"),
            "pi_date": convertDateToProperFormat(proforma_invoice.get("created_at")),
            "destination": proforma_invoice.get("destination", ""),
            "delivery_date": proforma_invoice.get("delivery_date", ""),
            "payment_term": proforma_invoice.get("payment_term", "0"),
            "revise_by": proforma_invoice.get("revise_by", ""),
            "transport": proforma_invoice.get("transport", "Customer"),
            "unloading": proforma_invoice.get("unloading", "Customer"),
            "sales_person": proforma_invoice.get("sales_person", ""),
            "vehicle_no": proforma_invoice.get("vehicle_no", "0"),
            "bill_to": {
                "name": customer.get("company_name") or customer.get("name"),
                "address": customer.get("address"),
                "phone": customer.get("phone"),
                "mobile": customer.get("mobile"),
                "gst": customer.get("gstin"),
            },
            "ship_to": {
                "name": customer.get("company_name") or customer.get("name"),
                "address": customer.get("shipping_address") or customer.get("address"),
                "phone": customer.get("phone"),
                "mobile": customer.get("mobile"),
            },
            "proforma_items": processed_items,
            "total_qty": total_qty,
            "basic_total": proforma_invoice.get("total_amount", 0),
            "remarks": proforma_invoice.get("remarks", ""),
            "total_weight": f"{total_weight:.2f}",
            "additional_costs": additional_costs_data,
            "cgst": cgst,
            "sgst": sgst,
            "is_gst": is_gst,
            "total_gst": total_gst if is_gst else 0,
            "grand_total": proforma_invoice.get("grand_total", 0),
            "bank_name": company_details.get("bank_account_name"),
            "bank": company_details.get("bank_name"),
            "branch": company_details.get("branch", ""),
            "account_no": company_details.get("bank_account_no"),
            "ifsc": company_details.get("ifsc_code"),
            "terms": company_details.get("terms_and_conditions", []),
        }

        pdf_context = {"form": form_data}

        print("pdf_context: ", pdf_context)

        pdf_bytes = createPdf(pdf_context, templates, "invoice.html")

        print("PDF generated successfully")

        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as e:
        print(e)
        return failure_response(str(e), {}, 500)
