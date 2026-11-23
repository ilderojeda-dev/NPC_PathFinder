"""Comparacion estatica por lotes con el mismo mapa, inicio y destino."""

from algoritmos_busqueda import ALGORITMOS_DISPONIBLES

class Comparacion:
    """Servicio con referencia a la aplicacion; no copia matrices ni mantiene globals."""

    def __init__(self, app):
        self.app = app

    def _buscar_progreso(self, inicio, objetivo, alg, texto):
        gen = self.app.buscar_ruta(inicio, objetivo, alg, self.app.LOTE_EXPANSIONES)
        while True:
            try:
                p = next(gen)
            except StopIteration as fin:
                return fin.value
            yield f"{texto} - {p['expandidos']:,} nodos expandidos"

    def generador_comparacion(self, inicio, destino):
        for alg in ALGORITMOS_DISPONIBLES:
            res = (yield from self._buscar_progreso(inicio, destino, alg, f'Comparando {alg}'))
            ruta = res['ruta']
            self.app.resultados_comparacion.append(dict(algoritmo=alg,
                tiempo=res['tiempo'],
                expandidos=res['expandidos'],
                nodos_ruta=None if ruta is None else len(ruta),
                estado=res['estado'],
                criterio_nodos=res.get('criterio_nodos', 'Descubiertos unicos / expandidos hacia el destino'),
                preparacion_alt_s=self.app.motor_pathfinding.alt.tiempo if 'ALT' in alg else 0.0))
        return 'Comparacion estatica terminada. Sin obstaculos dinamicos ni animacion.'

    def iniciar_comparacion(self):
        if self.app.preparacion_alt is not None or self.app.inicio_busqueda is None or self.app.destino_busqueda is None or self.app.comparando or (self.app.tarea_busqueda is not None):
            return
        self.app.estadisticas_registro.interrumpir_recorrido('Interrumpido por comparacion')
        self.app.animando = self.app.pausa_replan = False
        self.app.replan_actual = None
        self.app.navegacion.limpiar_mundo_dinamico()
        self.app.npc.ubicar_en_inicio()
        self.app.ruta_encontrada = None
        self.app.resultados_comparacion = []
        self.app.numero_comparacion += 1
        self.app.contexto_comparacion = dict(id=self.app.numero_comparacion,
            inicio=self.app.inicio_busqueda,
            destino=self.app.destino_busqueda,
            estado='En curso',
            resultados=self.app.resultados_comparacion,
            preparacion_alt_s=self.app.motor_pathfinding.alt.tiempo)
        self.app.historial_comparaciones.append(self.app.contexto_comparacion)
        if self.app.informe_ventana is not None:
            self.app.informe_ventana.indice_comparacion = len(self.app.historial_comparaciones) - 1
            self.app.informe_ventana.comparacion = True
            self.app.informe_ventana.aviso = ''
        self.app.comparando = True
        self.app.tarea_comparacion = self.generador_comparacion(self.app.inicio_busqueda,
            self.app.destino_busqueda)
        self.app.mensaje = 'Comparando busquedas sobre el mismo mapa estatico...'

    def avanzar_comparacion(self):
        if self.app.tarea_comparacion is None:
            return
        try:
            self.app.mensaje = next(self.app.tarea_comparacion)
        except StopIteration as fin:
            self.app.tarea_comparacion, self.app.comparando = (None, False)
            self.app.contexto_comparacion['estado'] = 'Terminada'
            self.app.mensaje = fin.value
            self.app.informes.abrir_informe(comparacion=True)
