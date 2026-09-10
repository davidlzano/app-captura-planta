"""
Servidor de la aplicación de captura en planta.

Escucha en 0.0.0.0 para que los dispositivos de la planta puedan entrar por la
red local. La validación vive del lado del servidor: el formulario también
valida, pero esa validación es comodidad para el usuario, no garantía.

Uso:
    python datos_demo.py    # crea planta.db con catálogos de ejemplo
    python app.py           # servidor en http://localhost:5000
"""

from pathlib import Path

from flask import Flask, jsonify, render_template, request

from data_manager import GestorDatos

app = Flask(__name__)

if not Path("planta.db").exists():
    raise SystemExit("No existe planta.db. Ejecuta primero: python datos_demo.py")

gestor = GestorDatos()

MAQUINAS = ["PEGADORA 1", "PEGADORA 2", "PEGADORA 3"]


@app.after_request
def sin_cache(respuesta):
    """
    Evita que el navegador sirva una versión vieja del formulario.

    En planta esto dejó de ser teórico: tras actualizar el formulario, los
    dispositivos seguían mostrando el anterior durante horas.
    """
    respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    respuesta.headers["Pragma"] = "no-cache"
    return respuesta


@app.route("/")
def index():
    return render_template("form.html", maquinas=MAQUINAS)


# --- Catálogos para el autocompletado ---

@app.route("/api/ordenes")
def listar_ordenes():
    return jsonify(sorted(gestor.ordenes.keys()))


@app.route("/api/eventos")
def listar_eventos():
    return jsonify([{"cod": k, "nombre": v} for k, v in sorted(gestor.eventos.items())])


@app.route("/api/operarios")
def listar_operarios():
    return jsonify(gestor.operarios)


@app.route("/api/orden")
def buscar_orden():
    return jsonify(gestor.buscar_orden(request.args.get("op", "")))


@app.route("/api/evento")
def buscar_evento():
    return jsonify({"evento": gestor.buscar_evento(request.args.get("cod", ""))})


# --- Registro ---

@app.route("/api/guardar", methods=["POST"])
def guardar():
    datos = request.get_json(silent=True) or {}

    # El formulario valida, pero el servidor no confía en el formulario.
    faltantes = [
        etiqueta
        for campo, etiqueta in [
            ("op", "orden de produccion"),
            ("maquina", "maquina"),
            ("operario_id", "operario"),
            ("cod_evento", "evento"),
        ]
        if not str(datos.get(campo, "")).strip()
    ]
    if faltantes:
        return jsonify({"error": f"Falta: {', '.join(faltantes)}"}), 400

    if str(datos["op"]).strip() not in gestor.ordenes:
        return jsonify({"error": "La orden no existe o no esta activa"}), 400

    if str(datos["maquina"]).strip().upper() not in MAQUINAS:
        return jsonify({"error": "Maquina no valida"}), 400

    resultado = gestor.guardar(datos)
    return jsonify({"status": "ok", **resultado})


@app.route("/api/historial")
def historial():
    return jsonify(
        gestor.historial(request.args.get("op", ""), request.args.get("maquina", ""))
    )


# --- Diagnóstico ---

@app.route("/api/estado")
def estado():
    """Permite verificar el servicio sin entrar al servidor."""
    return jsonify(gestor.estado())


@app.route("/api/recargar", methods=["POST"])
def recargar():
    """Recarga manual, para cuando acaban de cambiar un catálogo."""
    try:
        gestor.recargar()
        return jsonify({"status": "ok", "info": gestor.estado()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # threaded=True permite atender a varios dispositivos a la vez; la sección
    # crítica del guardado está protegida por un lock en data_manager.
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=False)
