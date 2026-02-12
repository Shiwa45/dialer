
import json
import html as html_mod

def _build_ice_servers(raw_input):
    print(f"Input: {raw_input!r}")
    DEFAULT_STUN = {"urls": "stun:stun.l.google.com:19302"}
    result = []
    
    raw = (raw_input or '').strip()
    raw = html_mod.unescape(raw)
    
    if raw:
        try:
            parsed = json.loads(raw)
            # Handle the case where the list items are strings that need to be parsed as JSON
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, str):
                        try:
                            # Try to parse the string item as JSON
                            item_parsed = json.loads(item)
                            if isinstance(item_parsed, dict) and item_parsed.get('urls'):
                                result.append(item_parsed)
                            elif isinstance(item_parsed, list): # Handle if it's a list inside a string
                                result.extend([x for x in item_parsed if isinstance(x, dict) and x.get('urls')])
                            else:
                                result.append({"urls": item})
                        except json.JSONDecodeError:
                            # If it's not JSON, treat it as a URL string
                             result.append({"urls": item})
                    elif isinstance(item, dict) and item.get('urls'):
                        result.append(item)
            elif isinstance(parsed, dict) and parsed.get('urls'):
                result.append(parsed)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"JSON Decode Error: {e}")
            for url in raw.split(','):
                url = url.strip()
                if url:
                    result.append({"urls": url})

    has_stun = any('stun:' in str(s.get('urls', '')) for s in result)
    if not has_stun:
        result.insert(0, DEFAULT_STUN)
        
    return result

# Reproduction using data from logs
# The log shows: [{"urls": "[   { \"urls\": \"stun:stun.l.google.com:19302\" }"}, ...]
# This suggests the input might be something like:
# '[{"urls": "[   { \\"urls\\": \\"stun:stun.l.google.com:19302\\" }"}, ...]' 
# OR it might be coming from the database in a weird format.

# Let's try to simulate the input based on the log output:
# [WebRTC] ICE Servers: [{"urls":"[   { \"urls\": \"stun:stun.l.google.com:19302\" }"},{"urls":"{     \"urls\": [       \"turn:192.168.1.60:3478?transport=udp\""},{"urls":"\"turn:192.168.1.60:3478?transport=tcp\"     ]"},{"urls":"\"username\": \"turnuser\""},{"urls":"\"cre"}]

# This output implies `ice_servers` (the result of `_build_ice_servers`) is a list of dicts where "urls" contains garbage.
# If `_build_ice_servers` returns that, then `raw` was likely parsed as JSON, but the structure was unexpected.

# Case 1: The DB field contains something that looks like JSON but is messed up.
# The user's log for "Raw ice_servers_json" shows:
# [{"urls": "[   { \"urls\": \"stun:stun.l.google.com:19302\" }"}, {"urls": "{     \"urls\": [       \"turn:192.168.1.60:3478?transport=udp\""}, ...]

# This means `_build_ice_servers` returned a list where each item is `{'urls': 'SOME_STRING'}`.
# Looking at the code:
#                     elif isinstance(item, str):
#                         result.append({"urls": item})

# So `parsed` was a list of strings!
# And those strings were:
# 1. "[   { \"urls\": \"stun:stun.l.google.com:19302\" }"
# 2. "{     \"urls\": [       \"turn:192.168.1.60:3478?transport=udp\"" 
# ...

# This happens if the DB field `ice_host` is literally:
# '["[ { ... }", "{ ... " ]'  <-- A JSON list of strings, where the strings are broken JSON fragments?

# Wait, if `ice_host` was just the string:
# [ { "urls": "stun:..." }, ... ]
# Then `json.loads` would return a list of dicts, and the code:
#                 for item in parsed:
#                     if isinstance(item, dict) and item.get('urls'):
#                         result.append(item)
# would work perfectly.

# But if `ice_host` is:
# "[   { \"urls\": \"stun:stun.l.google.com:19302\" }, ... ]"
# And it somehow got split? This is very strange.

# Let's assume the DB field contains a STRING that is verified as:
malformed_input = """
[
  "[   { \\"urls\\": \\"stun:stun.l.google.com:19302\\" }",
  "{     \\"urls\\": [       \\"turn:192.168.1.60:3478?transport=udp\\"",
  "\\"turn:192.168.1.60:3478?transport=tcp\\"     ]}",
  "\\"username\\": \\"turnuser\\"",
  "\\"credential\\": \\"turnpassword\\""
]
"""
# If the above is what's in the DB, then `json.loads` returns a list of strings.
# And `_build_ice_servers` wraps each string in `{"urls": string}`.
# That matches the log output perfectly!

print("--- REPRODUCTION ---")
result = _build_ice_servers(malformed_input)
print(f"Result: {json.dumps(result)}")

# The fix needs to be able to handle this.
# It seems like someone tried to put JSON *content* into a JSON list of strings?
# Or maybe the raw input is just a mess.

# Ideally, we want to extract valid JSON objects from this mess.
# But honestly, the input looks like a split string representation of a JSON object.
# Like `str(json_obj).split(',')` or something wild.

# IMPROVED STRATEGY:
# If the items are strings, we should try to see if they are valid JSON themselves.
# But here the strings are FRAGMENTS of JSON.
# "{\n     \"urls\": [       \"turn:192.168.1.60:3478?transport=udp\"" -> This is an open brace, not valid JSON.

# It looks like the DB content is irretrievably broken or formatted in a very specific, broken way.
# However, maybe we can assume the user actually wants to supply a standard JSON list of ice servers.

# Let's try to construct a robust parser that can handle:
# 1. Standard JSON list of dicts (Ideal)
# 2. JSON list of strings that are valid JSON (Double encoded)
# 3. Comma separated strings (Fallback)

# Since the current input produces garbage, we should just fail to parse it as "list of URLs" if it doesn't look like a URL.
# "{" is not a URL.

def _improved_build_ice_servers(phone_ice_host):
    DEFAULT_STUN = {"urls": "stun:stun.l.google.com:19302"}
    result = []
    
    raw = (phone_ice_host or '').strip()
    raw = html_mod.unescape(raw)
    
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and item.get('urls'):
                         # Valid RTCConfiguration object
                        result.append(item)
                    elif isinstance(item, str):
                        # Clean up whitespace
                        item = item.strip()
                        # Is it a double-encoded JSON object?
                        if item.startswith('{') and item.endswith('}'):
                            try:
                                nested = json.loads(item)
                                if isinstance(nested, dict) and nested.get('urls'):
                                    result.append(nested)
                                continue
                            except:
                                pass
                        
                        # Basic heuristic: A URL shouldn't start with JSON chars like { [ "
                        if not any(item.startswith(c) for c in ['{', '[', '"']):
                             result.append({"urls": item})
                             
            elif isinstance(parsed, dict) and parsed.get('urls'):
                result.append(parsed)
                
        except (json.JSONDecodeError, TypeError):
             pass

        # If JSON parsing failed or produced nothing useful, try comma-split
        # BUT only if we haven't found anything (or maybe we should mix?)
        # The original code falls back to split ONLY on JSONDecodeError.
        # Here we have a valid JSON list (of garbage strings).
        
    # If the JSON structure was "valid" but contained garbage (like our reproduction case),
    # `result` might be empty now with the improved logic (filtering out "{" strings).
    # In that case, we might want to try to treat the WHOLE raw string as comma-separated?
    # No, if it parses as JSON, we should trust it's meant to be JSON.
    
    # If result is empty after JSON attempt, and raw exists, maybe we should try naive split?
    if not result and raw:
         # Fallback: maybe it wasn't a JSON list of configs, but just a string we should split?
         # But if `json.loads` worked, it IS a JSON structure.
         pass

    # Ensure STUN
    has_stun = any('stun:' in str(s.get('urls', '')) for s in result)
    if not has_stun:
        result.insert(0, DEFAULT_STUN)
        
    return result

print("\n--- TEST IMPROVED ---")
fixed_result = _improved_build_ice_servers(malformed_input)
print(f"Fixed Result: {json.dumps(fixed_result)}")

