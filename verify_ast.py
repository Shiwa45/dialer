
import json
import ast
import logging

def _build_ice_servers_with_ast(raw_input):
    DEFAULT_STUN = {"urls": "stun:stun.l.google.com:19302"}
    result = []
    
    raw = (raw_input or '').strip()
    print(f"Input: {raw!r}")

    if raw:
        # 1. Try JSON parse
        try:
            parsed = json.loads(raw)
            print("Successfully parsed with json.loads")
        except (json.JSONDecodeError, TypeError):
            print("json.loads failed, trying ast.literal_eval")
            # 2. Try AST literal_eval (for Python list/dict syntax with single quotes)
            try:
                parsed = ast.literal_eval(raw)
                print("Successfully parsed with ast.literal_eval")
            except (ValueError, SyntaxError):
                print("ast.literal_eval failed")
                parsed = None

        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and item.get('urls'):
                    result.append(item)
                elif isinstance(item, str):
                    # Handle string items if needed (reuse existing logic)
                   pass
        elif isinstance(parsed, dict) and parsed.get('urls'):
            result.append(parsed)
            
        if not result and not parsed:
             # Fallback logic for comma-split
             pass

    # Ensure we always have at least one STUN
    has_stun = any('stun:' in str(s.get('urls', '')) for s in result)
    if not has_stun:
        result.insert(0, DEFAULT_STUN)
        
    return result

# Test Data: Single quoted Python-style list (Common copy-paste error or Python repr)
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

print("--- Testing Single Quoted Input ---")
res = _build_ice_servers_with_ast(python_repr)
print(f"Result: {json.dumps(res, indent=2)}")
