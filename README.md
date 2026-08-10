# SACA · Registro de Adultos Mayores

Aplicación web en Python 3 + Flask para registrar en la corte a los adultos
mayores que llegan, leyendo automáticamente los datos de su cédula de
identidad chilena con OCR (Tesseract) a partir de una foto tomada con la
cámara web.

## Funcionalidad

- Captura de la cédula con la cámara web del navegador (no requiere subir archivos).
- Lectura automática por OCR de: apellidos, nombres, RUT y fecha de nacimiento.
- La foto capturada se muestra en pantalla junto al formulario para revisar y
  corregir los datos antes de guardar (el OCR es una ayuda, no un reemplazo
  de la revisión humana).
- Validación del dígito verificador del RUT (en el navegador y en el servidor).
- La foto del documento queda guardada y asociada al registro.
- Registro adicional de email y teléfono.
- Reporte de todos los registros, filtrable por rango de fechas.
- Exportación del reporte a Excel (.xlsx).

## Requisitos

- Python 3.10+
- Tesseract OCR instalado en el sistema, con el paquete de idioma español:

  ```bash
  # Debian/Ubuntu
  sudo apt-get install tesseract-ocr tesseract-ocr-spa
  ```

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecución

Para desarrollo (servidor de Flask):

```bash
python3 wsgi.py
```

Para producción / como servicio (Waitress, igual que el resto de S.A.C.A.):

```bash
python3 -m waitress --host=0.0.0.0 --port=5002 --threads=4 wsgi:app
```

La app queda disponible en `http://localhost:5002` (o el puerto que uses).
La captura de cámara requiere HTTPS o `localhost` (restricción de los
navegadores para `getUserMedia`); si se va a usar en otro computador de la
red, hay que servirla detrás de HTTPS.

## Estructura

```
wsgi.py              # punto de entrada WSGI (no se llama app.py para no
                      # chocar con el paquete app/ al hacer "wsgi:app")
config.py           # configuración (rutas, base de datos)
app/
  __init__.py        # app factory (Flask + SQLAlchemy)
  models.py           # modelo Registro (SQLite)
  ocr_parser.py        # OCR + parseo del formato de cédula chilena
  routes.py            # rutas: /, /ocr, /registrar, /reportes, /exportar
  templates/           # HTML (Jinja2)
  static/               # CSS y JS (captura de cámara)
  uploads/               # fotos de cédulas guardadas
instance/
  saca.db              # base de datos SQLite (se crea sola al arrancar)
```

## Notas sobre el OCR

El parser (`app/ocr_parser.py`) está ajustado al formato de la cédula de
identidad del Servicio de Registro Civil e Identificación de Chile
(`APELLIDOS`, `NOMBRES`, `RUN`, `FECHA DE NACIMIENTO`). Prueba varias
versiones preprocesadas de la foto (escala de grises, contraste, nitidez) y
combina el mejor resultado de cada campo, ya que el ángulo y la luz de cada
foto varían. Aun así, el OCR nunca es 100% preciso — por eso la pantalla de
registro siempre deja los campos editables junto a la foto capturada.

## Reportes

En `/reportes` se puede filtrar por fecha de registro y exportar el listado
completo (o filtrado) a Excel desde el mismo botón.
