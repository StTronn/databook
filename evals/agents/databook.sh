#!/bin/sh
# Mounted at /usr/local/bin/databook (cc-p-t): databook from /opt/databook, leaving the task's own pandas untouched.
PYTHONPATH=/opt/databook exec python3 -c "import sys; from databook.cli import main; sys.exit(main())" "$@"
