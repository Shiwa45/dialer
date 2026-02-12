
import json
import logging
import html as html_mod
from agents.views_simple import _build_ice_servers
from telephony.models import Phone

# Mock phone object
class MockPhone:
    def __init__(self, ice_host):
        self.ice_host = ice_host

# Malformed input from logs
malformed_input = json.dumps([
  "[   { \"urls\": \"stun:stun.l.google.com:19302\" }",
  "{     \"urls\": [       \"turn:192.168.1.60:3478?transport=udp\"",
  "\"turn:192.168.1.60:3478?transport=tcp\"     ]}",
  "\"username\": \"turnuser\"",
  "\"credential\": \"turnpassword\""
])

print(f"Testing with malformed input: {malformed_input}")
phone = MockPhone(malformed_input)
result = _build_ice_servers(phone)
print(f"Result: {json.dumps(result, indent=2)}")

# Verify we got valid dicts and filtered out garbage
has_valid_urls = any(isinstance(x, dict) and 'urls' in x for x in result)
print(f"Has valid URLs: {has_valid_urls}")

# Test with valid double-encoded JSON
double_encoded = json.dumps(['{"urls": "stun:test.com"}'])
print(f"\nTesting with double-encoded input: {double_encoded}")
phone_valid = MockPhone(double_encoded)
result_valid = _build_ice_servers(phone_valid)
print(f"Result: {json.dumps(result_valid, indent=2)}")

# Test with list-in-string format (e.g. '["[ { ... } ]"]')
list_in_string = json.dumps(['[ { "urls": "stun:list-in-string.com" } ]'])
print(f"\nTesting with list-in-string input: {list_in_string}")
phone_list = MockPhone(list_in_string)
result_list = _build_ice_servers(phone_list)
print(f"Result: {json.dumps(result_list, indent=2)}")

# Test with Python string representation (Single quotes) - This requires ast.literal_eval
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
print(f"\nTesting with single-quoted input: {python_repr}")
phone_repr = MockPhone(python_repr)
result_repr = _build_ice_servers(phone_repr)
print(f"Result: {json.dumps(result_repr, indent=2)}")
