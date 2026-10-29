import ast, sys

files = [
    'app/main.py',
    'app/web.py',
    'app/models.py',
    'app/__init__.py',
    'app/services/ai.py',
    'app/services/automation.py',
    'app/services/contacts.py',
    'app/services/conversation.py',
    'app/services/drafts.py',
    'app/services/inbox.py',
    'app/services/storage.py',
]

errors = []
ok = []
for f in files:
    try:
        with open(f, encoding='utf-8') as fh:
            source = fh.read()
        ast.parse(source)
        ok.append(f)
    except FileNotFoundError:
        errors.append((f, 'FILE NOT FOUND'))
    except SyntaxError as e:
        errors.append((f, f'SyntaxError line {e.lineno}: {e.msg}'))

print(f'\n=== Syntax Check Results ===')
for f in ok:
    print(f'  OK   {f}')
for f, err in errors:
    print(f'  ERR  {f}: {err}')

if errors:
    print(f'\n{len(errors)} ERROR(S) FOUND')
    sys.exit(1)
else:
    print(f'\nAll {len(ok)} files OK')
