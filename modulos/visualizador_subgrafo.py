"""Visualiza regiones del grafo implicito utilizando la matriz existente."""

import numpy as np
import pygame
from . import interfaz_pygame as ui

class VisualizadorSubgrafo:
    """Ventana secundaria: elige una region y muestra sus nodos validos y conexiones.
    Cerrarla no interrumpe el recorrido ni cierra la aplicacion."""
    TAM_CONFIG, TAM_RESULTADO = ((640, 560), (960, 920))

    def __init__(self, app):
        self.app = app
        self.ventana = pygame.Window('Subgrafo del mapa', size=self.TAM_CONFIG)
        self.campos = ['450', '400', '50', '50']
        self.activo = 0
        self.reemplazar = True
        self.error = ''
        self.imagen = None
        self.rects = [pygame.Rect(28 + i % 2 * 292, 148 + i // 2 * 88, 280, 40) for i in range(4)]
        self.btn_vista = pygame.Rect(28, 346, 286, 36)
        self.btn_npc = pygame.Rect(326, 346, 286, 36)
        self.confirmar = pygame.Rect(28, 398, 584, 44)
        self.volver = pygame.Rect(self.TAM_RESULTADO[0] - 16 - 170, 18, 170, 36)
        self.dibujar()

    def centrar_en(self, cx, cy):
        filas, columnas = self.app.matriz_posiciones_validas.shape
        try:
            w, h = (int(self.campos[2]), int(self.campos[3]))
        except ValueError:
            w = h = 50
        w, h = (max(1, min(w, columnas)), max(1, min(h, filas)))
        x = max(0, min(columnas - w, int(cx - w / 2)))
        y = max(0, min(filas - h, int(cy - h / 2)))
        self.campos = [str(x), str(y), str(w), str(h)]
        self.error = ''

    def centrar_en_vista(self):
        sx = self.app.mapa_escalado.get_width() / self.app.ancho_mapa
        sy = self.app.mapa_escalado.get_height() / self.app.alto_mapa
        self.centrar_en((self.app.ANCHO_VISTA / 2 - self.app.desplazamiento_x) / sx,
            (self.app.ALTO_VISTA / 2 - self.app.desplazamiento_y) / sy)

    def centrar_en_npc(self):
        if self.app.inicio_busqueda is None:
            self.error = 'Marca un punto de inicio en el mapa para usar la posición del NPC.'
            return
        self.centrar_en(*self.app.npc.centro_hitbox())

    def generar(self):
        try:
            valores = [int(c) for c in self.campos]
            imagen, nodos, aristas = self.app.visualizador_subgrafo_servicio.crear_imagen_subgrafo(*valores)
        except ValueError as error:
            self.error = ui.acentuar(error)
            self.dibujar()
            return
        self.imagen = imagen
        self.region = valores
        self.nodos, self.aristas = (nodos, aristas)
        self.ventana.title = 'Subgrafo del mapa - nodos y conexiones'
        self.ventana.size = self.TAM_RESULTADO
        factor = min(884 / imagen.get_width(), 700 / imagen.get_height(), 1)
        self.presentacion = pygame.transform.scale(imagen,
            (max(1, int(imagen.get_width() * factor)), max(1, int(imagen.get_height() * factor))))
        self.dibujar()

    def dibujar(self):
        s = self.ventana.get_surface()
        s.fill(ui.BG)
        mouse = pygame.mouse.get_pos()
        if self.imagen is None:
            self.dibujar_config(s, mouse)
        else:
            self.dibujar_resultado(s, mouse)
        self.ventana.flip()

    def dibujar_config(self, s, mouse):
        filas, columnas = self.app.matriz_posiciones_validas.shape
        ui.text(s, 'Subgrafo del mapa', (28, 24), size=24, bold=True)
        ui.text(s,
            'Elige una región para ver sus nodos válidos y las conexiones entre ellos.',
            (28, 58),
            ui.MUTED,
            13)
        ui.etiqueta_seccion(s, 28, 100, 'Región (coordenadas del mapa)')
        nombres = ('X inicial (columna)', 'Y inicial (fila)', 'Ancho', 'Alto')
        for i, (nombre, rect) in enumerate(zip(nombres, self.rects)):
            ui.text(s, nombre, (rect.x, rect.y - 22), ui.MUTED, 13)
            ui.box(s, rect, ui.CARD, 9, ui.ACCENT if i == self.activo else ui.BORDER)
            if i == self.activo:
                pygame.draw.rect(s, ui.ACCENT, rect, 2, border_radius=9)
            ui.text(s, self.campos[i], (rect.x + 14, rect.y + 9), ui.TEXT, 16, True)
        ui.text(s,
            f'El mapa mide {columnas} × {filas} nodos. La región debe quedar dentro.',
            (28, 318),
            ui.MUTED,
            12)
        for rect, label in ((self.btn_vista, 'Centrar en la vista'), (self.btn_npc, 'Centrar en el NPC')):
            ui.button(s, rect, label, hover=rect.collidepoint(mouse))
        ui.button(s, self.confirmar, 'Visualizar', primary=True, hover=self.confirmar.collidepoint(mouse))
        if self.error:
            caja = pygame.Rect(28, 456, 584, 40)
            ui.box(s, caja, (44, 26, 26), 9, ui.DANGER)
            ui.text(s, self.error, (caja.x + 14, caja.y + 11), ui.DANGER, 13, width=caja.w - 28)
        ui.text(s,
            'Clic o TAB: cambiar de campo  ·  Escribir: valor  ·  Enter: visualizar  ·  Esc: cerrar',
            (28, 520),
            ui.MUTED,
            12)

    def dibujar_resultado(self, s, mouse):
        x, y, w, h = self.region
        ui.text(s, 'Subgrafo del mapa', (28, 18), size=24, bold=True)
        ui.text(s, 'Nodos válidos y conexiones de la región elegida', (28, 50), ui.MUTED, 13)
        ui.button(s, self.volver, 'Cambiar región', hover=self.volver.collidepoint(mouse))
        tarjetas = (('Origen', f'({x}, {y})'),
            ('Región', f'{w} × {h}'),
            ('Nodos válidos', f'{self.nodos:,}'),
            ('Conexiones', f'{self.aristas:,}'))
        ancho = (960 - 56 - 36) // 4
        for i, (etiqueta, valor) in enumerate(tarjetas):
            r = pygame.Rect(28 + i * (ancho + 12), 84, ancho, 52)
            ui.box(s, r, ui.CARD, 10)
            ui.text(s, etiqueta, (r.x + 14, r.y + 6), ui.MUTED, 11)
            ui.text(s, valor, (r.x + 14, r.y + 22), ui.TEXT, 18, True)
        cx = 28
        pygame.draw.circle(s, (25, 90, 255), (cx + 6, 156), 5)
        ui.text(s, 'Nodo válido', (cx + 20, 147), ui.TEXT, 12)
        pygame.draw.line(s, (245, 35, 35), (cx + 130, 156), (cx + 154, 156), 3)
        ui.text(s, 'Conexión entre vecinos', (cx + 162, 147), ui.TEXT, 12)
        ui.text(s, 'Fondo: mapa original', (cx + 340, 147), ui.MUTED, 12)
        marco = pygame.Rect(28, 176, 904, 716)
        ui.box(s, marco, (10, 20, 18), 12)
        s.blit(self.presentacion, self.presentacion.get_rect(center=marco.center))
        ui.text(s, 'X crece a la derecha y Y hacia abajo.  Esc cierra solo esta ventana.', (28, 898), ui.MUTED, 12)

    def evento(self, evento):
        if evento.type == pygame.WINDOWCLOSE or (evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE):
            self.ventana.destroy()
            return False
        if evento.type == pygame.WINDOWEXPOSED:
            self.dibujar()
        if self.imagen is not None:
            if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1 and self.volver.collidepoint(evento.pos):
                self.imagen = None
                self.error = ''
                self.ventana.size = self.TAM_CONFIG
                self.ventana.title = 'Subgrafo del mapa'
            self.dibujar()
            return True
        if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
            for i, rect in enumerate(self.rects):
                if rect.collidepoint(evento.pos):
                    self.activo, self.reemplazar = (i, True)
            if self.btn_vista.collidepoint(evento.pos):
                self.centrar_en_vista()
            elif self.btn_npc.collidepoint(evento.pos):
                self.centrar_en_npc()
            elif self.confirmar.collidepoint(evento.pos):
                self.generar()
                return True
        if evento.type == pygame.KEYDOWN:
            if evento.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.generar()
                return True
            if evento.key == pygame.K_TAB:
                self.activo = (self.activo + (-1 if evento.mod & pygame.KMOD_SHIFT else 1)) % 4
                self.reemplazar = True
            elif evento.key == pygame.K_BACKSPACE:
                self.campos[self.activo] = '' if self.reemplazar else self.campos[self.activo][:-1]
                self.reemplazar = False
            else:
                caracter = getattr(evento, 'unicode', '')
                if caracter and caracter.isascii() and caracter.isdigit():
                    valor = '' if self.reemplazar else self.campos[self.activo]
                    self.campos[self.activo] = (valor + caracter)[:6]
                    self.reemplazar = False
        self.dibujar()
        return True

class Subgrafos:
    """Servicio con referencia a la aplicacion; no copia matrices ni mantiene globals."""

    def __init__(self, app):
        self.app = app

    def crear_imagen_subgrafo(self, x, y, ancho, alto):
        filas, columnas = self.app.matriz_posiciones_validas.shape
        if x < 0 or y < 0 or ancho <= 0 or (alto <= 0):
            raise ValueError('X/Y deben ser >= 0; ancho/alto deben ser mayores que 0.')
        if x + ancho > columnas or y + alto > filas:
            raise ValueError(f'La region debe quedar dentro de {columnas} x {filas}.')
        nodos = self.app.matriz_posiciones_validas[y:y + alto, x:x + ancho] == 1
        horizontales = nodos[:, :-1] & nodos[:, 1:]
        verticales = nodos[:-1, :] & nodos[1:, :]
        cantidad_nodos = int(np.count_nonzero(nodos))
        cantidad_aristas = int(np.count_nonzero(horizontales) + np.count_nonzero(verticales))
        paso = min(14, max(2, 700 // max(ancho, alto)))
        fondo = self.app.imagen_original.subsurface(pygame.Rect(x, y, ancho, alto))
        imagen = pygame.transform.scale(fondo, (ancho * paso, alto * paso))
        for o in self.app.gestor_obstaculos.obstaculos:
            if o.x < x + ancho and o.x + o.ancho > x and (o.y < y + alto) and (o.y + o.alto > y):
                imagen.blit(pygame.transform.scale(o.sprite, (o.ancho * paso, o.alto * paso)),
                    ((o.x - x) * paso, (o.y - y) * paso))
        pixeles = pygame.surfarray.pixels3d(imagen)
        centro = paso // 2
        fy, fx = np.nonzero(horizontales)
        vy, vx = np.nonzero(verticales)
        for offset in range(paso + 1):
            pixeles[fx * paso + centro + offset, fy * paso + centro] = (245, 35, 35)
            pixeles[vx * paso + centro, vy * paso + centro + offset] = (245, 35, 35)
        ny, nx = np.nonzero(nodos)
        radio = 1 if paso >= 6 else 0
        for dy in range(-radio, radio + 1):
            for dx in range(-radio, radio + 1):
                if dx * dx + dy * dy <= radio * radio:
                    pixeles[nx * paso + centro + dx, ny * paso + centro + dy] = (25, 90, 255)
        del pixeles
        return (imagen, cantidad_nodos, cantidad_aristas)

    def abrir_subgrafo(self):
        if self.app.visualizador_subgrafo is None:
            self.app.visualizador_subgrafo = VisualizadorSubgrafo(self.app)
        else:
            self.app.visualizador_subgrafo.ventana.focus()
