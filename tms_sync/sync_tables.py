"""
sync_tables.py
==============
"""

import os
from db import get_connection
from api_client import fetch_data


# ------------------------------------------------------------
# 1. CARRIER_MASTER - DONE
# ------------------------------------------------------------
def sync_carriers():
    records = fetch_data(
        os.getenv("CARRIER_ENDPOINT"),
        entityname="CarrierType",
        select_fields=[
            "Id", "divisionCode", "CarrierCode", "CarrierDescription",
            "Contact.EmailAddress", "Contact.PrimaryTelephoneNumber"
        ],
        filter_criteria=[
            {
                "name": "CarrierCode",
                "op": "In",
                "value": ["BDTEX", "DHLEX", "EKART LOGISTICS", "SAFEX"]
            }
        ]
    )

    conn = get_connection()
    cur = conn.cursor()

    for r in records:
        contact = r.get("contact", {})
        cur.execute("""
            INSERT INTO carrier_master (
                "carrierCode", "divisionCode", "carrierName",
                "emailAddress", "primaryTelephoneNumber"
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT ("carrierCode") DO UPDATE SET
                "divisionCode" = EXCLUDED."divisionCode",
                "carrierName" = EXCLUDED."carrierName",
                "emailAddress" = EXCLUDED."emailAddress",
                "primaryTelephoneNumber" = EXCLUDED."primaryTelephoneNumber"
        """, (
            r["carrierCode"], r.get("divisionCode"), r["carrierDescription"],
            contact.get("emailAddress"), contact.get("primaryTelephoneNumber")
        ))

    conn.commit()
    cur.close()
    conn.close()
    print(f"[carrier_master] synced {len(records)} records")


# ------------------------------------------------------------
# 3. CUSTOMER_MASTER - DONE. Filtered to AMAZON only, per confirmed Postman test.
# ------------------------------------------------------------
CUSTOMER_ENDPOINT = os.getenv("CUSTOMER_ENDPOINT")

def sync_customers():
    select_fields = [
        "Id",
        "divisionCode",
        "logisticsGroupCode",
        "CustomerDescription",
    ]

    filter_criteria = [
        {
            "name": "id",
            "op": "In",
            "value": ["AMAZON"]
        }
    ]

    rows = fetch_data(
        CUSTOMER_ENDPOINT,
        entityname="CustomerType",
        select_fields=select_fields,
        filter_criteria=filter_criteria,
        entity_key="entityType",
    )

    synced = 0
    for r in rows:
        customer_code = r.get("id")
        customer_name = r.get("customerDescription")
        logistics_group_code = r.get("logisticsGroupCode")
        division_code = r.get("divisionCode")

        upsert_customer(customer_code, division_code, logistics_group_code, customer_name)
        synced += 1

    print(f"[customer_master] synced {synced} records")
    return synced


def upsert_customer(customer_code, division_code, logistics_group_code, customer_name):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO customer_master ("customerCode", "divisionCode", "logisticsGroupCode", "customerName")
            VALUES (%s, %s, %s, %s)
            ON CONFLICT ("customerCode") DO UPDATE
            SET "divisionCode" = EXCLUDED."divisionCode",
                "logisticsGroupCode" = EXCLUDED."logisticsGroupCode",
                "customerName" = EXCLUDED."customerName";
            """,
            (customer_code, division_code, logistics_group_code, customer_name),
        )
    conn.commit()
    conn.close()


# ------------------------------------------------------------
# 8. VOUCHER - must run AFTER load
# ------------------------------------------------------------
VOUCHER_ENDPOINT = os.getenv("VOUCHER_ENDPOINT")
VOUCHER_CARRIERS = ["BDTEX", "SAFEX", "EKART LOGISTICS", "DHLEX"]


def upsert_voucher(voucher_id, load_id, voucher_total):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO voucher ("systemVoucherID", "systemLoadID", "voucherTotal")
            VALUES (%s, %s, %s)
            ON CONFLICT ("systemVoucherID") DO UPDATE
            SET "systemLoadID" = EXCLUDED."systemLoadID",
                "voucherTotal" = EXCLUDED."voucherTotal";
            """,
            (voucher_id, load_id, voucher_total),
        )
    conn.commit()
    conn.close()

# ------------------------------------------------------------
# 2. COMMODITY_CODE - DONE. Filtered to ELEC only, per confirmed test.
# ------------------------------------------------------------
COMMODITY_ENDPOINT = os.getenv("COMMODITY_ENDPOINT")

def sync_commodities():
    select_fields = [
        "Id",
        "CommodityCode",
        "CommodityDescription",
    ]

    filter_criteria = [
        {
            "name": "id",
            "op": "In",
            "value": ["ELEC"]
        }
    ]

    rows = fetch_data(
        COMMODITY_ENDPOINT,
        entityname="CommodityType",
        select_fields=select_fields,
        filter_criteria=filter_criteria,
        entity_key="entityType",
    )

    synced = 0
    for r in rows:
        commodity_code = r.get("commodityCode")
        commodity_description = r.get("commodityDescription")

        upsert_commodity(commodity_code, commodity_description)
        synced += 1

    print(f"[commodity_code] synced {synced} records")
    return synced


def upsert_commodity(commodity_code, commodity_description):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO commodity_code ("commodityCode", "commodityDescription")
            VALUES (%s, %s)
            ON CONFLICT ("commodityCode") DO UPDATE
            SET "commodityDescription" = EXCLUDED."commodityDescription";
            """,
            (commodity_code, commodity_description),
        )
    conn.commit()
    conn.close()

# ------------------------------------------------------------
# 4. LOCATION_MASTER - DONE. Filtered to IND_ prefix range, per confirmed test.
# ------------------------------------------------------------
LOCATION_ENDPOINT = os.getenv("LOCATION_ENDPOINT")

def sync_locations():
    select_fields = [
        "id",
        "shippingLocationCode",
        "shippingLocationDescription",
        "address.latitude",
        "address.longitude",
    ]

    condition = {
        "o": [
            {"ge": {"o": [{"name": "shippingLocationCode"}, {"value": "IND_"}]}},
            {"le": {"o": [{"name": "shippingLocationCode"}, {"value": "IND_z"}]}}
        ]
    }

    rows = fetch_data(
        LOCATION_ENDPOINT,
        entityname="ShippingLocationType",
        select_fields=select_fields,
        entity_key="entityType",
        condition=condition,
    )

    synced = 0
    for r in rows:
        location_id = r.get("id")
        location_code = r.get("shippingLocationCode")
        location_name = r.get("shippingLocationDescription")
        address = r.get("address", {})
        latitude = address.get("latitude")
        longitude = address.get("longitude")

        upsert_location(location_id, location_code, location_name, latitude, longitude)
        synced += 1

    print(f"[location_master] synced {synced} records")
    return synced


def upsert_location(location_id, location_code, location_name, latitude, longitude):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO location_master ("locationID", "locationCode", "locationName", "latitude", "longitude")
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT ("locationID") DO UPDATE
            SET "locationCode" = EXCLUDED."locationCode",
                "locationName" = EXCLUDED."locationName",
                "latitude" = EXCLUDED."latitude",
                "longitude" = EXCLUDED."longitude";
            """,
            (location_id, location_code, location_name, latitude, longitude),
        )
    conn.commit()
    conn.close()

# ------------------------------------------------------------
# 5. LOAD - DONE. Filtered to FreightTermsEnumVal + systemLoadID range, per confirmed test.
#    Must run AFTER carrier/customer/location/commodity (FK dependencies).
# ------------------------------------------------------------
LOAD_ENDPOINT = os.getenv("LOAD_ENDPOINT")

def sync_loads():
    select_fields = [
        "SystemLoadID",
        "CarrierCode",
        "FirstShippingLocationCode",
        "LastShippingLocationCode",
        "DepartureShippingLocationCode",
        "CustomerCode",
        "CommodityCode",
        "FreightTermsEnumVal",
        "TotalTotalPallets",
        "DirectDistance",
        "TotalScaledWeight",
        "TotalVolume",
    ]

    filter_criteria = [
        {
            "name": "FreightTermsEnumVal",
            "op": "In",
            "value": ["FT_NULL", "FT_COLLECT", "FT_PRE_PAID"]
        }
    ]

    condition = {
        "o": [
            {"ge": {"o": [{"name": "systemLoadID"}, {"value": "6878"}]}},
            {"le": {"o": [{"name": "systemLoadID"}, {"value": "7094"}]}}
        ]
    }

    rows = fetch_data(
        LOAD_ENDPOINT,
        entityname="LoadType",
        select_fields=select_fields,
        filter_criteria=filter_criteria,
        entity_key="entityType",
        condition=condition,
    )

    synced = 0
    for r in rows:
        system_load_id = r.get("systemLoadID")
        carrier_code = r.get("carrierCode")
        first_location = r.get("firstShippingLocationCode")
        last_location = r.get("lastShippingLocationCode")
        customer_code = r.get("customerCode")
        commodity_code = r.get("commodityCode")
        freight_terms = r.get("freightTermsEnumVal")
        total_pallets = r.get("totalTotalPallets")
        direct_distance = r.get("directDistance")
        total_scaled_weight = r.get("totalScaledWeight")
        total_volume = r.get("totalVolume")

        upsert_load(
            system_load_id, carrier_code, first_location, last_location,
            customer_code, commodity_code, freight_terms, total_pallets,
            direct_distance, total_scaled_weight, total_volume
        )
        synced += 1

    print(f"[load] synced {synced} records")
    return synced


def upsert_load(system_load_id, carrier_code, first_location, last_location,
                 customer_code, commodity_code, freight_terms, total_pallets,
                 direct_distance, total_scaled_weight, total_volume):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO load (
                "systemLoadID", "carrierCode", "firstShippingLocationCode",
                "lastShippingLocationCode", "customerCode", "commodityCode",
                "freightTermsEnumVal", "totalTotalPallets", "directDistance",
                "totalScaledWeight", "totalVolume"
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT ("systemLoadID") DO UPDATE
            SET "carrierCode" = EXCLUDED."carrierCode",
                "firstShippingLocationCode" = EXCLUDED."firstShippingLocationCode",
                "lastShippingLocationCode" = EXCLUDED."lastShippingLocationCode",
                "customerCode" = EXCLUDED."customerCode",
                "commodityCode" = EXCLUDED."commodityCode",
                "freightTermsEnumVal" = EXCLUDED."freightTermsEnumVal",
                "totalTotalPallets" = EXCLUDED."totalTotalPallets",
                "directDistance" = EXCLUDED."directDistance",
                "totalScaledWeight" = EXCLUDED."totalScaledWeight",
                "totalVolume" = EXCLUDED."totalVolume";
            """,
            (
                system_load_id, carrier_code, first_location, last_location,
                customer_code, commodity_code, freight_terms, total_pallets,
                direct_distance, total_scaled_weight, total_volume
            ),
        )
    conn.commit()
    conn.close()

# ------------------------------------------------------------
# 8. VOUCHER - DONE, CONFIRMED. Filter + condition exactly as provided:
#    CarrierCode In [BDTEX, SAFEX, EKART LOGISTICS, DHLEX]
#    SystemVoucherID BETWEEN 000000000411 AND 000000000627
#    Must run AFTER load.
# ------------------------------------------------------------
def sync_vouchers():
    select_fields = [
        "SystemVoucherID",
        "SystemLoadID",
        "TotalVoucherRatingAmount",
        "DestinationShippingLocationCode",
        "OriginShippingLocationCode",
        "freightBillNumber",
    ]

    filter_criteria = [
        {
            "name": "CarrierCode",
            "op": "In",
            "value": ["BDTEX", "SAFEX", "EKART LOGISTICS", "DHLEX"]
        }
    ]

    condition = {
        "o": [
            {"ge": {"o": [{"name": "SystemVoucherID"}, {"value": "000000000411"}]}},
            {"le": {"o": [{"name": "SystemVoucherID"}, {"value": "000000000627"}]}}
        ]
    }

    rows = fetch_data(
        VOUCHER_ENDPOINT,
        entityname="APVoucherType",
        select_fields=select_fields,
        filter_criteria=filter_criteria,
        entity_key="entityType",
        condition=condition,
    )

    synced = 0
    for r in rows:
        voucher_id = r.get("systemVoucherID")
        load_id = r.get("systemLoadID")
        voucher_total = r.get("totalVoucherRatingAmount")

        upsert_voucher(voucher_id, load_id, voucher_total)
        synced += 1

    print(f"[voucher] synced {synced} records")
    return synced

# ------------------------------------------------------------
# 6. FREIGHT_BILL - DONE. Filtered to FreightBillNumber In [FRHT-1..FRHT-16], per confirmed test.
#    Must run BEFORE freight_bill_details.
# ------------------------------------------------------------
FREIGHT_BILL_ENDPOINT = os.getenv("FREIGHT_BILL_ENDPOINT")

def sync_freight_bills():
    select_fields = [
        "FreightBillNumber",
        "InvoiceDate",
        "TotalFreighBillDetailAmount",
    ]

    filter_criteria = [
        {
            "name": "FreightBillNumber",
            "op": "In",
            "value": [
                "FRHT-1", "FRHT-2", "FRHT-3", "FRHT-4", "FRHT-5", "FRHT-6",
                "FRHT-7", "FRHT-8", "FRHT-9", "FRHT-10", "FRHT-11", "FRHT-12",
                "FRHT-13", "FRHT-14", "FRHT-15", "FRHT-16"
            ]
        }
    ]

    rows = fetch_data(
        FREIGHT_BILL_ENDPOINT,
        entityname="FreightBillType",
        select_fields=select_fields,
        filter_criteria=filter_criteria,
        entity_key="entityType",
    )

    synced = 0
    for r in rows:
        freight_bill_number = r.get("freightBillNumber")
        invoice_date = r.get("invoiceDate")
        freight_amount = r.get("totalFreighBillDetailAmount")

        upsert_freight_bill(freight_bill_number, invoice_date, freight_amount)
        synced += 1

    print(f"[freight_bill] synced {synced} records")
    return synced


def upsert_freight_bill(freight_bill_number, invoice_date, freight_amount):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO freight_bill ("freightBillNumber", "invoiceDate", "freightAmount")
            VALUES (%s, %s, %s)
            ON CONFLICT ("freightBillNumber") DO UPDATE
            SET "invoiceDate" = EXCLUDED."invoiceDate",
                "freightAmount" = EXCLUDED."freightAmount";
            """,
            (freight_bill_number, invoice_date, freight_amount),
        )
    conn.commit()
    conn.close()

# ------------------------------------------------------------
# 7. FREIGHT_BILL_DETAILS - DONE. Filtered per confirmed structure:
#    FreightBillDetailStatusEnumVal In [...], VoucherNumber BETWEEN 411-629.
#    Must run AFTER load and freight_bill.
# ------------------------------------------------------------
FREIGHT_BILL_DETAILS_ENDPOINT = os.getenv("FREIGHT_BILL_DETAILS_ENDPOINT")

def sync_freight_bill_details():
    select_fields = [
        "FreightBillDetailID",
        "FreightBillNumber",
        "UserReferenceNumber",
        "TotalAmount",
    ]

    filter_criteria = [
        {
            "name": "FreightBillDetailStatusEnumVal",
            "op": "In",
            "value": [
                "S_NULL", "S_FBD_UNMATCHED", "S_FBD_MATCHED_VARIANCE",
                "S_FBD_APPROVED", "S_FBD_CANCELED"
            ]
        }
    ]

    condition = {
        "o": [
            {"ge": {"o": [{"name": "VoucherNumber"}, {"value": "000000000411"}]}},
            {"le": {"o": [{"name": "VoucherNumber"}, {"value": "000000000629"}]}}
        ]
    }

    rows = fetch_data(
        FREIGHT_BILL_DETAILS_ENDPOINT,
        entityname="FreightBillDetailType",
        select_fields=select_fields,
        filter_criteria=filter_criteria,
        entity_key="entityType",
        condition=condition,
    )

    synced = 0
    for r in rows:
        detail_id = r.get("freightBillDetailID")
        freight_bill_number = r.get("freightBillNumber")
        user_reference_number = r.get("userReferenceNumber")
        total_amount = r.get("totalAmount")

        upsert_freight_bill_detail(detail_id, freight_bill_number, user_reference_number, total_amount)
        synced += 1

    print(f"[freight_bill_details] synced {synced} records")
    return synced


def upsert_freight_bill_detail(detail_id, freight_bill_number, user_reference_number, total_amount):
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO freight_bill_details (
                "freightBillDetailID", "freightBillNumber", "userReferenceNumber", "freightBillDetailTotal"
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT ("freightBillDetailID") DO UPDATE
            SET "freightBillNumber" = EXCLUDED."freightBillNumber",
                "userReferenceNumber" = EXCLUDED."userReferenceNumber",
                "freightBillDetailTotal" = EXCLUDED."freightBillDetailTotal";
            """,
            (detail_id, freight_bill_number, user_reference_number, total_amount),
        )
    conn.commit()
    conn.close()