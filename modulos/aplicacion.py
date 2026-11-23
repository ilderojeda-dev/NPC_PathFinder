"""Inicializacion, eventos y coordinacion de NPC PathFinder. Importar no abre ventanas."""

from .algoritmos_busqueda import ALGORITMOS_DISPONIBLES
from pathlib import Path
from .obstaculos_dinamicos import TAMANOS
import os
import pygame
from . import interfaz_pygame as ui
from .mapa import Mapa
from .camara import Camara
from .npc import NPC
from .navegacion import Navegacion
from .estadisticas import Estadisticas
from .informes import Informes
from .comparacion import Comparacion
from .visualizador_subgrafo import Subgrafos

def configurar_dpi():
    os.environ.setdefault('SDL_WINDOWS_DPI_AWARENESS', 'permonitorv2')
    os.environ.setdefault('SDL_VIDEO_CENTERED', '1')
    if os.name == 'nt':
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass

class Aplicacion:
    """Coordina servicios y conserva el estado compartido de una ejecucion.

    Cada servicio recibe esta instancia explicitamente. Las matrices, las rutas
    y los historiales se comparten por referencia; no hay copias por modulo.
    Las ventanas secundarias reciben la misma instancia y los widgets reciben
    callbacks. Ningun modulo importa PathFinder ni inicia Pygame al importarse.
    """

    def __init__(self):
        self.mapa = Mapa(self)
        self.camara = Camara(self)
        self.npc = NPC(self)
        self.navegacion = Navegacion(self)
        self.estadisticas_registro = Estadisticas(self)
        self.informes = Informes(self)
        self.comparacion = Comparacion(self)
        self.visualizador_subgrafo_servicio = Subgrafos(self)
        configurar_dpi()
        self.CARPETA = Path(__file__).resolve().parents[1]
        self.CARPETA_DATOS = self.CARPETA / 'Datos_generados'
        self.CARPETA_DATOS.mkdir(exist_ok=True)
        self.RUTA_IMAGEN = self.CARPETA / 'Recursos' / 'mapa_bosque.png'
        self.RUTA_SPRITE = self.CARPETA / 'Recursos' / 'npc_aventurero.png'
        self.RUTA_MASCARA = self.CARPETA / 'Recursos' / 'mascara_obstaculos.png'
        self.ANCHO = 1200
        self.ALTO = 900
        self.ANCHO_LATERAL = ui.BarraLateral.ANCHO
        self.ANCHO_VISTA = self.ANCHO - self.ANCHO_LATERAL
        self.ALTO_VISTA = self.ALTO
        self.ANCHO_NPC = 32
        self.ALTO_NPC = 48
        self.VELOCIDAD_NPC = 150
        self.INTERVALO_ANIMACION = 0.12
        self.INTERVALO_IDLE = 0.3
        self.ANCHO_HITBOX_PIES = 15
        self.ALTO_HITBOX_PIES = 7
        self.ALPHA_UMBRAL = 10
        self.LOTE_EXPANSIONES = 2500
        self.ZOOM_SEGUIMIENTO = 2.0
        pygame.init()
        self.escritorio_ancho, self.escritorio_alto = pygame.display.get_desktop_sizes()[0]
        self.ANCHO = min(self.ANCHO, max(1, self.escritorio_ancho - 80))
        self.ALTO = min(self.ALTO, max(1, self.escritorio_alto - 100))
        self.ANCHO_VISTA, self.ALTO_VISTA = (self.ANCHO - self.ANCHO_LATERAL, self.ALTO)
        self.pantalla = pygame.display.set_mode((self.ANCHO, self.ALTO), pygame.RESIZABLE)
        pygame.display.set_caption('NPC PathFinder | Forest Navigation')
        self.fuente = ui.font(14)
        self.mapa.inicializar()
        self.npc.inicializar()
        self.camara.inicializar()
        self.visualizador_subgrafo = None
        self.ventana_principal = pygame.Window.from_display_module()
        self.ventana_principal.minimum_size = (min(640, self.ANCHO), min(400, self.ALTO))
        self.DURACION_EFECTO = 0.8
        self.informe_ventana = None
        self.navegacion.inicializar()
        self.mostrar_ayuda = False
        self.cursor_mano = False
        self.mostrar_zonas_bloqueo = False
        self.mostrar_landmarks = False
        self.aparicion_auto = False
        self.cfg_cada_pasos = 150
        self.cfg_maximo = 5
        self.cfg_tamano = 'Mixto'
        self.cfg_sin_ruta = 'retirar'
        self.cfg_semilla = self.SEMILLA_INICIAL
        self.cfg_radio_deteccion = 10
        self.estadisticas_registro.inicializar()
        self.algoritmo_seleccionado = ALGORITMOS_DISPONIBLES[0]
        self.configuracion_ventana = None
        self.barra = ui.BarraLateral(self.ANCHO_VISTA,
            self.ALTO,
            self.estado_ui,
            self.accion_interfaz,
            self.habilitado_interfaz,
            self.razon_deshabilitado)
        self.clic_inicial = None
        self.hubo_arrastre = False
        self.reloj = pygame.time.Clock()
        self.ejecutando = True
        self.arrastrando = False
        self.posicion_anterior = (0, 0)

    def ejecutar(self):
        try:
            while self.ejecutando:
                self.dt = min(self.reloj.tick(60) / 1000.0, 0.05)
                self.estadisticas_registro.actualizar_reloj_recorrido()
                self.procesar_eventos()
                self.actualizar()
                self.dibujar()
        finally:
            self.cerrar()

    def procesar_eventos(self):
        for evento in pygame.event.get():
            origen_evento = getattr(evento, 'window', None)
            id_ventana = getattr(origen_evento, 'id', origen_evento)
            if self.configuracion_ventana is not None and id_ventana == self.configuracion_ventana.ventana.id:
                if not self.configuracion_ventana.evento(evento):
                    self.configuracion_ventana = None
                continue
            if self.visualizador_subgrafo is not None and id_ventana == self.visualizador_subgrafo.ventana.id:
                if not self.visualizador_subgrafo.evento(evento):
                    self.visualizador_subgrafo = None
                continue
            if self.informe_ventana is not None and id_ventana == self.informe_ventana.ventana.id:
                if not self.informe_ventana.evento(evento):
                    self.informe_ventana = None
                continue
            if id_ventana is not None and id_ventana != self.ventana_principal.id:
                continue
            if evento.type in (pygame.WINDOWSIZECHANGED, pygame.VIDEORESIZE):
                self.camara.redimensionar_interfaz()
                continue
            if evento.type == pygame.MOUSEWHEEL and self.barra.contiene(pygame.mouse.get_pos()):
                self.barra.desplazar(-evento.y * 48)
                continue
            if evento.type == pygame.WINDOWCLOSE:
                self.ejecutando = False
                continue
            if evento.type == pygame.QUIT:
                self.ejecutando = False
            if evento.type == pygame.KEYDOWN:
                if evento.key == pygame.K_ESCAPE:
                    self.ejecutando = False
                elif evento.key == pygame.K_1:
                    self.modo = 0
                    self.modo_anterior_binario = self.modo
                    self.camara.actualizar_vista()
                elif evento.key == pygame.K_4:
                    self.modo_anterior_binario = self.modo if self.modo != 3 else self.modo_anterior_binario
                    self.modo = 3
                    self.camara.actualizar_vista()
                elif evento.key == pygame.K_g:
                    self.alternar_binaria()
                elif evento.key == pygame.K_v:
                    self.alternar_validas()
                elif evento.key == pygame.K_r and (not self.seguimiento_camara):
                    self.camara.centrar_mapa()
                elif evento.key == pygame.K_h:
                    self.alternar_hitbox()
                elif evento.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.habilitado_interfaz('ejecutar'):
                    self.navegacion.ejecutar_busqueda(self.algoritmo_seleccionado)
                elif evento.key == pygame.K_SPACE and self.habilitado_interfaz('animar'):
                    self.navegacion.animar_recorrido()
                elif evento.key == pygame.K_F1:
                    self.mostrar_ayuda = not self.mostrar_ayuda
                elif evento.key == pygame.K_q:
                    self.navegacion.generar_obstaculo()
                elif evento.key == pygame.K_p:
                    self.accion_cfg('Obstaculos auto')
                elif evento.key == pygame.K_x:
                    self.navegacion.limpiar_obstaculos_manual()
                elif evento.key == pygame.K_b:
                    self.alternar_zonas()
                elif evento.key == pygame.K_n:
                    self.accion_cfg('Semilla')
                elif evento.key == pygame.K_c and self.boton_habilitado('Comparar busquedas'):
                    self.comparacion.iniciar_comparacion()
                elif evento.key == pygame.K_i:
                    self.informes.abrir_informe()
            if evento.type == pygame.MOUSEWHEEL and (not self.seguimiento_camara) and (pygame.mouse.get_pos()[0] < self.ANCHO_VISTA):
                mouse_x, mouse_y = pygame.mouse.get_pos()
                zoom_anterior = self.zoom
                if evento.y > 0:
                    self.zoom = min(self.zoom * 1.15, self.zoom_maximo)
                else:
                    self.zoom = max(self.zoom / 1.15, self.zoom_minimo)
                factor = self.zoom / zoom_anterior
                self.desplazamiento_x = mouse_x - (mouse_x - self.desplazamiento_x) * factor
                self.desplazamiento_y = mouse_y - (mouse_y - self.desplazamiento_y) * factor
                self.camara.actualizar_vista()
            if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
                if self.barra.contiene(evento.pos):
                    self.barra.presionar(evento.pos)
                elif not self.seguimiento_camara:
                    self.clic_inicial = evento.pos
                    self.posicion_anterior = evento.pos
                    self.hubo_arrastre = False
                    self.arrastrando = True
            if evento.type == pygame.MOUSEMOTION and self.arrastrando:
                if abs(evento.pos[0] - self.clic_inicial[0]) + abs(evento.pos[1] - self.clic_inicial[1]) > 4:
                    self.hubo_arrastre = True
                if self.hubo_arrastre:
                    self.desplazamiento_x += evento.pos[0] - self.posicion_anterior[0]
                    self.desplazamiento_y += evento.pos[1] - self.posicion_anterior[1]
                    self.posicion_anterior = evento.pos
            if evento.type == pygame.MOUSEBUTTONUP and evento.button == 1:
                self.barra.soltar(evento.pos)
                if self.arrastrando and (not self.hubo_arrastre):
                    self.navegacion.seleccionar_punto(evento.pos)
                self.arrastrando = False
                self.clic_inicial = None
            if evento.type == pygame.WINDOWFOCUSLOST:
                self.arrastrando = False
                self.clic_inicial = None

    def actualizar(self):
        self.navegacion.avanzar_preparacion_alt()
        self.navegacion.avanzar_busqueda()
        self.comparacion.avanzar_comparacion()
        if not self.encuadrando_npc:
            self.npc.actualizar_npc(self.dt)
        self.navegacion.gestionar_deteccion()
        self.navegacion.gestionar_aparicion_automatica()
        self.navegacion.actualizar_efectos(self.dt)
        self.camara.actualizar_seguimiento(self.dt)
        if self.informe_ventana is not None:
            self.informe_ventana.refrescar()
        if self.configuracion_ventana is not None:
            self.configuracion_ventana.refrescar()

    def dibujar(self):
        self.pantalla.fill(ui.BG)
        self.pantalla.set_clip(pygame.Rect(0, 0, self.ANCHO_VISTA, self.ALTO_VISTA))
        self.pantalla.blit(self.mapa_escalado, (int(self.desplazamiento_x), int(self.desplazamiento_y)))
        self.navegacion.dibujar_resultado()
        self.npc.dibujar_rastro()
        self.navegacion.dibujar_zonas_bloqueo()
        self.navegacion.dibujar_obstaculos(False)
        if self.mostrar_landmarks and self.motor_pathfinding.alt.preparado:
            puntos = self.motor_pathfinding.alt.landmarks
            ui.dibujar_landmarks(self.pantalla,
                pygame.Rect(0, 0, self.ANCHO_VISTA, self.ALTO_VISTA),
                puntos, self.camara.a_pantalla(puntos))
        self.npc.dibujar_npc()
        self.navegacion.dibujar_obstaculos(True)
        self.npc.dibujar_hitbox_pies()
        self.navegacion.dibujar_efectos()
        self.pantalla.set_clip(None)
        self.dibujar_superposiciones()
        posicion_mouse = pygame.mouse.get_pos()
        self.barra.dibujar(self.pantalla, posicion_mouse, pygame.time.get_ticks())
        sobre_boton = self.barra.mano(posicion_mouse)
        if sobre_boton != self.cursor_mano:
            self.cursor_mano = sobre_boton
            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if sobre_boton else pygame.SYSTEM_CURSOR_ARROW)
            except pygame.error:
                pass
        pygame.display.flip()

    def cerrar(self):
        self.estadisticas_registro.interrumpir_recorrido('Interrumpido al cerrar')
        pygame.quit()
        ui._fonts.clear()
        self.ejecutando = False

    def ciclar(self, opciones, actual):
        return opciones[(opciones.index(actual) + 1) % len(opciones)]

    def boton_habilitado(self, nombre):
        if nombre == 'Mostrar landmarks':
            return True
        if nombre in ('Reiniciar',
            'Visualizar subgrafo',
            'Informe',
            'Obstaculos auto',
            'Zonas bloqueo',
            'Tamano',
            'Sin ruta',
            'Cada -',
            'Cada +',
            'Max -',
            'Max +',
            'Semilla',
            'Detec -',
            'Detec +'):
            return True
        if self.comparando or self.preparacion_alt is not None:
            return False
        if nombre == 'Animar recorrido':
            return self.tarea_busqueda is None and self.ruta_encontrada is not None and (not self.animando) and (self.algoritmo_activo == self.algoritmo_seleccionado)
        if nombre == 'Obstaculo ahora':
            return self.animando and self.tarea_busqueda is None and (not self.pausa_replan) and (not self.encuadrando_npc)
        if nombre == 'Limpiar obstaculos':
            return self.tarea_busqueda is None and (not self.animando) and bool(self.gestor_obstaculos.obstaculos)
        return self.inicio_busqueda is not None and self.destino_busqueda is not None and (self.tarea_busqueda is None)

    def accion_cfg(self, nombre):
        if nombre == 'Mostrar landmarks':
            self.mostrar_landmarks = not self.mostrar_landmarks
        elif nombre == 'Obstaculos auto':
            self.aparicion_auto = not self.aparicion_auto
        elif nombre == 'Zonas bloqueo':
            self.mostrar_zonas_bloqueo = not self.mostrar_zonas_bloqueo
        elif nombre == 'Sin ruta':
            self.cfg_sin_ruta = self.ciclar(('retirar', 'detener'), self.cfg_sin_ruta)
        elif nombre == 'Tamano':
            self.cfg_tamano = self.ciclar(TAMANOS, self.cfg_tamano)
        elif nombre == 'Cada -':
            self.cfg_cada_pasos = max(50, self.cfg_cada_pasos - 50)
        elif nombre == 'Cada +':
            self.cfg_cada_pasos = min(1000, self.cfg_cada_pasos + 50)
        elif nombre == 'Max -':
            self.cfg_maximo = max(1, self.cfg_maximo - 1)
        elif nombre == 'Max +':
            self.cfg_maximo = min(30, self.cfg_maximo + 1)
        elif nombre == 'Detec -':
            self.cfg_radio_deteccion = max(5, self.cfg_radio_deteccion - 5)
        elif nombre == 'Detec +':
            self.cfg_radio_deteccion = min(100, self.cfg_radio_deteccion + 5)
        elif nombre == 'Semilla':
            self.cfg_semilla += 1
            self.gestor_obstaculos.rng.seed(self.cfg_semilla)

    def alternar_binaria(self):
        if self.modo == 3:
            self.modo = self.modo_anterior_binario
        else:
            self.modo_anterior_binario = self.modo
            self.modo = 3
        self.camara.actualizar_vista()

    def alternar_validas(self):
        self.mostrar_posiciones_validas = not self.mostrar_posiciones_validas
        self.camara.actualizar_vista()

    def alternar_hitbox(self):
        self.mostrar_hitbox_pies = not self.mostrar_hitbox_pies

    def alternar_zonas(self):
        self.mostrar_zonas_bloqueo = not self.mostrar_zonas_bloqueo

    def accion_interfaz(self, nombre):
        """Despacha las acciones de la barra lateral y de la ventana de configuracion."""
        if nombre.startswith('alg:'):
            self.algoritmo_seleccionado = ALGORITMOS_DISPONIBLES[int(nombre[4:])]
        elif nombre in ('ejecutar', 'Ejecutar busqueda'):
            self.navegacion.ejecutar_busqueda(self.algoritmo_seleccionado)
        elif nombre in ('animar', 'Animar recorrido'):
            self.navegacion.animar_recorrido()
        elif nombre in ('reiniciar', 'Reiniciar'):
            self.navegacion.reiniciar_busqueda()
        elif nombre == 'auto':
            self.accion_cfg('Obstaculos auto')
        elif nombre in ('agregar', 'Obstaculo ahora'):
            self.navegacion.generar_obstaculo()
        elif nombre in ('limpiar', 'Limpiar obstaculos'):
            self.navegacion.limpiar_obstaculos_manual()
        elif nombre == 'v_binaria':
            self.alternar_binaria()
        elif nombre == 'v_validas':
            self.alternar_validas()
        elif nombre == 'v_hitbox':
            self.alternar_hitbox()
        elif nombre == 'v_zonas':
            self.alternar_zonas()
        elif nombre in ('subgrafo', 'Visualizar subgrafo'):
            self.visualizador_subgrafo_servicio.abrir_subgrafo()
        elif nombre in ('comparar', 'Comparar busquedas'):
            self.comparacion.iniciar_comparacion()
        elif nombre in ('informe', 'Informe'):
            self.informes.abrir_informe()
        elif nombre in ('config', 'Configuracion'):
            self.abrir_configuracion()
        else:
            self.accion_cfg(nombre)

    def habilitado_interfaz(self, nombre):
        if nombre in ('config',
            'auto',
            'v_binaria',
            'v_validas',
            'v_hitbox',
            'v_zonas',
            'subgrafo',
            'informe',
            'reiniciar'):
            return True
        if nombre.startswith('alg:'):
            return not (self.comparando or self.animando or self.tarea_busqueda is not None)
        return self.boton_habilitado({'ejecutar': 'Ejecutar busqueda',
            'animar': 'Animar recorrido',
            'agregar': 'Obstaculo ahora',
            'limpiar': 'Limpiar obstaculos',
            'comparar': 'Comparar busquedas'}.get(nombre,
            nombre))

    def razon_deshabilitado(self, nombre):
        """Texto que explica por que un control esta inactivo (se muestra en el tooltip)."""
        if nombre.startswith('alg:'):
            return 'No se puede cambiar durante una búsqueda o recorrido.'
        if self.preparacion_alt is not None:
            return 'Espera: se está preparando el mapa.'
        if self.comparando:
            return 'Hay una comparación en curso.'
        if nombre in ('ejecutar', 'comparar'):
            if self.inicio_busqueda is None:
                return 'Marca el inicio con un clic en el mapa.'
            if self.destino_busqueda is None:
                return 'Marca el destino con un segundo clic.'
            return 'Hay una búsqueda en curso.'
        if nombre == 'animar':
            if self.animando:
                return 'El NPC ya está en recorrido.'
            if self.tarea_busqueda is not None:
                return 'Espera a que termine la búsqueda.'
            if self.algoritmo_activo != self.algoritmo_seleccionado:
                return 'Primero ejecuta la búsqueda con el algoritmo seleccionado.'
            return 'Primero ejecuta una búsqueda que encuentre una ruta.'
        if nombre == 'agregar':
            return 'Disponible solo durante el recorrido.'
        if nombre == 'limpiar':
            return 'Detén el recorrido primero.' if self.animando else 'No hay obstáculos activos.'
        return ''

    def cambiar_configuracion(self, nombre, valor):
        limites = {'cfg_cada_pasos': (50, 1000), 'cfg_maximo': (1, 30), 'cfg_radio_deteccion': (5, 100)}
        if nombre in limites:
            lo, hi = limites[nombre]
            vars(self)[nombre] = max(lo, min(hi, int(valor)))
        elif nombre == 'cfg_semilla':
            vars(self)[nombre] = int(valor)
            self.gestor_obstaculos.rng.seed(int(valor))
        elif nombre == 'cfg_tamano' and valor in TAMANOS:
            vars(self)[nombre] = valor
        elif nombre == 'cfg_sin_ruta' and valor in ('retirar', 'detener'):
            vars(self)[nombre] = valor

    def abrir_configuracion(self):
        if self.configuracion_ventana is None:
            self.configuracion_ventana = ui.Configuracion(lambda: vars(self),
                self.accion_interfaz,
                self.boton_habilitado,
                self.cambiar_configuracion)
        else:
            self.configuracion_ventana.ventana.focus()
            self.configuracion_ventana.dibujar()

    def estado_ui(self):
        """Instantanea del estado para la barra lateral (no contiene logica)."""
        ini = self.sesion.get('inicial')
        tiene_puntos = self.inicio_busqueda is not None and self.destino_busqueda is not None
        ruta_lista = self.ruta_encontrada is not None
        terminado = not self.animando and self.sesion.get('resultado') == 'Destino alcanzado'
        if self.preparacion_alt is not None:
            clave, texto = ('preparando', 'Preparando el mapa')
        elif self.comparando:
            clave, texto = ('comparando', 'Comparando algoritmos')
        elif self.pausa_replan:
            clave, texto = ('replanificando', 'Replanificando ruta')
        elif self.tarea_busqueda is not None:
            clave, texto = ('buscando', 'Buscando ruta')
        elif self.animando:
            clave, texto = ('recorriendo', 'En recorrido')
        elif self.estadisticas.get('estado') == 'Sin camino':
            clave, texto = ('sin_ruta', 'Sin camino')
        elif terminado:
            clave, texto = ('completado', 'Destino alcanzado')
        elif ruta_lista:
            clave, texto = ('listo', 'Ruta lista')
        elif tiene_puntos:
            clave, texto = ('listo', 'Puntos marcados')
        else:
            clave, texto = ('espera', 'Selecciona inicio y destino')
        pasos = ('hecho' if tiene_puntos else 'activo',
            'hecho' if ruta_lista else 'activo' if tiene_puntos else 'pendiente',
            'hecho' if terminado else 'activo' if ruta_lista or self.animando else 'pendiente')
        tiempo_inicial = ini['tiempo'] if ini is not None else self.estadisticas.get('tiempo', 0.0)
        busqueda = [('Tiempo de búsqueda', f"{self.estadisticas.get('tiempo', 0):.4f} s"),
            ('Nodos explorados', f"{self.estadisticas.get('expandidos', 0):,}"),
            ('Ruta inicial', '--' if ini is None or ini['longitud'] is None else f"{ini['longitud']:,}")]
        if self.estadisticas.get('algoritmo') != self.algoritmo_seleccionado:
            busqueda = [(l, '--') for l, _ in busqueda]
        navegacion = [('Movimientos', f"{self.sesion['pasos']:,}"),
            ('Rutas creadas', str(len(self.sesion['rutas']))),
            ('Tiempo total', f"{tiempo_inicial + self.sesion['t_total']:.2f} s")]
        if self.comparando:
            busqueda = [(l, '--') for l, _ in busqueda]
            navegacion = [(l, '--') for l, _ in navegacion]
        return dict(algoritmos=ALGORITMOS_DISPONIBLES,
            alg_sel=self.algoritmo_seleccionado,
            estado_clave=clave,
            estado_texto=texto,
            mensaje=ui.acentuar(self.mensaje),
            pasos=pasos,
            auto=self.aparicion_auto,
            activos=len(self.gestor_obstaculos.obstaculos),
            generados=self.sesion['obstaculos'],
            replans=self.sesion['replans'],
            vistas=dict(binaria=self.modo == 3, validas=self.mostrar_posiciones_validas, hitbox=self.mostrar_hitbox_pies, zonas=self.mostrar_zonas_bloqueo),
            titulo_busqueda='Búsqueda',
            titulo_navegacion='Navegación',
            metricas_busqueda=busqueda,
            metricas_navegacion=navegacion)

    def dibujar_superposiciones(self):
        """Elementos flotantes del visor: estado ocupado, leyenda y ayuda."""
        vista = pygame.Rect(0, 0, self.ANCHO_VISTA, self.ALTO_VISTA)
        self.pantalla.set_clip(vista)
        t = pygame.time.get_ticks() / 1000
        if self.preparacion_alt is not None:
            ui.banner(self.pantalla, vista, 'Preparando el mapa', ui.acentuar(self.mensaje), ui.AMBER, t)
        elif self.comparando:
            ui.banner(self.pantalla, vista, 'Comparando algoritmos', ui.acentuar(self.mensaje), ui.BLUE, t)
        elif self.pausa_replan:
            ui.banner(self.pantalla,
                vista,
                f'Replanificando con {self.algoritmo_activo}',
                f"{self.estadisticas.get('expandidos', 0):,} nodos explorados",
                ui.AMBER,
                t)
        elif self.tarea_busqueda is not None:
            ui.banner(self.pantalla,
                vista,
                'Buscando ruta',
                f"{self.estadisticas.get('expandidos', 0):,} nodos explorados",
                ui.BLUE,
                t)
        items = []
        if self.ruta_encontrada is not None:
            items.append(((255, 214, 64), 'Ruta', 'linea'))
        if len(self.rastro_puntos) > 1:
            items.append(((255, 96, 84), 'Recorrido', 'linea'))
        if self.rutas_descartadas:
            items.append(((255, 150, 52), 'Ruta descartada', 'linea'))
        if self.gestor_obstaculos.obstaculos:
            items.append(((120, 170, 90), 'Obstáculo', 'caja'))
        if self.mostrar_zonas_bloqueo and self.gestor_obstaculos.obstaculos:
            items.append(((255, 80, 80), 'Zona de bloqueo', 'caja'))
        ui.leyenda(self.pantalla, vista, items)
        if not self.animando:
            ayuda = 'Clic: inicio y destino   ·   Arrastrar: mover   ·   Rueda: zoom   ·   R: centrar   ·   F1: atajos'
            coordenadas = self.camara.coordenadas_mouse_mapa(pygame.mouse.get_pos()) if pygame.mouse.get_focused() else None
            if coordenadas is not None:
                ayuda += f'   |   X: {coordenadas[0]}   Y: {coordenadas[1]}'
            ui.ayuda_visor(self.pantalla, vista, ayuda)
        if self.mostrar_ayuda:
            ui.panel_atajos(self.pantalla, vista)
        self.pantalla.set_clip(None)
