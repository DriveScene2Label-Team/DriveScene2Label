"""Read-only AWS configuration/pricing snapshot. Billing is optional and stays local.

No resource, budget, IAM or pricing commitment is changed. Price List values are
public list prices, not the account's invoice. Calculations consume these files.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--billing', action='store_true', help='One monthly-to-yesterday Cost Explorer request; account-wide, private output')
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT / '.local/hybrid/experiments'):
        raise ValueError('Use an experiment directory under .local/hybrid/experiments')
    directory.mkdir(parents=True, exist_ok=False)
    checked = datetime.now(timezone.utc)
    manifest = {'checked_at': checked.isoformat(), 'region': 'ap-northeast-2',
                'scope': 'read-only; list prices before tax, credits, negotiated discounts; CE is account-wide', 'calls': []}

    def save(name, value):
        (directory / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

    def call(name, arguments, region='ap-northeast-2'):
        command = ['aws', *arguments, '--profile', 'ds2l-seoul', '--region', region, '--output', 'json', '--no-cli-pager']
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
        row = {'name': name, 'command': command, 'exit_code': result.returncode}
        manifest['calls'].append(row)
        save('manifest', manifest)
        if result.returncode:
            save(name, {'available': False, 'error': result.stderr.strip()})
            return None
        data = json.loads(result.stdout)
        if 'PriceList' in data:
            data['PriceList'] = [json.loads(p) if isinstance(p, str) else p for p in data['PriceList']]
        save(name, data)
        return data

    identity = call('identity-private', ['sts', 'get-caller-identity'])
    if not identity or identity['Account'] != '189750306426':
        raise ValueError('Expected project AWS account')
    configuration = call('rds-configuration', ['rds', 'describe-db-instances', '--db-instance-identifier', 'ds2l-hybrid-database', '--query',
         'DBInstances[0].{instance:DBInstanceClass,engine:Engine,version:EngineVersion,storage:StorageType,allocatedGiB:AllocatedStorage,multiAZ:MultiAZ,backupDays:BackupRetentionPeriod,status:DBInstanceStatus}'])
    if not configuration or any(configuration.get(k) != v for k, v in
            {'instance': 'db.t4g.small', 'engine': 'postgres', 'storage': 'gp3', 'multiAZ': False}.items()):
        raise ValueError('RDS configuration changed; review pricing filters before estimating')
    call('s3-current-objects', ['s3api', 'list-objects-v2', '--bucket', 'ds2l-189750306426-ap-northeast-2-data', '--query',
         '{objects:length(Contents),bytes:sum(Contents[].Size)}'])
    call('s3-all-versions', ['s3api', 'list-object-versions', '--bucket', 'ds2l-189750306426-ap-northeast-2-data', '--query',
         '{versions:length(Versions),bytes:sum(Versions[].Size),deleteMarkers:length(DeleteMarkers || `[]`)}'])

    def prices(name, service, filters):
        return call(name, ['pricing', 'get-products', '--service-code', service, '--filters',
            json.dumps([{'Type': 'TERM_MATCH', 'Field': k, 'Value': v} for k, v in filters.items()])], region='us-east-1')

    base = {'regionCode': 'ap-northeast-2'}
    prices('rds-instance-price', 'AmazonRDS', {**base, 'productFamily': 'Database Instance', 'databaseEngine': 'PostgreSQL', 'instanceType': 'db.t4g.small', 'deploymentOption': 'Single-AZ'})
    prices('rds-storage-prices', 'AmazonRDS', {**base, 'productFamily': 'Database Storage', 'databaseEngine': 'PostgreSQL', 'deploymentOption': 'Single-AZ'})
    prices('s3-standard-price', 'AmazonS3', {**base, 'productFamily': 'Storage', 'volumeType': 'Standard'})
    prices('s3-put-price', 'AmazonS3', {**base, 'group': 'S3-API-Tier1'})
    prices('s3-get-price', 'AmazonS3', {**base, 'group': 'S3-API-Tier2'})
    prices('internet-egress-prices', 'AWSDataTransfer', {'fromRegionCode': 'ap-northeast-2', 'toLocation': 'External', 'transferType': 'AWS Outbound'})
    if args.billing:
        # UTC date explicitly checked here; End is exclusive. Never extrapolate
        # an incomplete day or call account totals the cost of this application.
        start = checked.date().replace(day=1).isoformat()
        end = checked.date().isoformat()
        if start < end:
            call('billing-private', ['ce', 'get-cost-and-usage', '--time-period', f'Start={start},End={end}',
                 '--granularity', 'MONTHLY', '--metrics', 'UnblendedCost', '--group-by', 'Type=DIMENSION,Key=SERVICE',
                 '--filter', json.dumps({'Not': {'Dimensions': {'Key': 'RECORD_TYPE', 'Values': ['Credit', 'Refund']}}})], region='us-east-1')
    print(json.dumps({'directory': str(directory), 'calls': len(manifest['calls']),
                      'unavailable_calls': [c['name'] for c in manifest['calls'] if c['exit_code']]}))


if __name__ == '__main__':
    main()
