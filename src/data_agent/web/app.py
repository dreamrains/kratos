"""Flask app factory for Data Agent Web GUI."""

from __future__ import annotations

from pathlib import Path

from flask import Flask

from data_agent.web.agent_manager import AgentManager

MAX_UPLOAD_MB = 200


def create_app() -> Flask:
    web_dir = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(web_dir / "templates"),
        static_folder=str(web_dir / "static"),
    )

    app.config["SECRET_KEY"] = "data-agent-web"
    app.config["agent_manager"] = AgentManager()
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

    from data_agent.config import get_config
    cfg = get_config()
    app.jinja_env.globals["config"] = cfg

    from data_agent.web.blueprints.pages import pages_bp
    from data_agent.web.blueprints.chat import chat_bp
    from data_agent.web.blueprints.sessions import sessions_bp
    from data_agent.web.blueprints.uploads import uploads_bp
    from data_agent.web.blueprints.artifacts import artifacts_bp
    from data_agent.web.blueprints.objects import objects_bp
    from data_agent.web.blueprints.commands import commands_bp
    from data_agent.web.blueprints.tasks import tasks_bp
    from data_agent.web.blueprints.capabilities import capabilities_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(chat_bp, url_prefix="/api")
    app.register_blueprint(sessions_bp, url_prefix="/api")
    app.register_blueprint(uploads_bp, url_prefix="/api")
    app.register_blueprint(artifacts_bp, url_prefix="/api")
    app.register_blueprint(objects_bp, url_prefix="/api")
    app.register_blueprint(commands_bp, url_prefix="/api")
    app.register_blueprint(tasks_bp, url_prefix="/api")
    app.register_blueprint(capabilities_bp, url_prefix="/api")

    @app.errorhandler(413)
    def request_entity_too_large(e):
        from flask import jsonify
        return jsonify({"error": f"File too large. Maximum size: {MAX_UPLOAD_MB}MB"}), 413

    return app
