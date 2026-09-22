"""Shared list filtering before pagination; same semantics as the Web V2 filters."""
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

VN = ZoneInfo('Asia/Ho_Chi_Minh')


def normalize(value):
    value = unicodedata.normalize('NFD', str(value or '').lower().replace('đ','d'))
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^\w]+',' ',value,flags=re.UNICODE).split())


def phrase(field, query):
    terms = normalize(query).split()
    if not terms:
        return True
    words = normalize(field).split()
    return any(all(start+i < len(words) and (words[start+i].startswith(term) if i == len(terms)-1 else words[start+i] == term) for i,term in enumerate(terms)) for start in range(len(words)))


def customer_matches(row, query):
    value = re.sub(r'[+(]*\d(?:[\d\s().-]*\d)?\)*', lambda m: re.sub(r'\D','',m.group()), str(query or ''))
    terms = normalize(value).split()
    phone = re.sub(r'\D','',str(row.get('phone') or row.get('customer_phone') or ''))
    local = lambda value: '0'+value[2:] if re.fullmatch(r'84\d{9}',value) else value
    return phrase(row.get('name') or row.get('customer_name'), ' '.join(t for t in terms if not t.isdigit())) and all(term in phone or local(term) in local(phone) for term in terms if term.isdigit())


def invoice_numbers(row):
    if isinstance(row,list):
        return [number for item in row for number in invoice_numbers(item)]
    if not isinstance(row,dict):
        return []
    return [row.get('bill_no',''), *row.get('bill_numbers',[]), *[number for key in ('before','after','invoice','pending','payload') for number in invoice_numbers(row.get(key))]]


def matches(row, *, date_from='', date_to='', employee='', customer='', service='', bill_no='', history=False):
    if history:
        row = {**row, 'effective_at':row.get('effective_at') or row.get('at') or row.get('created_at') or row.get('timestamp'),
               'customer_name':row.get('customer_name') or (row.get('before') or {}).get('name') or (row.get('after') or {}).get('name'),
               'entries':[{'employee_name':row.get('employee_name') or row.get('actor'), 'service':row.get('service') or row.get('action') or row.get('event_type')}]}
    if bill_no and not any(bill_no.strip().lower() in str(number).lower() for number in invoice_numbers(row)):
        return False
    if date_from or date_to:
        raw = row.get('effective_at') or row.get('booked_at') or row.get('created_at') or row.get('business_date')
        try:
            moment = datetime.fromisoformat(str(raw).replace('Z','+00:00'))
            day = (moment.replace(tzinfo=VN) if moment.tzinfo is None else moment.astimezone(VN)).date().isoformat()
        except (ValueError,TypeError):
            return False
        if date_from and day < date_from or date_to and day > date_to:
            return False
    if customer and not customer_matches(row,customer):
        return False
    return any(phrase(entry.get('employee_name'),employee) and phrase(entry.get('service'),service) for entry in row.get('entries') or [row])
