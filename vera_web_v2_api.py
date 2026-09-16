"""VERA SPA Web V2 Python API.

This service is the server-side write boundary for the React/Web V2 pilot.
The browser never writes leave_records directly.  The API validates the
Supabase session, resolves the mapped VERA employee, derives leave days and
penalty from the canonical LoaiNghi policy, applies the same safety invariants
used by the Streamlit leave registration flow, writes PostgreSQL with a
record_uid, and mirrors the row to the legacy MainData Google Sheet.

The API deliberately fails closed when policy data is missing or a rule cannot
be interpreted.  That is safer than allowing Web V2 to bypass a legacy rule.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import hmac
import logging
from io import BytesIO
import json
import math
import os
import re
import threading
import time
import unicodedata
import uuid
from typing import Any
from urllib.parse import quote

import gspread
import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.utils.datetime import from_excel
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field