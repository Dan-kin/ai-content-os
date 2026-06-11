"""Network helpers with macOS Python certificate compatibility."""
import ssl
import urllib.request


def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def urlopen(request, timeout):
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_context()),
        _Redirect308Handler())
    return opener.open(request, timeout=timeout)


class _Redirect308Handler(urllib.request.HTTPRedirectHandler):
    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_301(req, fp, code, msg, headers)
