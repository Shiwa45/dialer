
import json
import logging
import html as html_mod

class MockPhone:
    def __init__(self, ice_host):
        self.ice_host = ice_host

def _build_ice_servers(phone):
    DEFAULT_STUN = {"urls": "stun:stun.l.google.com:19302"}
    result = []
    
    # Simulate DB retrieval
    raw = (getattr(phone, 'ice_host', '') or '').strip()
    raw = html_mod.unescape(raw)
    
    print(f"Processing raw input: {raw!r}")

    if raw:
        # Try JSON parse first
        try:
            # SIMULATE FAILURE if the input is single-quoted JSON (common in Python repr)
            # json.loads(" [{'urls': '...'}] ") -> Fails
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and item.get('urls'):
                        result.append(item)
                    elif isinstance(item, str):
                        item = item.strip()
                        # Handling double-encoded or fragmented JSON strings
                        # Try to parse string item as JSON if it looks like an object or list
                        if (item.startswith('{') and item.endswith('}')) or (item.startswith('[') and item.endswith(']')):
                            try:
                                nested = json.loads(item)
                                if isinstance(nested, dict) and nested.get('urls'):
                                    result.append(nested)
                                elif isinstance(nested, list):
                                    for n in nested:
                                        if isinstance(n, dict) and n.get('urls'):
                                            result.append(n)
                                continue
                            except (json.JSONDecodeError, TypeError):
                                pass

                        # Fallback: treat as simple URL if it doesn't look like JSON syntax
                        if not any(item.startswith(c) for c in ['{', '[', '"']):
                            result.append({"urls": item})

            elif isinstance(parsed, dict) and parsed.get('urls'):
                result.append(parsed)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"JSON Parse Failed: {e}")
            # Not JSON — treat as comma-separated STUN/TURN URLs
            # THIS IS THE SUSPECTED CULPRIT
            for url in raw.split(','):
                url = url.strip()
                if url:
                    result.append({"urls": url})

    # Ensure we always have at least one STUN
    has_stun = any(
        'stun:' in str(s.get('urls', ''))
        for s in result
    )
    if not has_stun:
        result.insert(0, DEFAULT_STUN)
        
    return result

# 1. Test with the User's claimed valid JSON (This works)
valid_json = """
[
  { "urls": "stun:stun.l.google.com:19302" },
  {
    "urls": [
      "turn:192.168.1.60:3478?transport=udp",
      "turn:192.168.1.60:3478?transport=tcp"
    ],
    "username": "turnuser",
    "credential": "turnpass"
  }
]
"""
print("\n--- TEST 1: Valid JSON ---")
res1 = _build_ice_servers(MockPhone(valid_json))
print(f"Result 1: {json.dumps(res1)}")


# 2. Test with Python string representation (Single quotes) - Simulating DB mess
# This should consistently return DEFAULT STUN because single quotes are invalid JSON
# AND the fallback text contains braces/quotes so it should be filtered out.
python_repr = """
[
  { 'urls': 'stun:stun.l.google.com:19302' },
  {
    'urls': [
      'turn:192.168.1.60:3478?transport=udp',
      'turn:192.168.1.60:3478?transport=tcp'
    ],
    'username': 'turnuser',
    'credential': 'turnpass'
  }
]
"""
print("\n--- TEST 2: Python Repr (Single Quotes) ---")
res2 = _build_ice_servers(MockPhone(python_repr))
print(f"Result 2: {json.dumps(res2, indent=2)}")
# Expected: Full list of servers, including TURN, parsed via ast.literal_eval


# 3. Test with the user's log fragment as input
# Should also return Default STUN
trace_input = '[   { "urls": "stun:stun.l.google.com:19302" }'
print("\n--- TEST 3: Trace Input ---")
res3 = _build_ice_servers(MockPhone(trace_input))
print(f"Result 3: {json.dumps(res3)}")
