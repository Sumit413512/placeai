# Register tenant-scoped Institution Admin access-request routes on the
# canonical institution router before app.app includes it.
from . import institution_access as _institution_access  # noqa: F401,E402
