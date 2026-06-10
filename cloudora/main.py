import uvicorn
import logging
from .api import api
from . import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def main():
    uvicorn.run(
        "cloudora.api:api",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        workers=1,
        log_level="info",
    )


if __name__ == "__main__":
    main()
