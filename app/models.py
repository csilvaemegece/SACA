from datetime import date, datetime

from app import db


class MotivoVisita(db.Model):
    __tablename__ = "motivos_visita"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False, unique=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return self.nombre


class Registro(db.Model):
    __tablename__ = "registros"

    id = db.Column(db.Integer, primary_key=True)
    nombres = db.Column(db.String(120), nullable=False)
    apellidos = db.Column(db.String(120), nullable=False)
    rut = db.Column(db.String(15), nullable=False, index=True)
    fecha_nacimiento = db.Column(db.Date, nullable=False)
    email = db.Column(db.String(120), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    foto_filename = db.Column(db.String(255), nullable=True)
    motivo_visita_id = db.Column(db.Integer, db.ForeignKey("motivos_visita.id"), nullable=True)
    fecha_registro = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    motivo = db.relationship("MotivoVisita")

    @property
    def edad(self):
        if not self.fecha_nacimiento:
            return None
        today = date.today()
        years = today.year - self.fecha_nacimiento.year
        if (today.month, today.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day):
            years -= 1
        return years

    def to_dict(self):
        return {
            "id": self.id,
            "nombres": self.nombres,
            "apellidos": self.apellidos,
            "rut": self.rut,
            "fecha_nacimiento": self.fecha_nacimiento.isoformat() if self.fecha_nacimiento else None,
            "edad": self.edad,
            "email": self.email,
            "telefono": self.telefono,
            "foto_filename": self.foto_filename,
            "motivo_visita": self.motivo.nombre if self.motivo else None,
            "fecha_registro": self.fecha_registro.isoformat() if self.fecha_registro else None,
        }
