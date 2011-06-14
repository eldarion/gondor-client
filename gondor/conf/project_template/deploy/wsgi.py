import os
import sys

from os.path import abspath, dirname, join

sys.path.insert(0, abspath(join(dirname(__file__), os.pardir, os.pardir)))
sys.path.insert(0, abspath(join(dirname(__file__), os.pardir)))

os.environ["DJANGO_SETTINGS_MODULE"] = "{{ project_name }}.settings"

# force settings to import now to get better feedback on Gondor when project
# is not configured correctly.
from django.conf import settings
settings._setup()

from django.core.handlers.wsgi import WSGIHandler
application = WSGIHandler()