"""Read-only loopback Spring -> CLIP -> RDS search comparison, with exact response checks."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--base-url', default='http://127.0.0.1:8080')
    parser.add_argument('--dataset-id', type=int, default=21)
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('This experiment is scoped to the local backend')
    args.directory.mkdir(parents=True, exist_ok=False)
    responses, runs = {}, []
    def request(parameters):
        start = time.perf_counter()
        with urlopen(args.base_url + '/api/search/scenes?' + urlencode(parameters), timeout=45) as response:
            payload = json.load(response)
        elapsed = time.perf_counter() - start
        if not payload.get('scenes'):
            raise RuntimeError('Expected a nonempty search fixture')
        return payload, elapsed
    # Public synthetic queries, not user search history. Warmup excluded from measurements.
    for index, query in enumerate(('road with cars', 'pedestrians crossing a street', 'rainy night driving')):
        for scope in ('dataset', 'global'):
            for aggregation in ('MAX', 'AVERAGE', 'TOP_K_AVERAGE'):
                scenario = f'q{index}-{scope}-{aggregation}'
                parameters = {'q': query, 'k': 10, 'aggregation': aggregation, 'imageTopK': 3, 'keyframesOnly': 'true'}
                if scope == 'dataset':
                    parameters['datasetId'] = args.dataset_id
                request(parameters)
                for repeat in range(3):
                    payload, elapsed = request(parameters)
                    key = scenario + '-r' + str(repeat)
                    responses[key] = payload
                    entry = {'scenario': scenario, 'repeat': repeat, 'client_seconds': elapsed,
                             'scenes': len(payload['scenes']),
                             'response_sha256': hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
                    runs.append(entry)
                    with (args.directory / 'events.jsonl').open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps(entry) + '\n')
                print('Completed API scenario ' + scenario, flush=True)
    save = lambda name, value: (args.directory / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    save('responses.json', responses)
    save('runs.json', runs)
    summary = {'boundary': 'loopback HTTP Spring + CLIP HTTP/JSON + exact RDS search; warm model, sequential requests',
               'dataset_id': args.dataset_id, 'runs': len(runs), 'cache_condition': 'repeated public text; one excluded warmup per scenario',
               'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'median_seconds': {scope: statistics.median(r['client_seconds'] for r in runs if '-'+scope+'-' in r['scenario'])
                                  for scope in ('dataset', 'global')}}
    if args.reference:
        baseline = json.loads((args.reference / 'responses.json').read_text(encoding='utf-8'))
        summary['exact_responses'] = responses == baseline
        summary['reference'] = str(args.reference)
        old = json.loads((args.reference / 'summary.json').read_text(encoding='utf-8'))
        summary['reduction'] = {scope: 1-summary['median_seconds'][scope]/old['median_seconds'][scope] for scope in ('dataset', 'global')}
    save('summary.json', summary)
    if args.reference and not summary['exact_responses']:
        raise RuntimeError('Search API output equivalence failed; timings cannot authorize adoption')


if __name__ == '__main__':
    main()
