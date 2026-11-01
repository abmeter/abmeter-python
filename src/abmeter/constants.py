"""SDK default values."""

DEFAULT_BASE_URL = "https://abmeter.ai"
DEFAULT_FLUSH_INTERVAL = 60  # seconds
DEFAULT_FETCH_INTERVAL = 60  # seconds
DEFAULT_LOG_LEVEL = "error"

BATCH_SIZE = 100
DEFAULT_SHUTDOWN_TIMEOUT = 5.0  # seconds a graceful shutdown may block
MAX_SUBMIT_ATTEMPTS = 3
MAX_RETRY_QUEUE_SIZE = 1000
DEFAULT_RETRY_AFTER = 30.0  # seconds to pause on a 429 without a usable Retry-After
MIN_RETRY_AFTER = 1.0
MAX_RETRY_AFTER = 600.0  # cap on a 429 pause: the API's rate-limit window
