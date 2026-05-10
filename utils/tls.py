from curl_cffi import requests as curl_requests

def create_tls_session():
    session = curl_requests.Session(impersonate="chrome120")
    return session
