"""Uvicorn entry point for Data Agent Web GUI."""

import uvicorn


def main():
    uvicorn.run(
        "data_agent.web.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1,
    )


if __name__ == "__main__":
    main()
