import tls_client


def create_tls_session(fingerprint: str = "chrome_120") -> tls_client.Session:
    session = tls_client.Session(
        client_identifier="chrome_120",
        random_tls_extension_order=True
    )
    return session
