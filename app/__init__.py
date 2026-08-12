import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()

MOTIVOS_POR_DEFECTO = [
    "Audiencia",
    "Consulta / Orientación",
    "Retiro de documentos",
    "Notificación",
    "Otro",
]


def _migrar_columna_motivo(app):
    """Agrega la columna motivo_visita_id a bases de datos ya desplegadas
    antes de esta funcionalidad -- db.create_all() no altera tablas existentes."""
    inspector = inspect(db.engine)
    if "registros" not in inspector.get_table_names():
        return
    columnas = {c["name"] for c in inspector.get_columns("registros")}
    if "motivo_visita_id" not in columnas:
        db.session.execute(text("ALTER TABLE registros ADD COLUMN motivo_visita_id INTEGER"))
        db.session.commit()


def _sembrar_motivos_por_defecto():
    from app.models import MotivoVisita

    if MotivoVisita.query.first() is not None:
        return
    for nombre in MOTIVOS_POR_DEFECTO:
        db.session.add(MotivoVisita(nombre=nombre, activo=True))
    db.session.commit()


def create_app(config_object="config.Config"):
    app = Flask(__name__)
    app.config.from_object(config_object)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "instance"), exist_ok=True)

    db.init_app(app)

    from app.routes import bp as main_bp
    app.register_blueprint(main_bp)

    with app.app_context():
        _migrar_columna_motivo(app)
        db.create_all()
        _sembrar_motivos_por_defecto()

    return app
