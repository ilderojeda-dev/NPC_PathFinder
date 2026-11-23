"""Registro de sesiones, movimientos, tiempos y replanificaciones."""

from time import perf_counter, time_ns

class Estadisticas:
    """Servicio con referencia a la aplicacion; no copia matrices ni mantiene globals."""

    def __init__(self, app):
        self.app = app

    def inicializar(self):
        self.app.IDENTIFICADOR_APERTURA = str(time_ns())
        self.app.resultados_sesion = {}
        self.app.historial_sesiones = []
        self.app.historial_comparaciones = []
        self.app.resultados_comparacion = []
        self.app.contexto_comparacion = {}
        self.app.numero_comparacion = 0
        self.app.sesion = self.nueva_sesion(None)

    def nueva_sesion(self, algoritmo, origen='Animacion en vivo'):
        ses = dict(id=len(self.app.historial_sesiones) + 1,
            inicio=self.app.inicio_busqueda,
            destino=self.app.destino_busqueda,
            rutas=[],
            tipos={'roca': 0, 'arbusto': 0, 'tronco': 0},
            reloj_inicio=None,
            reloj_ultimo=None,
            reloj_fin=None,
            t_total=0.0,
            t_movimiento=0.0,
            t_detenido=0.0,
            algoritmo=algoritmo,
            origen=origen,
            semilla=self.app.cfg_semilla,
            inicial=None,
            obstaculos=0,
            sin_efecto=0,
            omitidos=0,
            retirados=0,
            replans=0,
            replans_ok=0,
            replans_fallidas=0,
            t_busqueda=0.0,
            t_replan=0.0,
            descubiertos=0,
            expandidos=0,
            t_preparacion=0.0,
            t_animacion=0.0,
            pasos=0,
            longitud_final=None,
            resultado='--',
            log=[])
        if algoritmo is not None:
            self.app.historial_sesiones.append(ses)
        return ses

    def registrar_ruta(self, ses, longitud, tiempo_busqueda):
        ses['rutas'].append(dict(longitud=longitud,
            nodos_totales=longitud + 1,
            realizados=0,
            completada=False,
            tiempo_busqueda=tiempo_busqueda))

    def nodos_recorridos_ruta(self, ruta):
        return ruta['realizados'] + 1

    def actualizar_reloj_recorrido(self):
        # El tiempo de recorrido incluye las pausas de replanificacion.
        if self.app.sesion['reloj_inicio'] is None or self.app.sesion['reloj_fin'] is not None:
            return
        ahora = perf_counter()
        intervalo = max(0.0, ahora - self.app.sesion['reloj_ultimo'])
        self.app.sesion['reloj_ultimo'] = ahora
        clave = 't_movimiento' if self.app.moviendo_npc and (not self.app.pausa_replan) and (not self.app.encuadrando_npc) else 't_detenido'
        self.app.sesion[clave] += intervalo
        self.app.sesion['t_total'] = ahora - self.app.sesion['reloj_inicio']

    def cerrar_recorrido(self, resultado):
        self.actualizar_reloj_recorrido()
        if self.app.sesion['reloj_inicio'] is not None and self.app.sesion['reloj_fin'] is None:
            self.app.sesion['reloj_fin'] = self.app.sesion['reloj_ultimo']
        self.app.sesion['resultado'] = resultado

    def interrumpir_recorrido(self, motivo):
        if self.app.sesion['reloj_inicio'] is not None and self.app.sesion['reloj_fin'] is None:
            self.cerrar_recorrido(motivo)

    def registrar_inicial(self, ses, res, longitud):
        ses['inicial'] = dict(tiempo=res['tiempo'],
            descubiertos=res['descubiertos'],
            expandidos=res['expandidos'],
            longitud=longitud)
        ses['t_busqueda'] = res['tiempo']
        ses['descubiertos'] = res['descubiertos']
        ses['expandidos'] = res['expandidos']
        ses['longitud_final'] = longitud
        ses['resultado'] = res.get('estado', 'Ruta encontrada')
        if longitud is not None:
            self.registrar_ruta(ses, longitud, res['tiempo'])

    def acumular_replan(self, ses, res, exito):
        ses['replans'] += 1
        ses['replans_ok' if exito else 'replans_fallidas'] += 1
        ses['t_busqueda'] += res['tiempo']
        ses['t_replan'] += res['tiempo']
        ses['descubiertos'] += res['descubiertos']
        ses['expandidos'] += res['expandidos']
