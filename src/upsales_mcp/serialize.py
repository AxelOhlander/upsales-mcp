"""Serialization utilities for converting Upsales SDK models to JSON."""

import json

# Exclude computed/noise fields that add no value for AI agents
EXCLUDE_FIELDS = {
    # SDK computed properties
    "custom_fields",
    "is_active",
    "full_name",
    "has_phone",
    "contact_count",
    "is_headquarters",
    "is_appointment",
    "has_outcome",
    "has_weblink",
    "has_attendees",
    "attendee_count",
    "is_locked",
    "expected_value",
    "is_recurring",
    "margin_percentage",
    "is_outgoing",
    "is_incoming",
    "has_error",
    "from_",
    "is_map_email",
    "has_attachments",
    "has_tracking_events",
    # Order: weighted values (= base value * probability/100, always computable)
    "weightedValue",
    "weightedOneOffValue",
    "weightedMonthlyValue",
    "weightedAnnualValue",
    "weightedContributionMargin",
    "weightedContributionMarginLocalCurrency",
    "weightedValueInMasterCurrency",
    "weightedOneOffValueInMasterCurrency",
    "weightedMonthlyValueInMasterCurrency",
    "weightedAnnualValueInMasterCurrency",
    # Order: master currency duplicates (= base value when currencyRate=1)
    "valueInMasterCurrency",
    "oneOffValueInMasterCurrency",
    "monthlyValueInMasterCurrency",
    "annualValueInMasterCurrency",
    # Order: noise fields
    "contributionMarginLocalCurrency",
    "risks",
    "salesCoach",
    "checklist",
    "titleCategories",
    "projectPlanOptions",
    "lastIntegrationStatus",
    "userSalesStatistics",
    "periodization",
    # UI permission flags
    "userEditable",
    "userRemovable",
    # Company: internal tracking
    "excludedFromProspectingMonitor",
    "isMonitored",
    "hasVisit",
    "hasMail",
    "hasForm",
    "autoMatchedProspectingId",
    "prospectingId",
    "prospectingUpdateDate",
    "prospectingCreditRating",
    "prospectingNumericCreditRating",
    "monitorChangeDate",
    # Company: low-value nested objects (all zeros/false for most accounts)
    "growth",
    "ads",
    "supportTickets",
    "scoreUpdateDate",
    # Contact: internal tracking
    "isPriority",
    "emailBounceReason",
    "mailBounces",
    "optins",
    "socialEvent",
    "connectedClients",
    # Mail: internal tracking and large fields
    "groupMailId",
    "jobId",
    "mailBodySnapshotId",
    "isMap",
    "events",
    "recipients",
    "tags",
    "template",
    "thread",
    "body",  # HTML email body, often 50K+; request explicitly via fields if needed
    # Agreement: noise fields (metadata sub-fields stripped via _nested_exclude)
    "orderValue",  # Deprecated, use value
    "contributionMarginInAgreementCurrency",
    "valueInMasterCurrency",
    "yearlyValueInMasterCurrency",
    "yearlyContributionMargin",
    "yearlyContributionMarginInAgreementCurrency",
    "purchaseCost",
    "isParent",
    "invoiceRelatedClient",
    "priceListId",
    "agreementGroupId",
    # Order/Agreement: raw custom fields — resolved inline when definitions are available,
    # excluded only as a fallback (see custom_field_defs parameter on serialize()).
    # Order: activity counters (rarely useful)
    "noCompletedAppointments",
    "noPostponedAppointments",
    "noTimesCallsNotAnswered",
    "noTimesClosingDateChanged",
    "noTimesOrderValueChanged",
}

# Keys to strip from nested objects (e.g. orderRow items, agreement metadata)
NESTED_EXCLUDE = {
    "valueInMasterCurrency",
    "monthlyValueInMasterCurrency",
    "annualValueInMasterCurrency",
    "contributionMarginLocalCurrency",
    "contributionMargin",
    "bundleFixedPrice",
    "tierQuantity",
    "sortId",
    "bundleRows",
    "custom",
    "productId",
    "purchaseCost",
    "listPrice",
    # Agreement metadata internals
    "agreementInvoiceStartdate",
    "agreementInitialInvoiceStartdate",
    "agreementRenewalDateReal",
    "agreementRenewalActivityCreated",
    "agreementNextOrderDateReal",
    "latestOrderCreationDate",
    "agreementIntervalType",
    "agreementOrderCreationTime",
    "willCreateMoreOrders",
    "noticePeriod",
    "agreementNotes",
    "orderSequenceNr",
    "latestOrderId",
    "versionNo",
    "activeVersionId",
}


def _strip_empty(d: dict) -> dict:
    """Recursively strip null/empty values and noise from dicts."""
    cleaned = {}
    for k, v in d.items():
        if v is None or v == [] or v == {} or v == "":
            continue
        if k in NESTED_EXCLUDE:
            continue
        if isinstance(v, dict):
            v = _strip_empty(v)
            if not v:
                continue
        elif isinstance(v, list):
            v = [_strip_empty(i) if isinstance(i, dict) else i for i in v]
        cleaned[k] = v
    return cleaned


def _resolve_custom_fields(raw_custom: list[dict], definitions: dict[int, dict]) -> dict:
    """Resolve raw custom field entries to a named dict.

    Returns:
        Dict keyed by field name, e.g.:
        {"Delivery Date": {"value": "2026-03-14", "fieldId": 42, "type": "Date"}}
    """
    resolved = {}
    for entry in raw_custom:
        field_id = entry.get("fieldId")
        if not field_id or field_id not in definitions:
            continue
        defn = definitions[field_id]
        # Pick the first non-None typed value (matches SDK CustomFields logic)
        value = (
            entry.get("value")
            or entry.get("valueInteger")
            or entry.get("valueDate")
            or entry.get("valueArray")
        )
        if value is None:
            continue
        resolved[defn["name"]] = {
            "value": value,
            "fieldId": field_id,
            "type": defn["type"],
        }
    return resolved


def serialize(
    obj: object,
    fields: list[str] | None = None,
    metadata: dict | None = None,
    custom_field_defs: dict[int, dict] | None = None,
) -> str:
    """Serialize a model or list of models to JSON string.

    Args:
        obj: A Pydantic model or list of models.
        fields: If provided, only include these keys in the output (plus 'id' always).
            Use 'customFields' or 'custom' to include resolved custom fields.
        metadata: If provided, wraps output in {"metadata": ..., "data": ...}.
        custom_field_defs: If provided, resolves raw custom field data to named values.
            Dict mapping fieldId -> {"name": str, "type": str, "alias": str|None}.
    """

    def _dump(item: object) -> dict:
        data = item.model_dump(
            mode="json",
            by_alias=True,
            exclude=EXCLUDE_FIELDS,
        )

        # Resolve custom fields before field selection
        raw_custom = data.pop("custom", None)
        if custom_field_defs and raw_custom:
            resolved = _resolve_custom_fields(raw_custom, custom_field_defs)
            if resolved:
                data["customFields"] = resolved
        # If no definitions available, raw 'custom' is already popped (excluded)

        if fields:
            # Support dot-notation: "orderRow.product.id" keeps top-level "orderRow"
            keep = {"id"}
            for f in fields:
                keep.add(f.split(".")[0])
            # Treat 'custom' in field list as requesting resolved 'customFields'
            if "custom" in keep:
                keep.discard("custom")
                keep.add("customFields")
            data = {k: v for k, v in data.items() if k in keep}
        data = _strip_empty(data)
        return data

    if isinstance(obj, list):
        items = [_dump(item) for item in obj]
        if metadata:
            return json.dumps({"metadata": metadata, "data": items}, indent=2, default=str)
        return json.dumps(items, indent=2, default=str)
    return json.dumps(_dump(obj), indent=2, default=str)
