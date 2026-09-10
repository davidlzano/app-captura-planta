"""
Capa de datos de la aplicación de captura.

Dos responsabilidades:

1. Mantener en memoria los catálogos que alimentan el autocompletado, y
   refrescarlos periódicamente sin reiniciar el servicio.
2. Registrar la producción por hora, calculándola a partir de la lectura del
   contador de la máquina.

Sobre el punto 2, que es lo menos obvio: el operario no digita cuántas
unidades produjo en la última hora, digita el número que muestra el contador
de la máquina. La producción se deriva restando lo ya registrado por ese
operario en esa orden y esa máquina durante el día.

La razón es que restar mentalmente cada hora, en planta y con prisa, es
exactamente donde se cuelan los errores. Copiar un número de una pantalla no
lo es. Y al cambiar de operario, de orden o de turno el acumulado vuelve a
cero, así que el siguiente registro se convierte en base nueva sin que nadie
tenga que indicarlo.
"""

import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

RUTA_DB = Path("planta.db")

# Cada cuánto se refrescan los catálogos desde la base.
INTERVALO_RECARGA_MIN = 60

# Serializa la sección crítica del guardado. Leer el acumulado y escribir el
# registro deben ocurrir como una sola operación: si dos inspectores guardan
# al mismo tiempo sobre la misma orden, ambos leerían el mismo acumulado y el
# segundo calcularía mal su producción.
_lock_escritura = threading.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


class GestorDatos:
    def __init__(self):
        self.ordenes: dict[str, dict] = {}
        self.eventos: dict[str, str] = {}
        self.operarios: list[dict] = []
        self.ultima_carga: datetime | None = None
        self.recargar()
        self._iniciar_recarga_automatica()

    # -------------------------------------------------------------------------
    # Catálogos
    # -------------------------------------------------------------------------

    def recargar(self) -> None:
        """
        Refresca los catálogos desde la base.

        Si la consulta falla, se conservan los datos que ya estaban en memoria.
        Una app de planta que se queda sin catálogos deja de servir por
        completo; una que trabaja con datos de hace una hora sigue siendo útil.
        """
        try:
            con = sqlite3.connect(RUTA_DB)
            con.row_factory = sqlite3.Row
            try:
                self.ordenes = {
                    r["op"]: {"cod_referencia": r["cod_referencia"], "referencia": r["referencia"]}
                    for r in con.execute(
                        "SELECT op, cod_referencia, referencia FROM ordenes WHERE activa = 1"
                    )
                }
                self.eventos = {
                    r["codigo"]: r["nombre"]
                    for r in con.execute("SELECT codigo, nombre FROM eventos")
                }
                self.operarios = [
                    {"id": r["id"], "nombre": r["nombre"]}
                    for r in con.execute("SELECT id, nombre FROM operarios ORDER BY nombre")
                ]
            finally:
                con.close()

            self.ultima_carga = datetime.now()
            logging.info(
                "Catalogos cargados: %d ordenes, %d eventos, %d operarios",
                len(self.ordenes), len(self.eventos), len(self.operarios),
            )
        except Exception as e:
            logging.error("Error al recargar catalogos: %s", e)
            if self.ultima_carga is None:
                raise

    def _iniciar_recarga_automatica(self) -> None:
        """Hilo demonio que refresca los catálogos en segundo plano."""

        def bucle():
            while True:
                threading.Event().wait(INTERVALO_RECARGA_MIN * 60)
                try:
                    self.recargar()
                except Exception as e:
                    logging.error("Fallo en recarga automatica: %s", e)

        hilo = threading.Thread(target=bucle, daemon=True)
        hilo.start()
        logging.info("Recarga automatica cada %d minutos", INTERVALO_RECARGA_MIN)

    # -------------------------------------------------------------------------
    # Consultas para el formulario
    # -------------------------------------------------------------------------

    def buscar_orden(self, op: str) -> dict:
        return self.ordenes.get(str(op).strip(), {})

    def buscar_evento(self, codigo: str) -> str:
        return self.eventos.get(str(codigo).strip(), "")

    def estado(self) -> dict:
        """Diagnóstico. Permite verificar el servicio sin entrar al servidor."""
        con = sqlite3.connect(RUTA_DB)
        try:
            total = con.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
            hoy = con.execute(
                "SELECT COUNT(*) FROM registros WHERE fecha = ?",
                (datetime.now().strftime("%Y-%m-%d"),),
            ).fetchone()[0]
        finally:
            con.close()

        return {
            "ultima_carga": self.ultima_carga.strftime("%Y-%m-%d %H:%M:%S") if self.ultima_carga else None,
            "intervalo_recarga_min": INTERVALO_RECARGA_MIN,
            "ordenes": len(self.ordenes),
            "eventos": len(self.eventos),
            "operarios": len(self.operarios),
            "registros_totales": total,
            "registros_hoy": hoy,
        }

    # -------------------------------------------------------------------------
    # Registro
    # -------------------------------------------------------------------------

    @staticmethod
    def _es_tiraje(evento: str) -> bool:
        """
        Solo los eventos de tiraje producen unidades.

        Se compara sin tildes porque el catálogo no es consistente: aparece
        tanto 'TIRAJE' como 'PRODUCCIÓN TIRAJE'.
        """
        texto = (evento or "").upper().replace("Á", "A").replace("Ó", "O")
        return "TIRAJE" in texto

    def _acumulado(self, con, op, maquina, operario_id, fecha) -> int:
        fila = con.execute(
            """
            SELECT COALESCE(SUM(cantidad), 0)
            FROM registros
            WHERE op = ? AND maquina = ? AND operario_id = ? AND fecha = ?
            """,
            (op, maquina, operario_id, fecha),
        ).fetchone()
        return int(fila[0] or 0)

    def guardar(self, datos: dict) -> dict:
        """
        Registra un evento de producción.

        Devuelve la lectura recibida y la producción calculada, para que el
        formulario pueda mostrarle al operario qué se guardó realmente. Sin esa
        devolución, quien digita una lectura de 12.400 no entiende por qué el
        historial muestra 800.
        """
        ahora = datetime.now()
        fecha = ahora.strftime("%Y-%m-%d")
        op = str(datos.get("op", "")).strip()
        maquina = str(datos.get("maquina", "")).strip().upper()
        operario_id = str(datos.get("operario_id", "")).strip()
        evento = datos.get("evento", "")

        try:
            lectura = int(datos.get("cantidad", 0) or 0)
        except (ValueError, TypeError):
            lectura = 0

        with _lock_escritura:
            con = sqlite3.connect(RUTA_DB)
            try:
                if self._es_tiraje(evento):
                    acumulado = self._acumulado(con, op, maquina, operario_id, fecha)
                    produccion = max(lectura - acumulado, 0)
                else:
                    # Paros, graduación, mantenimiento: no producen unidades.
                    produccion = 0

                orden = self.buscar_orden(op)
                con.execute(
                    """
                    INSERT INTO registros (
                        fecha, hora, maquina, op, cod_referencia, referencia,
                        cod_evento, evento, cantidad, lectura_contador,
                        operario_id, operario, observaciones
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        fecha,
                        ahora.strftime("%H:%M"),
                        maquina,
                        op,
                        orden.get("cod_referencia", ""),
                        orden.get("referencia", ""),
                        datos.get("cod_evento", ""),
                        evento,
                        produccion,
                        lectura,
                        operario_id,
                        datos.get("operario_nombre", ""),
                        datos.get("observaciones", ""),
                    ),
                )
                con.commit()
            finally:
                con.close()

        logging.info(
            "Registro | %s | OP %s | %s | lectura=%s produccion=%s",
            maquina, op, evento, lectura, produccion,
        )
        return {"lectura": lectura, "produccion": produccion}

    def historial(self, op: str, maquina: str) -> list[dict]:
        """Registros de hoy para una orden y máquina, del más reciente al más viejo."""
        con = sqlite3.connect(RUTA_DB)
        con.row_factory = sqlite3.Row
        try:
            filas = con.execute(
                """
                SELECT hora, evento, cantidad, lectura_contador, operario
                FROM registros
                WHERE op = ? AND maquina = ? AND fecha = ?
                ORDER BY hora DESC
                """,
                (op.strip(), maquina.strip().upper(), datetime.now().strftime("%Y-%m-%d")),
            ).fetchall()
        finally:
            con.close()
        return [dict(f) for f in filas]
