import sqlite3
from types import SimpleNamespace

import pytest

from app import models
from app.db import get_db
from app.permissions import (STATUSES_FOR_TESTS, available_transitions, can_assign,
                             check_transition) if False else (None,)  # placeholder removed below
