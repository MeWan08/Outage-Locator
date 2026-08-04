import datetime, time, requests

API = 'http://127.0.0.1:8000'
time.sleep(5)

# Step 1: Create scheduled outage FIRST
now = datetime.datetime.now(datetime.timezone.utc)
end = now + datetime.timedelta(minutes=20)
res = requests.post(f'{API}/api/simulator/scheduled-outages', json={
    'scope': 'dt', 'target_id': 'D-0012',
    'start': now.isoformat(), 'end': end.isoformat()
})
print('1. Scheduled Outage created:', res.text)

time.sleep(2)

# Step 2: Inject fault
res = requests.post(f'{API}/api/simulator/fault', json={
    'kind': 'dt', 'dt_id': 'D-0012', 'silent_failure': False
})
print('2. Fault injected:', res.json()['dt_id'])

# Wait for detection loop to run
for wait in [5, 10, 15]:
    time.sleep(5)
    res = requests.get(f'{API}/api/incidents')
    incidents = res.json()
    d12 = [i for i in incidents if i.get('dt_id') == 'D-0012']
    print(f'3. After {wait}s: D-0012 incidents visible in list: {len(d12)}')
    for i in d12:
        inc_id = i["id"]
        inc_status = i["status"]
        print(f'   {inc_id} status={inc_status}')

# Also check via status filter
res = requests.get(f'{API}/api/incidents?status=suppressed_scheduled')
suppressed = [i for i in res.json() if i.get('dt_id') == 'D-0012']
print(f'4. Suppressed D-0012 incidents: {len(suppressed)}')
for i in suppressed:
    inc_id = i["id"]
    inc_status = i["status"]
    print(f'   {inc_id} status={inc_status}')
