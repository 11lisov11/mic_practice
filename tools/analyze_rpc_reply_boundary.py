"""Compare recorded GET reply lengths and missing responses across router captures."""
import argparse
import json
from pathlib import Path

from analyze_rpc_wire_capture import packets


def inspect_capture(folder):
    _, requests, _ = packets(folder / 'to_MCU.bin')
    _, responses, _ = packets(folder / 'from_MCU.bin')
    request_ids = [row['obj'][1] for row in requests
                   if row['obj'][0] == 0 and row['obj'][2] == 'get']
    response_bytes = {
        row['obj'][1]: row['end'] - row['start'] for row in responses
        if row['obj'][0] == 1 and isinstance(row['obj'][3], str)
        and row['obj'][3].startswith('DATA ')
    }
    aligned = []
    for index, request_id in enumerate(request_ids):
        size = response_bytes.get(request_id)
        if size is None or size % 64 != 0:
            continue
        following = request_ids[index + 1] if index + 1 < len(request_ids) else None
        aligned.append({'request_id': request_id, 'reply_wire_bytes': size,
                        'next_request_id': following,
                        'next_request_answered': (following in response_bytes
                                                  if following is not None else None)})
    return {'capture': folder.name, 'requests': len(request_ids),
            'responses': sum(request_id in response_bytes for request_id in request_ids),
            'missing_request_ids': [request_id for request_id in request_ids
                                    if request_id not in response_bytes],
            'replies_at_64_byte_boundary': aligned}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_parent', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    captures = [inspect_capture(folder) for folder in sorted(args.capture_parent.glob('stock_router_*'))
                if (folder / 'to_MCU.bin').is_file() and (folder / 'from_MCU.bin').is_file()]
    if not captures:
        parser.error('No matching captures')
    result = {'captures': captures,
              'interpretation': ('Observational correlation only. An aligned response followed by a '
                                 'successful GET rules out length by itself as a sufficient cause.')}
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
