import urllib.request, urllib.error
req = urllib.request.Request('http://localhost:8000/api/chat/rooms/', headers={'Origin': 'http://localhost:3000'})
try:
  urllib.request.urlopen(req)
except urllib.error.HTTPError as e:
  print(e.headers)
