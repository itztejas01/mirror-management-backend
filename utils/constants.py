import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")


TIMESTAMP_FORMAT = "%d-%m-%Y %I:%M %p"
CURRENT_TIME = datetime.now()
SUPABASE_JWT_SECRET_KEY = os.getenv("BACKEND_SUPABASE_JWT_SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

POSTGRESQL_USER = os.getenv("POSTGRES_USER")
POSTGRESQL_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRESQL_DB = os.getenv("POSTGRES_DB")
POSTGRESQL_HOST = os.getenv("POSTGRES_HOST")
POSTGRESQL_PORT = os.getenv("POSTGRES_PORT")


class SUPABASE_TABLES:
    additional_costs_master = "additional_costs_master"
    customers = "customers"
    orders = "orders"
    order_metrics = "order_metrics"
    order_view = "order_view"
    products = "products"
    proforma_additional_costs = "proforma_additional_costs"
    proforma_invoices = "proforma_invoices"
    proforma_invoice_items = "proforma_items"
    thickness_master = "thickness_master"
    users = "users"
    company_details = "company_master"


RATE_TYPE = {
    "per_sq_mm": "MM",
    "per_sq_ft": "SQFT",
    "per_sq_m": "SQM",
    "per_sq_yd": "SQYD",
    "per_sq_in": "SQIN",
    "per_sq_cm": "SQCM",
    "per_sq_m": "SQM",
}
