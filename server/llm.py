"""Minimal LLM client for the RaspTank.

Talks to any OpenAI-compatible ``/chat/completions`` endpoint using only the
standard library, so nothing new has to be installed on the Pi.

Settings come from the repo-root ``.env`` (or the real environment):

    LLM_BASE_URL=https://api.example.com/v1
    LLM_API_KEY=...
    LLM_MODEL=gpt-4o-mini

Usage:

    from llm import ask
    print(ask("drive forward two metres"))
"""

import json
import os
import urllib.error
import urllib.request
from tools import registry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(name, default=''):
    """Environment first, then the repo-root .env."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    try:
        with open(os.path.join(ROOT, '.env')) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(name + '='):
                    return line.split('=', 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return default


def configured():
    """True when a base URL, key and model are all present."""
    return all(_env(n) for n in ('LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL'))


def ask(prompt, system=None, timeout=30):
    """Send one prompt and return the reply text.

    Raises RuntimeError when the settings are missing or the call fails, so
    callers can show the message instead of a traceback.
    """
    base = _env('LLM_BASE_URL').rstrip('/')
    key = _env('LLM_API_KEY')
    model = _env('LLM_MODEL')
    
    print("do i have the following", base, key, model)
    
    if not (base and key and model):
        raise RuntimeError('LLM_BASE_URL, LLM_API_KEY and LLM_MODEL must be set in .env')

    messages = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt})

    body = json.dumps({
        'model': model, 
        'messages': messages,
        'tools': registry.get_schemas(),}).encode()
    
    print("sending this",json.dumps(json.loads(body.decode()), indent=4))

    
    req = urllib.request.Request(
        base + '/chat/completions',
        data=body,
        headers={'Content-Type': 'application/json','Authorization': 'Bearer ' + key},
    ) 

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
            print(json.dumps(payload, indent=4))
    except urllib.error.HTTPError as exc:        
        detail = exc.read().decode('utf-8', 'replace')[:200]
        print('LLM returned HTTP %d: %s' % (exc.code, detail))
        raise RuntimeError('LLM returned HTTP %d: %s' % (exc.code, detail)) from None
    except Exception as exc:
        print('LLM call failed: %s' % exc)        
        raise RuntimeError('LLM call failed: %s' % exc) from None

    try:
        message = payload['choices'][0]['message']
        print(json.dumps(message, indent=4))        
    except (KeyError, IndexError, TypeError):
        raise RuntimeError('unexpected LLM response: %s' % str(payload)[:200]) from None
    if message.get('tool_calls'):
        tool_calls = json.dumps(message['tool_calls'], indent=2)
        print(json.dumps(tool_calls, indent=4))        
        return tool_calls
    return json.dumps(message, indent=2)


if __name__ == '__main__':
    import sys
    print(ask(' '.join(sys.argv[1:]) or 'Say hello in five words.'))
