# Deck-Level Unbound Loads Cross-Referencing

## Problem

`get_unbound_compartment` returns **all** unbound loads across **all** decks, with no `deck_id` filter parameter. When the user asks "查甲板4中没有绑定舱室的负载", you cannot directly filter by deck.

## Solution: Cross-Reference Two Datasets

```python
from hermes_tools import terminal
import json

# Step 1: Get all loads on a specific deck
r1 = terminal('python3 /path/to/tool_dispatcher.py --tool get_loads '
              '--params \'{"deck_id":"DECK 4","compartment_id":""}\'')
deck_loads = json.loads(r1['output'])['data']
deck_ids = {l['load_id'] for l in deck_loads}

# Step 2: Get all unbound loads (for a system type)
r2 = terminal('python3 /path/to/tool_dispatcher.py --tool get_unbound_compartment '
              '--params \'{"system_type":"secondary"}\'')
unbound = json.loads(r2['output'])['data']
unbound_ids = {l['load_id'] for l in unbound['loads']}

# Step 3: Intersect — which unbound loads are on this deck?
deck_unbound = [l for l in deck_loads if l['load_id'] in unbound_ids]
deck_bound   = [l for l in deck_loads if l['load_id'] not in unbound_ids]
```

## Alternative: Query Each Unbound Load Detail

If the total unbound list is small (< 20), loop `get_load_detail` on each and check `compartment_name`:

```python
for ld in unbound['loads']:
    r = terminal(f'python3 ... --tool get_load_detail --params \'{{"load_id":"{ld}"}}\'')
    detail = json.loads(r['output'])['data']
    if detail.get('deck_name') == 'DECK_4_heremes_test':
        print(f"{ld} is on DECK 4")
```

## Performance Note

The cross-reference approach (step 1+2+3) is **much faster** than querying each unbound load individually when the unbound list is large (50+ items). It needs only 2 API calls + set intersection in Python.
