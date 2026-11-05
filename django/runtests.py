"""Roda os testes do pacote: python runtests.py"""
import os
import shutil
import sys
from pathlib import Path

import django
from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    django.setup()
    try:
        falhas = get_runner(settings)().run_tests(sys.argv[1:] or ["tests"])
    finally:
        shutil.rmtree(settings.APP_UPDATE_GUARD["FILES_ROOT"], ignore_errors=True)
    sys.exit(bool(falhas))
