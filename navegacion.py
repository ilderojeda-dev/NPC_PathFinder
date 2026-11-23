"""Coordina las busquedas por lotes, rutas y replanificaciones; no implementa algoritmos."""

from algoritmos_busqueda import MotorPathfinding
import numpy as np
from time import perf_counter
import pygame
import interfaz_pygame as ui

class Navegacion:
    """Servicio con referencia a la aplicacion; no copia matrices ni mantiene globals."""

    def __init__(self, app):
        self.app = app

    def preparar_motor(self):
        """Crear una sola vez el motor y su preparacion ALT incremental por lotes."""
        self.app.motor_pathfinding = MotorPathfinding(self.app.matriz_posiciones_validas_estatica,
            self.app.matriz_posiciones_validas)
        self.app.preparacion_alt = self.app.motor_pathfinding.preparar_alt()
        self.app.buscar_ruta = self.app.motor_pathfinding.buscar_ruta

    def inicializar(self):
        self.app.inicio_busqueda = self.app.destino_busqueda = self.app.tarea_busqueda = None
        self.app.ruta_encontrada = None
        self.app.estadisticas = {}
        self.app.animando = False
        self.app.indice_ruta = 0
        self.app.acumulado_ruta = 0.0
        self.app.mensaje = 'Selecciona el inicio con un clic y despues el destino.'
        self.app.ruta_vertices = []
        self.app.rutas_descartadas = []
        self.app.ruta_inicial = None
        self.app.ruta_np = None
        self.app.algoritmo_activo = None
        self.app.pausa_replan = False
        self.app.replan_actual = None
        self.app.pasos_desde_obstaculo = 0
        self.app.efectos_aparicion = []
        self.app.comparando = False
        self.app.tarea_comparacion = None

    def avanzar_preparacion_alt(self):
        if self.app.preparacion_alt is None:
            return
        try:
            progreso = next(self.app.preparacion_alt)
            self.app.mensaje = f"Preparando mapa ALT: landmark {progreso['landmark']}/{progreso['cantidad']} - {progreso['expandidos']:,} posiciones"
        except StopIteration:
            self.app.preparacion_alt = None
            self.app.mensaje = 'Mapa preparado. Selecciona inicio y destino, o ejecuta la busqueda.'

    def reiniciar_busqueda(self):
        self.app.estadisticas_registro.interrumpir_recorrido('Interrumpido por reinicio')
        self.app.camara.detener_seguimiento()
        if self.app.tarea_busqueda is not None:
            self.app.tarea_busqueda.close()
            self.app.sesion['resultado'] = 'Busqueda cancelada'
        if self.app.tarea_comparacion is not None:
            self.app.tarea_comparacion.close()
            self.app.contexto_comparacion['estado'] = 'Cancelada'
        self.app.tarea_comparacion, self.app.comparando = (None, False)
        self.app.pausa_replan, self.app.replan_actual = (False, None)
        self.limpiar_mundo_dinamico()
        self.app.inicio_busqueda = self.app.destino_busqueda = self.app.tarea_busqueda = None
        self.app.ruta_encontrada = self.app.ruta_inicial = self.app.ruta_np = None
        self.app.algoritmo_activo = None
        self.app.sesion = self.app.estadisticas_registro.nueva_sesion(None)
        self.app.pasos_desde_obstaculo = 0
        self.app.estadisticas = {}
        self.app.animando = self.app.moviendo_npc = False
        self.app.rastro_puntos.clear()
        self.app.mensaje = 'Selecciona el inicio con un clic y despues el destino.'

    def seleccionar_punto(self, pos):
        if self.app.tarea_busqueda is not None or self.app.animando or self.app.comparando:
            return
        nodo = self.app.camara.mouse_a_nodo(pos)
        if nodo is None:
            self.app.mensaje = 'Posicion invalida: la hitbox completa debe caber en terreno libre.'
        elif self.app.inicio_busqueda is None:
            self.app.inicio_busqueda = nodo
            self.app.npc.ubicar_en_inicio()
            self.app.mensaje = 'Inicio seleccionado. Ahora selecciona el destino.'
        elif self.app.destino_busqueda is None:
            self.app.destino_busqueda = nodo
            self.app.mensaje = 'Puntos listos. Selecciona un algoritmo y ejecuta la busqueda.'
        else:
            self.app.mensaje = 'Pulsa Reiniciar para seleccionar otros puntos.'

    def ejecutar_busqueda(self, algoritmo):
        if self.app.preparacion_alt is not None or self.app.inicio_busqueda is None or self.app.destino_busqueda is None or (self.app.tarea_busqueda is not None) or self.app.comparando:
            return
        self.app.estadisticas_registro.interrumpir_recorrido('Interrumpido por nueva busqueda')
        self.app.animando = False
        self.limpiar_mundo_dinamico()
        self.app.pausa_replan, self.app.replan_actual = (False, None)
        self.app.npc.ubicar_en_inicio()
        self.app.ruta_encontrada = self.app.ruta_inicial = self.app.ruta_np = None
        self.app.algoritmo_activo = algoritmo
        self.app.gestor_obstaculos.rng.seed(self.app.cfg_semilla)
        self.app.sesion = self.app.estadisticas_registro.nueva_sesion(algoritmo)
        self.app.resultados_sesion[algoritmo] = self.app.sesion
        self.app.estadisticas = dict(algoritmo=algoritmo,
            descubiertos=0,
            expandidos=0,
            tiempo=0.0,
            estado='Buscando')
        self.app.tarea_busqueda = self.app.buscar_ruta(self.app.inicio_busqueda,
            self.app.destino_busqueda,
            algoritmo)
        self.app.mensaje = 'Buscando... puedes mover la camara o reiniciar.'

    def avanzar_busqueda(self):
        if self.app.tarea_busqueda is None:
            return
        try:
            self.app.estadisticas.update(next(self.app.tarea_busqueda))
        except StopIteration as fin:
            resultado = fin.value
            self.app.tarea_busqueda = None
            if self.app.replan_actual is not None:
                self.finalizar_replanificacion(resultado)
                return
            ruta = resultado.pop('ruta')
            self.app.estadisticas.update(resultado)
            self.app.mensaje = self.app.estadisticas['estado']
            if ruta is not None:
                self.instalar_ruta(ruta)
                self.app.ruta_inicial = list(ruta)
                self.app.estadisticas_registro.registrar_inicial(self.app.sesion,
                    self.app.estadisticas,
                    len(ruta) - 1)
                self.app.mensaje += '. Pulsa Animar recorrido.'
            else:
                self.app.ruta_encontrada = None
                self.app.estadisticas_registro.registrar_inicial(self.app.sesion, self.app.estadisticas, None)
                self.app.sesion['resultado'] = 'Sin camino'

    def animar_recorrido(self):
        if self.app.boton_habilitado('Animar recorrido'):
            self.restaurar_escenario_inicial()
            self.app.npc.ubicar_en_inicio()
            self.app.zoom = min(self.app.zoom_maximo, max(self.app.zoom, self.app.ZOOM_SEGUIMIENTO))
            self.app.camara.actualizar_vista()
            self.app.animando = len(self.app.ruta_encontrada) > 1
            self.app.seguimiento_camara = True
            self.app.encuadrando_npc = True
            self.app.progreso_visual = 0.0
            self.app.sesion['reloj_inicio'] = self.app.sesion['reloj_ultimo'] = perf_counter()
            self.app.sesion['resultado'] = 'En recorrido'
            if not self.app.animando:
                self.app.sesion['rutas'][-1]['completada'] = True
                self.app.estadisticas_registro.cerrar_recorrido('Destino alcanzado')
            self.app.mensaje = 'Recorriendo ruta...' if self.app.animando else 'El inicio ya es el destino.'

    def dibujar_resultado(self):
        ancho = self.app.camara.ancho_linea()
        for tramo in self.app.rutas_descartadas:
            ui.polilinea(self.app.pantalla,
                self.app.camara.a_pantalla(tramo),
                (255, 150, 52),
                max(2, ancho - 1),
                grosor_borde=1)
        if self.app.ruta_encontrada is not None and self.app.ruta_vertices:
            ui.polilinea(self.app.pantalla,
                self.app.camara.a_pantalla(self.app.ruta_vertices),
                (255, 214, 64),
                ancho)
        for nodo, color, etiqueta in ((self.app.inicio_busqueda, (84, 232, 128), 'Inicio'),
            (self.app.destino_busqueda, (255, 110, 236), 'Destino')):
            if nodo is not None:
                ui.marcador(self.app.pantalla, self.app.camara.a_pantalla([nodo])[0], color, etiqueta)

    def limpiar_mundo_dinamico(self):
        cambios = self.app.gestor_obstaculos.limpiar()
        for c in cambios:
            self.app.mapa.registrar_cambio_mapa(c, rescalar=False)
        if cambios and self.app.mostrar_posiciones_validas:
            self.app.camara.actualizar_vista()
        self.app.efectos_aparicion.clear()
        self.app.rutas_descartadas.clear()

    def instalar_ruta(self, ruta):
        self.app.ruta_encontrada = ruta
        self.app.ruta_np = np.array(ruta, dtype=np.intp).reshape(-1, 2)
        self.app.ruta_vertices = self.app.npc.vertices_ortogonales(ruta)

    def restaurar_escenario_inicial(self):
        """Vuelve al mapa limpio y a la ruta inicial para poder repetir la
    animacion con las mismas condiciones (misma semilla)."""
        self.limpiar_mundo_dinamico()
        self.app.pausa_replan = False
        self.app.replan_actual = None
        self.app.pasos_desde_obstaculo = 0
        if self.app.ruta_inicial is not None:
            self.instalar_ruta(list(self.app.ruta_inicial))
        ini = self.app.sesion.get('inicial')
        if self.app.sesion['reloj_inicio'] is not None:
            nueva = self.app.estadisticas_registro.nueva_sesion(self.app.algoritmo_activo)
            if ini:
                self.app.estadisticas_registro.registrar_inicial(nueva,
                    dict(ini, estado='Ruta encontrada'),
                    ini['longitud'])
            self.app.sesion = nueva
        self.app.resultados_sesion[self.app.algoritmo_activo] = self.app.sesion
        self.app.gestor_obstaculos.rng.seed(self.app.cfg_semilla)

    def generar_obstaculo(self):
        """Hace aparecer un obstaculo durante la animacion. Devuelve True si se
    coloco. Es la unica puerta de entrada de obstaculos en vivo."""
        if self.app.tarea_busqueda is not None or self.app.comparando or (not self.app.animando) or self.app.pausa_replan or self.app.encuadrando_npc or (self.app.ruta_encontrada is None):
            return False
        t0 = perf_counter()
        npc = self.app.npc.centro_hitbox()
        obs = self.app.gestor_obstaculos.proponer(self.app.cfg_tamano,
            self.app.ruta_encontrada,
            self.app.indice_ruta,
            npc,
            self.app.destino_busqueda,
            rango=(self.app.cfg_radio_deteccion + 25, self.app.cfg_radio_deteccion + 55))
        if obs is None:
            self.app.mensaje = 'No hay un lugar valido para un obstaculo en este momento.'
            return False
        obs.paso = self.app.sesion['pasos']
        info = self.app.gestor_obstaculos.colocar(obs)
        self.app.mapa.registrar_cambio_mapa(info)
        self.app.efectos_aparicion.append(dict(obs=obs, t=0.0))
        self.app.sesion['obstaculos'] += 1
        self.app.sesion['tipos'][obs.tipo] += 1
        self.app.pasos_desde_obstaculo = 0
        bloqueado = self.app.gestor_obstaculos.ruta_bloqueada(self.app.ruta_np, self.app.indice_ruta)
        self.app.sesion['t_preparacion'] += perf_counter() - t0
        if bloqueado is None:
            self.app.sesion['sin_efecto'] += 1
            self.app.sesion['log'].append(dict(evento='sin_efecto',
                paso=self.app.sesion['pasos'],
                posicion=npc,
                obstaculo=obs.descripcion(),
                resultado='Sin efecto: la ruta sigue valida, no se recalcula'))
            self.app.mensaje = f'Obstaculo {obs.tipo} #{obs.id}: no afecta la ruta, no se recalcula.'
        else:
            self.app.mensaje = f'Aparecio {obs.tipo} #{obs.id} a {bloqueado - self.app.indice_ruta} pasos sobre la ruta. El NPC lo detectara a {self.app.cfg_radio_deteccion} px.'
        return True

    def detectar_obstaculo_cercano(self):
        """Sensor del NPC: indice del primer nodo bloqueado de la ruta dentro del
    radio de deteccion (cfg_radio_deteccion nodos por delante) o None."""
        if self.app.ruta_np is None:
            return None
        tramo = self.app.ruta_np[self.app.indice_ruta + 1:self.app.indice_ruta + self.app.cfg_radio_deteccion + 2]
        if len(tramo) == 0:
            return None
        libres = self.app.gestor_obstaculos.efectiva[tramo[:, 1], tramo[:, 0]]
        if libres.all():
            return None
        return self.app.indice_ruta + 1 + int(np.argmin(libres))

    def gestionar_deteccion(self):
        """Si el sensor ve un bloqueo cercano, pausa y replanifica desde aqui."""
        if not (self.app.animando and (not self.app.pausa_replan) and (not self.app.encuadrando_npc) and (self.app.tarea_busqueda is None) and (not self.app.comparando) and self.app.gestor_obstaculos.obstaculos):
            return
        idx = self.detectar_obstaculo_cercano()
        if idx is None:
            return
        nx, ny = self.app.ruta_encontrada[idx]
        obs = next((o for o in self.app.gestor_obstaculos.obstaculos if o.region[0] <= nx < o.region[2] and o.region[1] <= ny < o.region[3]),
            self.app.gestor_obstaculos.obstaculos[-1])
        self.iniciar_replanificacion(obs, idx)
        self.app.mensaje = f'NPC detecta {obs.tipo} #{obs.id} a {idx - self.app.indice_ruta} pasos. Pausa y replanificacion con {self.app.algoritmo_activo} desde {self.app.npc.centro_hitbox()}...'

    def iniciar_replanificacion(self, obstaculo, indice_bloqueo):
        pos = self.app.npc.centro_hitbox()
        self.app.replan_actual = dict(obstaculo=obstaculo,
            paso=self.app.sesion['pasos'],
            posicion=pos,
            bloqueado_en=indice_bloqueo,
            restante_anterior=len(self.app.ruta_encontrada) - 1 - self.app.indice_ruta,
            ruta_vieja=list(self.app.ruta_encontrada[self.app.indice_ruta:]))
        self.app.estadisticas_registro.actualizar_reloj_recorrido()
        self.app.pausa_replan = True
        self.app.moviendo_npc = False
        self.app.estadisticas.update(algoritmo=self.app.algoritmo_activo,
            descubiertos=0,
            expandidos=0,
            tiempo=0.0,
            estado='Replanificando')
        self.app.tarea_busqueda = self.app.buscar_ruta(pos,
            self.app.destino_busqueda,
            self.app.algoritmo_activo,
            self.app.LOTE_EXPANSIONES)
        self.app.mensaje = f'Obstaculo {obstaculo.tipo} #{obstaculo.id} bloquea la ruta. Pausa y replanificacion con {self.app.algoritmo_activo} desde {pos}...'

    def finalizar_replanificacion(self, resultado):
        self.app.estadisticas_registro.actualizar_reloj_recorrido()
        info = self.app.replan_actual
        self.app.replan_actual = None
        ruta = resultado.pop('ruta')
        self.app.estadisticas.update(resultado)
        exito = ruta is not None
        self.app.estadisticas_registro.acumular_replan(self.app.sesion, resultado, exito)
        entrada = dict(evento='replan',
            num=self.app.sesion['replans'],
            paso=info['paso'],
            posicion=info['posicion'],
            obstaculo=info['obstaculo'].descripcion(),
            tiempo=resultado['tiempo'],
            descubiertos=resultado['descubiertos'],
            expandidos=resultado['expandidos'],
            restante_anterior=info['restante_anterior'],
            longitud_nueva=len(ruta) - 1 if exito else None,
            resultado='')
        if exito:
            nueva = set(ruta)
            tramo = []
            for nodo in info['ruta_vieja']:
                if nodo not in nueva:
                    tramo.append(nodo)
                elif tramo:
                    self.app.rutas_descartadas.append(self.app.npc.vertices_ortogonales(tramo))
                    tramo = []
            if tramo:
                self.app.rutas_descartadas.append(self.app.npc.vertices_ortogonales(tramo))
            self.app.estadisticas_registro.registrar_ruta(self.app.sesion, len(ruta) - 1, resultado['tiempo'])
            self.instalar_ruta(ruta)
            self.app.indice_ruta = 0
            self.app.progreso_visual = 0.0
            self.app.sesion['longitud_final'] = self.app.sesion['pasos'] + len(ruta) - 1
            entrada['resultado'] = 'Ruta encontrada'
            self.app.mensaje = f"Replanificacion #{self.app.sesion['replans']} ({self.app.algoritmo_activo}): nueva ruta de {len(ruta) - 1} movimientos. Continua el recorrido."
        elif self.app.cfg_sin_ruta == 'retirar':
            self.app.mapa.registrar_cambio_mapa(self.app.gestor_obstaculos.retirar(info['obstaculo']))
            self.app.sesion['retirados'] += 1
            entrada['resultado'] = 'Sin ruta: obstaculo retirado'
            self.app.mensaje = 'Sin ruta posible con ese obstaculo: se retira y el NPC continua por la ruta anterior.'
        else:
            self.app.animando = False
            self.app.estadisticas_registro.cerrar_recorrido('Sin ruta posible: recorrido detenido')
            entrada['resultado'] = 'Sin ruta: recorrido detenido'
            self.app.mensaje = 'Sin ruta posible hasta el destino. Recorrido detenido.'
        self.app.sesion['log'].append(entrada)
        self.app.pausa_replan = False

    def gestionar_aparicion_automatica(self):
        if not (self.app.aparicion_auto and self.app.animando and (not self.app.pausa_replan) and (not self.app.encuadrando_npc) and (self.app.tarea_busqueda is None) and (not self.app.comparando)):
            return
        if self.app.sesion['obstaculos'] >= self.app.cfg_maximo or self.app.pasos_desde_obstaculo < self.app.cfg_cada_pasos:
            return
        if not self.generar_obstaculo():
            self.app.pasos_desde_obstaculo = max(0, self.app.cfg_cada_pasos - 20)

    def actualizar_efectos(self, dt):
        for e in self.app.efectos_aparicion:
            e['t'] += dt
        self.app.efectos_aparicion[:] = [e for e in self.app.efectos_aparicion if e['t'] < self.app.DURACION_EFECTO]

    def dibujar_obstaculos(self, delante):
        """delante=False: obstaculos situados 'detras' de los pies del NPC;
    delante=True: los que estan mas abajo y deben taparlo."""
        if not self.app.gestor_obstaculos.obstaculos:
            return
        pie = self.app.npc.centro_hitbox()[1] if self.app.inicio_busqueda is not None else -1
        visible = pygame.Rect(0, 0, self.app.ANCHO_VISTA, self.app.ALTO_VISTA)
        for o in self.app.gestor_obstaculos.obstaculos:
            if (o.y + o.alto > pie) != delante:
                continue
            r = self.app.camara._rect_pantalla(o.x, o.y, o.ancho, o.alto)
            if not r.colliderect(visible):
                continue
            if o.cache_tamano != r.size:
                o.cache_sprite = pygame.transform.scale(o.sprite, r.size)
                o.cache_tamano = r.size
            self.app.pantalla.blit(o.cache_sprite, r.topleft)

    def dibujar_zonas_bloqueo(self):
        """Muestra la zona inflada por la hitbox (centros de pies invalidados)."""
        if not self.app.mostrar_zonas_bloqueo:
            return
        for o in self.app.gestor_obstaculos.obstaculos:
            x0, y0, x1, y1 = o.region
            r = self.app.camara._rect_pantalla(x0, y0, x1 - x0, y1 - y0)
            velo = pygame.Surface(r.size, pygame.SRCALPHA)
            velo.fill((255, 40, 40, 60))
            self.app.pantalla.blit(velo, r.topleft)
            pygame.draw.rect(self.app.pantalla, (255, 80, 80), r, 1)
            pygame.draw.rect(self.app.pantalla, (255, 255, 255), self.app.camara._rect_pantalla(*o.huella), 1)

    def dibujar_efectos(self):
        for e in self.app.efectos_aparicion:
            o = e['obs']
            f = e['t'] / self.app.DURACION_EFECTO
            r = self.app.camara._rect_pantalla(*o.huella).inflate(int(8 + 44 * f), int(8 + 44 * f))
            color = (255, int(230 - 120 * f), 80)
            pygame.draw.rect(self.app.pantalla, color, r, 2, border_radius=8)

    def limpiar_obstaculos_manual(self):
        if self.app.boton_habilitado('Limpiar obstaculos'):
            self.limpiar_mundo_dinamico()
            self.app.mensaje = 'Obstaculos dinamicos retirados. Mapa limpio.'
