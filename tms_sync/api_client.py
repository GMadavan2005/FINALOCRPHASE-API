"""
api_client.py
=============
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("TMS_API_BASE_URL")
LOGIN_PATH = os.getenv("TMS_LOGIN_PATH")
USERNAME = os.getenv("TMS_API_USERNAME")
PASSWORD = os.getenv("TMS_API_PASSWORD")
PAGE_SIZE = 100


def get_token():
    response = requests.get(BASE_URL + LOGIN_PATH, auth=(USERNAME, PASSWORD))
    response.raise_for_status()
    return response.json()["value"]


def fetch_data(endpoint_path, entityname, select_fields, filter_criteria=None, entity_key="entityname", condition=None):
    all_records = []
    start_row = 0

    while True:
        token = get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {
            entity_key: entityname,
            "select": {"name": select_fields},
            "page": {"startAtRow": start_row, "maxRows": PAGE_SIZE},
        }
        if filter_criteria:
            body["filter"] = filter_criteria
        if condition:
            body["condition"] = condition

        response = requests.post(BASE_URL + endpoint_path, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()

        page_info = payload.get("page", {})
        records = payload.get("data", [])
        all_records.extend(records)

        total_row_count = int(page_info.get("totalRowCount", len(all_records)))
        if len(all_records) >= total_row_count or not records:
            break
        start_row += PAGE_SIZE

    return all_records
