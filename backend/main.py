from fastapi import FastAPI, Response, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from utils.helpers import (
    failure_response,
    verify_token,
    success_response,
    convertDateToProperFormat,
    createPdf,
    get_financial_year,
    parse_fractional_inch,
)

from mangum import Mangum
from fastapi.templating import Jinja2Templates
from utils.supabaseClient import supabase
from utils.constants import (
    SUPABASE_TABLES,
    CURRENT_TIME,
    RATE_TYPE,
)
from datetime import timedelta, datetime
from utils.schema import UserLoginSchema, SizeSheetRequest
import re
from supabase import Client
from natsort import natsorted
from math import ceil


# Initialize logging

app = FastAPI()
origins = ["*"]
handler = Mangum(app)
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
        request.state.authenticated_client = user["authenticated_client"]
    except HTTPException as e:
        return failure_response(e.detail, status_code=e.status_code)

    response = await call_next(request)
    return response


async def get_authenticated_client(request: Request) -> Client:
    return request.state.authenticated_client


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/latest-invoice-number")
async def latest_invoice_number(
    authenticated_client: Client = Depends(get_authenticated_client),
):
    try:
        fy = get_financial_year()
        result = authenticated_client.rpc(
            "get_next_invoice_number", {"fy_param": fy}
        ).execute()

        print("result: ", result)

        if result.data is None:
            return failure_response(result.error.message, {}, 500)

        invoice_number = result.data

        return success_response(
            "Financial year fetched successfully",
            {"invoice_number": invoice_number},
            200,
        )
    except Exception as e:
        print(e)
        return failure_response(str(e), {}, 500)


@app.post("/size-sheet/{customer_id}")
async def size_sheet(
    customer_id: str,
    payload: SizeSheetRequest,
    authenticated_client: Client = Depends(get_authenticated_client),
):
    try:
        company_details = (
            authenticated_client.table(SUPABASE_TABLES.company_details)
            .select("*")
            .eq("id", 1)
            .execute()
        )

        if len(company_details.data) == 0:
            return failure_response("Company details not found", {}, 404)

        company_details = company_details.data[0]

        customer_resp = (
            authenticated_client.table(SUPABASE_TABLES.customers)
            .select(
                "name,company_name,gstin,phone,email,address,mobile,shipping_address"
            )
            .eq("id", customer_id)
            .limit(1)
            .execute()
        )

        if len(customer_resp.data) == 0:
            return failure_response("Customer not found", {}, 404)

        customer = customer_resp.data[0]

        processed_items = []
        total_qty = 0
        total_sqft = 0.0
        total_weight = 0.0

        for item in payload.items:
            unit = (item.unit or "ft").lower()
            total_weight += float(item.weight or 0.0)
            qty = int(item.quantity or 0)

            if unit == "mm":
                width_feet = float(item.size_width)
                height_feet = float(item.size_height)
                line_sqft = width_feet * height_feet * qty * 10.764 / 1000000
                total_sqft += line_sqft
            elif unit == "inch":
                width_inches = parse_fractional_inch(
                    item.size_width, item.size_width_fraction or ""
                )
                height_inches = parse_fractional_inch(
                    item.size_height, item.size_height_fraction or ""
                )

                width_rounding_value = int(item.width_rounding_value or 0)
                height_rounding_value = int(item.height_rounding_value or 0)

                if width_rounding_value and width_rounding_value > 0:
                    width_inches = (
                        ceil(width_inches / width_rounding_value) * width_rounding_value
                    )

                if height_rounding_value and height_rounding_value > 0:
                    height_inches = (
                        ceil(height_inches / height_rounding_value)
                        * height_rounding_value
                    )

                width_feet = width_inches
                height_feet = height_inches
                line_sqft = width_feet * height_feet * qty / 144
                total_sqft += line_sqft
            else:
                width_feet = float(item.size_width)
                height_feet = float(item.size_height)
                line_sqft = width_feet * height_feet * qty
                total_sqft += line_sqft

            total_qty += qty

            processed_items.append(
                {
                    "customer_order_no": item.customer_order_no or "",
                    "name": item.product_name or "",
                    "thickness": item.thickness or "",
                    "width": item.size_width,
                    "height": item.size_height,
                    "unit": unit,
                    "qty": qty,
                    "weight": f"{(item.weight or 0):.2f}",
                    "size_width_fraction": item.size_width_fraction or "",
                    "size_height_fraction": item.size_height_fraction or "",
                    "total_sqft": f"{line_sqft:.2f}",
                }
            )
        processed_items = natsorted(
            processed_items, key=lambda x: x.get("customer_order_no", "")
        )

        form_data = {
            "company_logo": company_details.get("logo"),
            "company_name": company_details.get("company_name"),
            "company_address": company_details.get("address"),
            "company_mobile": ", ".join(company_details.get("mobile_nos", [])),
            "company_email": company_details.get("email_id"),
            "company_gst": company_details.get("gst_no"),
            "company_pan": company_details.get("pan_no"),
            "title": payload.title or "Size Sheet",
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
            "items": processed_items,
            "total_qty": total_qty,
            "total_weight": f"{total_weight:.2f}",
            "total_sqft": f"{total_sqft:.2f}",
            "remarks": payload.remarks or "",
        }

        pdf_context = {"form": form_data}

        pdf_bytes = createPdf(pdf_context, templates, "size_sheet.html")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": f'attachment; filename="size_sheet_{customer_id}.pdf"',
            },
        )
    except Exception as e:
        print(e)
        return failure_response(str(e), {}, 500)


@app.get("/stats")
async def get_stats(authenticated_client: Client = Depends(get_authenticated_client)):
    try:
        # Get current month's orders
        current_month = CURRENT_TIME.strftime("%Y-%m")
        current_month_orders = (
            authenticated_client.table(SUPABASE_TABLES.orders)
            .select(
                f"""*,
                    {SUPABASE_TABLES.proforma_invoices}:{SUPABASE_TABLES.proforma_invoices}(*)
                    """,
                count="exact",
            )
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

        # Get previous month's orders
        previous_month = (CURRENT_TIME.replace(day=1) - timedelta(days=1)).strftime(
            "%Y-%m"
        )
        previous_month_orders = (
            authenticated_client.table(SUPABASE_TABLES.orders)
            .select(
                f"""*,
                    {SUPABASE_TABLES.proforma_invoices}:{SUPABASE_TABLES.proforma_invoices}(*)
                    """,
                count="exact",
            )
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

        # Get recent activity - new quotations in pending status for current month
        current_month_quotations = (
            authenticated_client.table(SUPABASE_TABLES.orders)
            .select(
                f"""*,
                    {SUPABASE_TABLES.proforma_invoices}:{SUPABASE_TABLES.proforma_invoices}(*),
                    {SUPABASE_TABLES.customers}:{SUPABASE_TABLES.customers}(name, company_name)
                    """,
                count="exact",
            )
            .gte("created_at", datetime.strptime(f"{current_month}-01", "%Y-%m-%d"))
            .lt(
                "created_at",
                (
                    datetime.strptime(f"{current_month}-01", "%Y-%m-%d")
                    + timedelta(days=32)
                ).replace(day=1),
            )
            .eq("status", "pending")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )

        # Get total customers count
        total_customers = (
            authenticated_client.table(SUPABASE_TABLES.customers)
            .select("*", count="exact")
            .execute()
        )

        # Get delivered orders count
        delivered_orders = (
            authenticated_client.table(SUPABASE_TABLES.orders)
            .select("*", count="exact")
            .eq("status", "delivered")  # Assuming there's a status field
            .execute()
        )

        # Get monthly orders data for the last 12 months for graph
        monthly_orders_data = []
        for i in range(12):
            month_date = CURRENT_TIME.replace(day=1) - timedelta(days=i * 30)
            month_str = month_date.strftime("%Y-%m")

            month_orders = (
                authenticated_client.table(SUPABASE_TABLES.orders)
                .select(
                    f"""*,
                        {SUPABASE_TABLES.proforma_invoices}:{SUPABASE_TABLES.proforma_invoices}(*)
                        """,
                    count="exact",
                )
                .gte("created_at", datetime.strptime(f"{month_str}-01", "%Y-%m-%d"))
                .lt(
                    "created_at",
                    (
                        datetime.strptime(f"{month_str}-01", "%Y-%m-%d")
                        + timedelta(days=32)
                    ).replace(day=1),
                )
                .execute()
            )

            month_revenue = (
                sum(
                    order["proforma_invoices"]["grand_total"]
                    for order in month_orders.data
                )
                if month_orders.data
                else 0
            )

            monthly_orders_data.append(
                {
                    "month": month_date.strftime("%B %Y"),
                    "month_key": month_str,
                    "order_count": month_orders.count or 0,
                    "revenue": float(f"{month_revenue:.2f}"),
                }
            )

        # Reverse to get chronological order
        monthly_orders_data.sort(key=lambda x: x["month_key"])

        # Calculate stats
        current_month_total = sum(
            float(f"{order['proforma_invoices']['grand_total']:.2f}")
            for order in current_month_orders.data
        )
        previous_month_total = sum(
            float(f"{order['proforma_invoices']['grand_total']:.2f}")
            for order in previous_month_orders.data
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

        # Process recent activity data
        recent_activity = []
        for order in current_month_quotations.data:
            customer_name = order.get("customers", {}).get("company_name") or order.get(
                "customers", {}
            ).get("name", "Unknown")
            recent_activity.append(
                {
                    "order_id": order.get("id"),
                    "customer_name": customer_name,
                    "created_at": order.get("created_at"),
                    "proforma_number": order.get("proforma_invoices", {}).get(
                        "pi_name", "N/A"
                    ),
                    "total_amount": float(
                        f"{order.get('proforma_invoices', {}).get('grand_total', 0):.2f}"
                    ),
                    "status": order.get("status", "N/A"),
                }
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
            "recent_activity": {
                "pending_quotations_count": current_month_quotations.count or 0,
                "recent_quotations": recent_activity,
            },
            "system_overview": {
                "total_customers": total_customers.count or 0,
                "delivered_orders": delivered_orders.count or 0,
            },
            "monthly_data": monthly_orders_data,
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
    authenticated_client: Client = Depends(get_authenticated_client),
):
    # print("Generating invoice for order_id: ", SUPABASE_URL, SUPABASE_ANON_KEY)
    try:
        company_details = (
            authenticated_client.table(SUPABASE_TABLES.company_details)
            .select("*")
            .eq("id", 1)
            .execute()
        )

        if len(company_details.data) == 0:
            return failure_response("Company details not found", {}, 404)

        company_details = company_details.data[0]

        order = (
            authenticated_client.table(SUPABASE_TABLES.orders)
            .select(
                f"""*,
                    {SUPABASE_TABLES.proforma_invoices}:{SUPABASE_TABLES.proforma_invoices}(*,
                    {SUPABASE_TABLES.users}:{SUPABASE_TABLES.users}(full_name),
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
        # total_qty = sum(item.get("quantity", 0) for item in items)
        # total_weight = sum(item.get("weight", 0) for item in items)
        total_qty = 0
        total_weight = 0

        # Process items
        processed_items = []
        total_items_sqft = 0
        for item in items:
            quantity = int(item.get("quantity", 0))
            total_weight += item.get("weight", 0)
            total_qty += quantity

            # first convert the width and height to feet
            # if the unit is mm, then convert to feet
            if item.get("unit") == "mm":
                width_feet = float(item.get("size_width", 0))
                height_feet = float(item.get("size_height", 0))

                total_sqft = width_feet * height_feet * quantity * 10.764 / 1000000

                total_items_sqft += total_sqft
            elif item.get("unit") == "inch":
                size_width_fraction = item.get("size_width_fraction", "")
                size_height_fraction = item.get("size_height_fraction", "")
                width_whole = item.get("size_width", 0)
                height_whole = item.get("size_height", 0)

                width_inches = parse_fractional_inch(width_whole, size_width_fraction)
                height_inches = parse_fractional_inch(
                    height_whole, size_height_fraction
                )

                width_rounding_value = int(item.get("width_rounding_value", 0))
                height_rounding_value = int(item.get("height_rounding_value", 0))

                if width_rounding_value and width_rounding_value > 0:
                    width_inches = (
                        ceil(width_inches / width_rounding_value) * width_rounding_value
                    )
                if height_rounding_value and height_rounding_value > 0:
                    height_inches = (
                        ceil(height_inches / height_rounding_value)
                        * height_rounding_value
                    )

                width_feet = width_inches
                height_feet = height_inches

                total_sqft = width_feet * height_feet * quantity / 144

                total_items_sqft += total_sqft

            else:
                width_feet = item.get("size_width", 0)
                height_feet = item.get("size_height", 0)

                total_sqft = width_feet * height_feet * quantity

                total_items_sqft += total_sqft

            processed_items.append(
                {
                    "customer_order_no": item.get("customer_order_no", ""),
                    "name": item.get("products", {}).get("name", ""),
                    "weight": f'{item.get("weight", 0):.2f}',
                    "width": item.get("size_width", ""),
                    "height": item.get("size_height", ""),
                    "total_sqft": f"{total_sqft:.2f}",
                    "qty": item.get("quantity", 0),
                    "rate": item.get("rate", 0),
                    "unit": item.get("unit", ""),
                    "amount": item.get("amount", 0),
                    "rate_type": RATE_TYPE[item.get("rate_type", "")],
                    "size_width_fraction": item.get("size_width_fraction", ""),
                    "size_height_fraction": item.get("size_height_fraction", ""),
                    "thickness": item.get("thickness_master", {}).get("name", ""),
                }
            )

        # sort the processed_items by customer_order_no
        # processed_items.sort(key=lambda x: x.get("customer_order_no", ""))
        processed_items = natsorted(
            processed_items, key=lambda x: x.get("customer_order_no", "")
        )

        additional_costs = proforma_invoice.get("proforma_additional_costs", [])
        additional_costs_data = list()

        if len(additional_costs) > 0:
            additional_costs_data = [
                {
                    "name": cost.get("cost_type", {}).get("name", ""),
                    "amount": cost.get("amount", 0),
                }
                for cost in additional_costs
            ]

        # Calculate GST
        is_gst = proforma_invoice.get("is_gst", False)
        total_cost_with_additional_cost = proforma_invoice.get("total_amount", 0)

        if len(additional_costs_data) > 0:
            total_cost_with_additional_cost = total_cost_with_additional_cost + sum(
                cost.get("amount", 0) for cost in additional_costs_data
            )

        total_gst = proforma_invoice.get("gst_amount", 0)
        cgst = total_gst / 2 if is_gst else 0
        sgst = total_gst / 2 if is_gst else 0

        # Calculate advanced payment
        has_advanced_payment = proforma_invoice.get("has_advanced_payment", False)
        advanced_payment_amount = (
            proforma_invoice.get("advanced_payment_amount", 0)
            if has_advanced_payment
            else 0
        )
        advanced_payment_notes = (
            proforma_invoice.get("advanced_payment_notes", "")
            if has_advanced_payment
            else ""
        )

        grand_total = proforma_invoice.get("grand_total", 0)
        balance_amount = (
            grand_total - advanced_payment_amount
            if has_advanced_payment
            else grand_total
        )

        sales_person = "Default"
        if proforma_invoice.get("users", {}) is not None:
            sales_person = proforma_invoice.get("users", {}).get("full_name", "")

        form_data = {
            "company_logo": company_details.get("logo"),
            "company_name": company_details.get("company_name"),
            "company_address": company_details.get("address"),
            "company_mobile": ", ".join(company_details.get("mobile_nos", [])),
            "company_email": company_details.get("email_id"),
            "company_gst": company_details.get("gst_no"),
            "company_pan": company_details.get("pan_no"),
            "proforma_no": proforma_invoice.get("pi_name"),
            "sales_person": sales_person,
            "pi_date": convertDateToProperFormat(proforma_invoice.get("created_at")),
            "destination": (
                proforma_invoice.get("destination", "N/A")
                if proforma_invoice.get("destination") is not None
                else "N/A"
            ),
            "delivery_date": (
                convertDateToProperFormat(order_data.get("delivery_date", "N/A"))
                if order_data.get("delivery_date") is not None
                else "N/A"
            ),
            "transport": (
                proforma_invoice.get("transport_info", "N/A")
                if proforma_invoice.get("transport_info") is not None
                else "N/A"
            ),
            "unloading": (
                proforma_invoice.get("unloading_info", "N/A")
                if proforma_invoice.get("unloading_info") is not None
                else "N/A"
            ),
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
            "total_cost_with_additional_cost": f"{total_cost_with_additional_cost:.2f}",
            "remarks": proforma_invoice.get("remarks", ""),
            "total_weight": f"{total_weight:.2f}",
            "total_sqft": f"{total_items_sqft:.2f}",
            "additional_costs": additional_costs_data,
            "cgst": f"{cgst:.2f}",
            "sgst": f"{sgst:.2f}",
            "is_gst": is_gst,
            "total_gst": f"{total_gst:.2f}" if is_gst else 0,
            "grand_total": f"{proforma_invoice.get('grand_total', 0):.2f}",
            "has_advanced_payment": has_advanced_payment,
            "advanced_payment_amount": advanced_payment_amount,
            "advanced_payment_notes": advanced_payment_notes,
            "balance_amount": f"{balance_amount:.2f}",
            "bank_name": company_details.get("bank_account_name"),
            "bank": company_details.get("bank_name"),
            "branch": company_details.get("branch", ""),
            "account_no": company_details.get("bank_account_no"),
            "ifsc": company_details.get("ifsc_code"),
            "terms": company_details.get("terms_and_conditions", []),
        }

        pdf_context = {"form": form_data}

        # print("pdf_context: ", pdf_context)

        pdf_bytes = createPdf(pdf_context, templates, "invoice.html")

        print("PDF generated successfully")

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": f'attachment; filename="invoice_{order_id}.pdf"',
            },
        )
    except Exception as e:
        print(e)
        return failure_response(str(e), {}, 500)
