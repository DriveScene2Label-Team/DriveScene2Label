"""Atomic JSON evidence updates with bounded retries for Windows file locks."""
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4


def save_json(path,value):
    path=Path(path)
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    payload=json.dumps(value,ensure_ascii=False,indent=2)
    for attempt in range(8):
        try:
            temporary.write_text(payload,encoding='utf-8')
            os.replace(temporary,path)
            return
        except PermissionError:
            if attempt==7:
                # Keep the temporary payload as recovery evidence. Never truncate the
                # previous successful report just to bypass a destination lock.
                raise
            print(f'Evidence file lock: retry {attempt+1}/7 for {path.name}',file=sys.stderr,flush=True)
            time.sleep(min(.05*2**attempt,1.0))
