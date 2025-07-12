from .constants import SUPABASE_URL, SUPABASE_ANON_KEY

from supabase import create_client, Client

supabase: Client = create_client(
    supabase_url=SUPABASE_URL, supabase_key=SUPABASE_ANON_KEY
)
