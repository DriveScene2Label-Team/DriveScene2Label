"""Deterministic, bounded scenarios from captured AWS list prices, never an invoice."""
import argparse
from decimal import Decimal
import json
from pathlib import Path

GIB = 1024 ** 3
ARCHIVE_BYTES = 4168148189
PART_BYTES = 16 * 1024 ** 2


def calculate(prices, storage_gib, version_bytes, archive_bytes=ARCHIVE_BYTES):
    """Rates are USD per hour, GB-month, request and GB as recorded by Price List."""
    rates = {k: Decimal(str(v)) for k, v in prices.items()}
    size = Decimal(archive_bytes) / GIB
    parts = (archive_bytes + PART_BYTES - 1) // PART_BYTES
    put_count = parts + 2  # Create, UploadPart per part, Complete; retries excluded.
    rds_storage = Decimal(storage_gib) * rates['rds_gp3']
    s3_storage = Decimal(version_bytes) / GIB * rates['s3_standard']
    scenarios = {
        'rds_730h_compute': rates['rds_instance'] * 730,
        'rds_100h_compute': rates['rds_instance'] * 100,
        'rds_provisioned_storage_month': rds_storage,
        'rds_730h_compute_and_storage': rates['rds_instance'] * 730 + rds_storage,
        's3_snapshot_storage_month': s3_storage,
        'rds_730h_and_s3_snapshot_storage_subtotal': rates['rds_instance'] * 730 + rds_storage + s3_storage,
        'one_archive_storage_month': size * rates['s3_standard'],
        'single_upload_requests': rates['s3_put'],
        'multipart_upload_requests_no_retry': rates['s3_put'] * put_count,
        'multipart_extra_requests_per_upload': rates['s3_put'] * (put_count - 1),
        'multipart_extra_requests_per_100_uploads': rates['s3_put'] * (put_count - 1) * 100,
        'one_archive_download_if_free_allowance_exhausted': size * rates['egress'] + rates['s3_get'],
        '100_archive_downloads_with_100GiB_free_remaining': max(Decimal(0), size * 100 - 100) * rates['egress'] + rates['s3_get'] * 100,
        '100_archive_downloads_with_no_free_remaining': size * 100 * rates['egress'] + rates['s3_get'] * 100,
    }
    # This small scenario calculator deliberately does not extrapolate into later
    # price tiers, include multipart retries, or infer account-wide free allowance.
    if Decimal(version_bytes) / GIB >= 51200 or size * 100 > 10240:
        raise ValueError('Scenario exceeds the selected first pricing tier')
    return {'currency': 'USD', 'monthly_hours_assumption': 730,
            'archive_bytes': archive_bytes, 'archive_GiB': str(size),
            'multipart_parts': parts, 'multipart_put_class_requests_no_retry': put_count,
            'snapshot_storage_GiB': str(Decimal(version_bytes) / GIB),
            'rates': {k: str(v) for k, v in rates.items()},
            'scenarios': {k: str(v) for k, v in scenarios.items()},
            'excluded': ['tax, credits, negotiated discounts', 'RDS CPU burst credits, extra backup storage, RDS network transfer',
                         'public IPv4 and other AWS resources', 'Vercel, Cognito, local electricity/hardware',
                         'S3 retries, incomplete parts, object growth after snapshot'],
            'not_an_invoice': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    root = args.directory
    def read(name): return json.loads((root / (name + '.json')).read_text(encoding='utf-8'))
    specs = {
        'rds_instance': ('rds-instance-price', 'APN2-InstanceUsage:db.t4g.small', 'Hrs'),
        'rds_gp3': ('rds-storage-prices', 'APN2-RDS:GP3-Storage', 'GB-Mo'),
        's3_standard': ('s3-standard-price', 'APN2-TimedStorage-ByteHrs', 'GB-Mo'),
        's3_put': ('s3-put-price', 'APN2-Requests-Tier1', 'Requests'),
        's3_get': ('s3-get-price', 'APN2-Requests-Tier2', 'Requests'),
        'egress': ('internet-egress-prices', 'APN2-DataTransfer-Out-Bytes', 'GB'),
    }
    selected = {}
    for key, (file, usage, unit) in specs.items():
        products = [p for p in read(file)['PriceList'] if p['product']['attributes']['usagetype'] == usage]
        if len(products) != 1:
            raise ValueError('Expected exactly one standard SKU for ' + key)
        product = products[0]
        dimensions = [(term, d) for term in product['terms']['OnDemand'].values() for d in term['priceDimensions'].values()
                      if d['unit'] == unit and Decimal(d['beginRange']) == 0]
        if len(dimensions) != 1:
            raise ValueError('Ambiguous first tier for ' + key)
        term, dimension = dimensions[0]
        selected[key] = {'sku': product['product']['sku'], 'attributes': product['product']['attributes'],
                         'effective_date': term['effectiveDate'], 'dimension': dimension}
    result = calculate({k: v['dimension']['pricePerUnit']['USD'] for k, v in selected.items()},
                       read('rds-configuration')['allocatedGiB'], read('s3-all-versions')['bytes'])
    result['checked_at'] = read('manifest')['checked_at']
    for name, value in [('selected-prices', selected), ('cost-scenarios', result)]:
        (root / (name + '.json')).write_text(json.dumps(value, indent=2), encoding='utf-8')
    billing = root / 'billing-private.json'
    if billing.is_file():
        raw = read('billing-private')
        periods = []
        for period in raw.get('ResultsByTime', []):
            amounts = [Decimal(g['Metrics']['UnblendedCost']['Amount']) for g in period['Groups']]
            units = {g['Metrics']['UnblendedCost']['Unit'] for g in period['Groups']}
            if units != {'USD'}: raise ValueError('Unexpected mixed billing currencies')
            periods.append({'period': period['TimePeriod'], 'estimated': period['Estimated'],
                            'services': len(amounts), 'account_total_excluding_credits_refunds_USD': str(sum(amounts))})
        (root / 'billing-summary-private.json').write_text(json.dumps({'scope': 'whole account, not this application; not net invoice', 'periods': periods}, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
