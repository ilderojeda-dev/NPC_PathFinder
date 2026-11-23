"""Transformaciones de coordenadas, zoom, redimensionado y seguimiento del NPC."""

import math
import pygame

class Camara:
    """Servicio con referencia a la aplicacion; no copia matrices ni mantiene globals."""

    def __init__(self, app):
        self.app = app

    def inicializar(self):
        self.app.modo = 0
        self.app.modo_anterior_binario = 0
        self.app.mostrar_posiciones_validas = False
        self.app.nombres_vista = {0: 'Imagen original', 3: 'Matriz binaria de transitabilidad'}
        self.app.zoom_minimo = min((self.app.ANCHO_VISTA - 40) / self.app.ancho_mapa,
            (self.app.ALTO_VISTA - 40) / self.app.alto_mapa)
        self.app.zoom_maximo = min(4.0, 4500 / max(self.app.ancho_mapa, self.app.alto_mapa))
        self.app.zoom = self.app.zoom_minimo
        self.app.desplazamiento_x = (self.app.ANCHO_VISTA - self.app.ancho_mapa * self.app.zoom) / 2
        self.app.desplazamiento_y = (self.app.ALTO_VISTA - self.app.alto_mapa * self.app.zoom) / 2
        self.app.seguimiento_camara = False
        self.app.encuadrando_npc = False
        self.app.progreso_visual = 0.0
        self.actualizar_vista()

    def a_pantalla(self, puntos):
        """Coordenadas del mapa -> pantalla (centro de cada nodo)."""
        sx = self.app.mapa_escalado.get_width() / self.app.ancho_mapa
        sy = self.app.mapa_escalado.get_height() / self.app.alto_mapa
        ox, oy = (int(self.app.desplazamiento_x), int(self.app.desplazamiento_y))
        return [(round(ox + (x + 0.5) * sx), round(oy + (y + 0.5) * sy)) for x, y in puntos]

    def ancho_linea(self):
        """Grosor de las lineas de ruta: legible con poco zoom, sin engrosarse de mas."""
        return max(3, round(1.5 * self.app.zoom + 1.5))

    def actualizar_vista(self):
        if self.app.mostrar_posiciones_validas:
            superficie = self.app.imagen_posiciones_validas
        elif self.app.modo == 3:
            superficie = self.app.imagen_transitabilidad
        else:
            superficie = self.app.imagen_original
        nuevo_ancho = max(1, int(self.app.ancho_mapa * self.app.zoom))
        nuevo_alto = max(1, int(self.app.alto_mapa * self.app.zoom))
        self.app.mapa_escalado = pygame.transform.scale(superficie, (nuevo_ancho, nuevo_alto))

    def centrar_mapa(self):
        self.app.zoom = self.app.zoom_minimo
        self.app.desplazamiento_x = (self.app.ANCHO_VISTA - self.app.ancho_mapa * self.app.zoom) / 2
        self.app.desplazamiento_y = (self.app.ALTO_VISTA - self.app.alto_mapa * self.app.zoom) / 2
        self.actualizar_vista()

    def detener_seguimiento(self):
        self.app.seguimiento_camara = self.app.encuadrando_npc = False
        self.app.progreso_visual = 0.0
        self.app.arrastrando = False
        self.app.clic_inicial = None

    def centro_visual_mundo(self):
        if self.app.seguimiento_camara and self.app.ruta_encontrada:
            i = min(int(self.app.progreso_visual), len(self.app.ruta_encontrada) - 1)
            j = min(i + 1, len(self.app.ruta_encontrada) - 1)
            fraccion = self.app.progreso_visual - i
            a, b = (self.app.ruta_encontrada[i], self.app.ruta_encontrada[j])
            return (a[0] + (b[0] - a[0]) * fraccion, a[1] + (b[1] - a[1]) * fraccion)
        return self.app.npc.centro_hitbox()

    def centro_pies_pantalla(self):
        if self.app.seguimiento_camara and (not self.app.encuadrando_npc):
            return (self.app.ANCHO_VISTA / 2, self.app.ALTO_VISTA / 2)
        x, y = self.centro_visual_mundo()
        sx = self.app.mapa_escalado.get_width() / self.app.ancho_mapa
        sy = self.app.mapa_escalado.get_height() / self.app.alto_mapa
        return (int(self.app.desplazamiento_x) + (x + 0.5) * sx, int(self.app.desplazamiento_y) + (y + 0.5) * sy)

    def actualizar_seguimiento(self, dt):
        # Se admite fondo exterior para conservar el NPC centrado cerca de los bordes.
        if not self.app.seguimiento_camara or not self.app.ruta_encontrada:
            return
        factor = 1 - math.exp(-18 * max(0, dt))
        if not self.app.encuadrando_npc:
            self.app.progreso_visual += (self.app.indice_ruta - self.app.progreso_visual) * factor
            if not self.app.animando and abs(self.app.indice_ruta - self.app.progreso_visual) < 0.01:
                self.app.progreso_visual = float(self.app.indice_ruta)
        x, y = self.centro_visual_mundo()
        sx = self.app.mapa_escalado.get_width() / self.app.ancho_mapa
        sy = self.app.mapa_escalado.get_height() / self.app.alto_mapa
        destino_x = self.app.ANCHO_VISTA / 2 - (x + 0.5) * sx
        destino_y = self.app.ALTO_VISTA / 2 - (y + 0.5) * sy
        if self.app.encuadrando_npc:
            self.app.desplazamiento_x += (destino_x - self.app.desplazamiento_x) * factor
            self.app.desplazamiento_y += (destino_y - self.app.desplazamiento_y) * factor
            if max(abs(destino_x - self.app.desplazamiento_x), abs(destino_y - self.app.desplazamiento_y)) < 0.1:
                self.app.desplazamiento_x, self.app.desplazamiento_y = (destino_x, destino_y)
                self.app.encuadrando_npc = False
        else:
            self.app.desplazamiento_x, self.app.desplazamiento_y = (destino_x, destino_y)
            if not self.app.animando and self.app.progreso_visual == float(self.app.indice_ruta):
                self.app.seguimiento_camara = False

    def coordenadas_mouse_mapa(self, pos):
        """Pixel del mapa bajo el mouse, incluyendo terrenos no transitables."""
        if not (0 <= pos[0] < self.app.ANCHO_VISTA and 0 <= pos[1] < self.app.ALTO_VISTA):
            return None
        rect = self.app.mapa_escalado.get_rect(topleft=(int(self.app.desplazamiento_x),
            int(self.app.desplazamiento_y)))
        if not rect.collidepoint(pos):
            return None
        return ((pos[0] - rect.x) * self.app.ancho_mapa // rect.w,
            (pos[1] - rect.y) * self.app.alto_mapa // rect.h)

    def mouse_a_nodo(self, pos):
        if not (0 <= pos[0] < self.app.ANCHO_VISTA and 0 <= pos[1] < self.app.ALTO_VISTA):
            return None
        x = math.floor((pos[0] - int(self.app.desplazamiento_x)) * self.app.ancho_mapa / self.app.mapa_escalado.get_width())
        y = math.floor((pos[1] - int(self.app.desplazamiento_y)) * self.app.alto_mapa / self.app.mapa_escalado.get_height())
        return (x, y) if self.app.mapa.es_posicion_valida(x, y) else None

    def redimensionar_interfaz(self):
        """Conserva el centro del mundo y el zoom al cambiar el viewport."""
        anterior_ancho, anterior_alto = (self.app.ANCHO_VISTA, self.app.ALTO_VISTA)
        self.app.pantalla = pygame.display.get_surface()
        self.app.ANCHO, self.app.ALTO = self.app.pantalla.get_size()
        self.app.ANCHO_VISTA, self.app.ALTO_VISTA = (max(1, self.app.ANCHO - self.app.ANCHO_LATERAL),
            self.app.ALTO)
        self.app.desplazamiento_x += (self.app.ANCHO_VISTA - anterior_ancho) / 2
        self.app.desplazamiento_y += (self.app.ALTO_VISTA - anterior_alto) / 2
        self.app.zoom_minimo = min(self.app.ANCHO_VISTA / self.app.ancho_mapa,
            self.app.ALTO_VISTA / self.app.alto_mapa)
        self.app.barra.redimensionar(self.app.ANCHO_VISTA, self.app.ALTO)
        self.app.arrastrando, self.app.clic_inicial = (False, None)

    def _rect_pantalla(self, x, y, ancho, alto):
        sx = self.app.mapa_escalado.get_width() / self.app.ancho_mapa
        sy = self.app.mapa_escalado.get_height() / self.app.alto_mapa
        return pygame.Rect(round(int(self.app.desplazamiento_x) + x * sx),
            round(int(self.app.desplazamiento_y) + y * sy),
            max(1, round(ancho * sx)),
            max(1, round(alto * sy)))
