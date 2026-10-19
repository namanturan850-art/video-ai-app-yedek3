"""Run a command; if it fails, repeat the end of its output as a GitHub ::error annotation.

Usage: python scripts/ci_annotated_run.py "Title" -- command arg ...
CI logs are not always downloadable, but annotations are readable through the API.
"""
import subprocess
import sys


def main(argv):
    if len(argv) < 3 or argv[1] != '--':
        print('usage: ci_annotated_run.py TITLE -- COMMAND...', file=sys.stderr)
        return 2
    title, command = argv[0], argv[2:]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    sys.stdout.write(result.stdout)
    if result.returncode:
        tail = result.stdout.strip()[-6000:].replace('%', '%25').replace('\r', '').replace('\n', '%0A')
        print(f'::error title={title}::{tail}')
    return result.returncode


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
