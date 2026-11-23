"""Presentacion Pygame: tema, widgets, barra lateral y ventana de configuracion.

Sin logica de busqueda ni de simulacion: este modulo solo dibuja y reporta
clics. Todo el estado llega mediante callbacks (estado, accion, habilitado,
razon), de modo que la aplicacion principal conserva el control.
"""
import math
import pygame

# ---------------------------------------------------------------- tema
BG = (14, 24, 23)
PANEL = (20, 34, 31)
CARD = (29, 46, 41)
CARD_HOVER = (38, 60, 52)
CARD_PRESS = (22, 36, 32)
CARD_OFF = (24, 35, 32)
BORDER = (49, 71, 61)
TEXT = (236, 241, 226)
MUTED = (155, 176, 161)
DIM = (95, 115, 101)
ACCENT = (176, 219, 133)
ACCENT_HOVER = (198, 235, 158)
ACCENT_PRESS = (148, 192, 110)
INK = (24, 43, 28)
AMBER = (234, 190, 94)
BLUE = (122, 186, 228)
DANGER = (236, 120, 108)
_fonts = {}


def font(size=15, bold=False):
    key = size, bold
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont('Segoe UI', size, bold=bold)
    return _fonts[key]


def recortar(value, f, width):
    """Recorta con puntos suspensivos hasta que el texto quepa en width."""
    value = str(value)
    if width is None or f.size(value)[0] <= width:
        return value
    while value and f.size(value + '...')[0] > width:
        value = value[:-1]
    return value.rstrip() + '...'


def text(surface, value, pos, color=TEXT, size=15, bold=False, width=None):
    f = font(size, bold)
    surface.blit(f.render(recortar(value, f, width), True, color), pos)


def text_centrado(surface, value, rect, color=TEXT, size=14, bold=False):
    f = font(size, bold)
    img = f.render(recortar(value, f, rect.w - 8), True, color)
    surface.blit(img, img.get_rect(center=rect.center))


def ajustar(value, size, width, bold=False, max_lineas=3):
    """Divide un texto en lineas que caben en width (la ultima se recorta)."""
    f = font(size, bold)
    lineas, actual = [], ''
    for palabra in str(value).split():
        prueba = (actual + ' ' + palabra).strip()
        if f.size(prueba)[0] <= width:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        lineas[-1] = recortar(lineas[-1] + ' ...', f, width)
    return lineas


def box(surface, rect, color=CARD, radius=12, border=BORDER):
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surface, border, rect, 1, border_radius=radius)


def button(surface, rect, label, enabled=True, primary=False, active=False, hover=False):
    """Boton plano (lo usan el informe y la configuracion)."""
    color = ACCENT if primary and enabled else ((44, 67, 54) if active or hover else CARD)
    if not enabled:
        color = CARD_OFF
    box(surface, rect, color, 9)
    ink = INK if primary and enabled else TEXT if enabled else DIM
    text_centrado(surface, label, rect, ink, 14, True)


def boton_configuracion(surface, rect, hover=False, pressed=False, enabled=True):
    """Engranaje dibujado sin depender de fuentes con simbolos especiales."""
    fondo = CARD_PRESS if pressed else CARD_HOVER if hover else CARD
    box(surface, rect, fondo, 9)
    cx, cy = rect.center
    puntos = []
    for i in range(32):
        angulo = i * math.tau / 32
        radio = 11 if i % 4 in (1, 2) else 8.5
        puntos.append((round(cx + math.cos(angulo) * radio), round(cy + math.sin(angulo) * radio)))
    pygame.draw.polygon(surface, ACCENT if hover else TEXT, puntos)
    pygame.draw.circle(surface, fondo, (cx, cy), 4)


def marca_logo(surface, x, y):
    """Pequeno grafo (tres nodos conectados) como marca de la aplicacion."""
    a, b, c = (x + 4, y + 22), (x + 24, y + 22), (x + 14, y + 4)
    for p, q in ((a, b), (b, c), (a, c)):
        pygame.draw.line(surface, ACCENT, p, q, 2)
    for p in (a, b, c):
        pygame.draw.circle(surface, BG, p, 5)
        pygame.draw.circle(surface, ACCENT, p, 4)


def etiqueta_seccion(surface, x, y, value):
    text(surface, str(value).upper(), (x, y), MUTED, 11, True)


def pastilla(surface, rect, value, color, size=11):
    """Etiqueta pequena redondeada con el texto en color de acento."""
    fondo = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(fondo, (*color, 38), fondo.get_rect(), border_radius=rect.h // 2)
    pygame.draw.rect(fondo, (*color, 130), fondo.get_rect(), 1, border_radius=rect.h // 2)
    surface.blit(fondo, rect.topleft)
    text_centrado(surface, value, rect, color, size, True)


def interruptor(surface, rect, activo, habilitado=True):
    pista = pygame.Rect(0, 0, 40, 22)
    pista.midright = (rect.right - 12, rect.centery)
    pygame.draw.rect(surface, ACCENT if activo else BORDER, pista, border_radius=11)
    pygame.draw.circle(surface, INK if activo else MUTED,
                       (pista.right - 11 if activo else pista.x + 11, pista.centery), 8)


# ---------------------------------------------------------------- superposiciones del visor
def polilinea(surface, puntos, color, ancho, borde=(8, 18, 16), grosor_borde=2):
    """Linea gruesa con contorno oscuro y uniones redondeadas (legible sobre cualquier fondo)."""
    if len(puntos) < 2:
        return
    if grosor_borde:
        pygame.draw.lines(surface, borde, False, puntos, ancho + grosor_borde * 2)
        if ancho >= 3:
            for p in puntos:
                pygame.draw.circle(surface, borde, p, (ancho + grosor_borde * 2) // 2)
    pygame.draw.lines(surface, color, False, puntos, ancho)
    if ancho >= 3:
        for p in puntos:
            pygame.draw.circle(surface, color, p, ancho // 2)


def etiqueta_flotante(surface, pos, value, color):
    f = font(12, True)
    img = f.render(value, True, color)
    r = img.get_rect(topleft=(pos[0] + 12, pos[1] - 13)).inflate(14, 6)
    fondo = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(fondo, (8, 18, 16, 215), fondo.get_rect(), border_radius=r.h // 2)
    pygame.draw.rect(fondo, (*color, 190), fondo.get_rect(), 1, border_radius=r.h // 2)
    surface.blit(fondo, r.topleft)
    surface.blit(img, img.get_rect(center=r.center))


def marcador(surface, centro, color, etiqueta, radio=8):
    """Marcador de inicio/destino: anillo con halo y etiqueta con fondo."""
    halo = pygame.Surface((radio * 4, radio * 4), pygame.SRCALPHA)
    pygame.draw.circle(halo, (*color, 70), (radio * 2, radio * 2), radio * 2)
    surface.blit(halo, (centro[0] - radio * 2, centro[1] - radio * 2))
    pygame.draw.circle(surface, (8, 18, 16), centro, radio + 2)
    pygame.draw.circle(surface, color, centro, radio)
    pygame.draw.circle(surface, (8, 18, 16), centro, max(2, radio // 3))
    etiqueta_flotante(surface, (centro[0] + radio, centro[1] - radio // 2), etiqueta, color)


def banner(surface, vista, titulo, detalle, color=AMBER, tiempo=0.0):
    """Cinta superior con indicador giratorio para los estados ocupados."""
    f1, f2 = font(14, True), font(12)
    t1 = f1.render(titulo, True, TEXT)
    t2 = f2.render(recortar(detalle, f2, 420), True, MUTED) if detalle else None
    ancho = 56 + max(t1.get_width(), t2.get_width() if t2 else 0) + 22
    r = pygame.Rect(0, vista.y + 16, ancho, 50 if t2 else 38)
    r.centerx = vista.centerx
    fondo = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(fondo, (12, 24, 22, 235), fondo.get_rect(), border_radius=14)
    pygame.draw.rect(fondo, (*color, 160), fondo.get_rect(), 1, border_radius=14)
    surface.blit(fondo, r.topleft)
    cx, cy = r.x + 26, r.centery
    for i in range(8):
        a = tiempo * 6 - i * math.tau / 8
        k = 1 - i / 8
        pygame.draw.circle(surface, tuple(int(c * (0.35 + 0.65 * k)) for c in color),
                           (round(cx + math.cos(a) * 9), round(cy + math.sin(a) * 9)), 2 + (i < 3))
    surface.blit(t1, (r.x + 50, r.y + (7 if t2 else 10)))
    if t2:
        surface.blit(t2, (r.x + 50, r.y + 27))


def leyenda(surface, vista, items):
    if not items:
        return
    f = font(12)
    ancho = 30 + max(f.size(l)[0] for _, l, _ in items) + 14
    r = pygame.Rect(0, 0, ancho, 14 + 22 * len(items))
    r.bottomright = (vista.right - 14, vista.bottom - 14)
    fondo = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(fondo, (12, 24, 22, 220), fondo.get_rect(), border_radius=12)
    pygame.draw.rect(fondo, (*BORDER, 255), fondo.get_rect(), 1, border_radius=12)
    surface.blit(fondo, r.topleft)
    for i, (color, label, estilo) in enumerate(items):
        y = r.y + 18 + i * 22
        if estilo == 'linea':
            pygame.draw.line(surface, (8, 18, 16), (r.x + 12, y), (r.x + 26, y), 6)
            pygame.draw.line(surface, color, (r.x + 12, y), (r.x + 26, y), 3)
        else:
            pygame.draw.rect(surface, color, (r.x + 12, y - 6, 14, 12), border_radius=3)
        surface.blit(f.render(label, True, TEXT), (r.x + 34, y - 8))


def ayuda_visor(surface, vista, value):
    f = font(12)
    # Mantener toda la ayuda y las coordenadas legibles en ventanas pequenas.
    lineas = ajustar(value, 12, max(1, vista.w - 52), max_lineas=100)
    imagenes = [f.render(linea, True, MUTED) for linea in lineas]
    r = pygame.Rect(0, 0, max(img.get_width() for img in imagenes) + 24,
                    len(imagenes) * f.get_linesize() + 14)
    r.bottomleft = (vista.x + 14, vista.bottom - 14)
    fondo = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(fondo, (12, 24, 22, 220), fondo.get_rect(), border_radius=12)
    surface.blit(fondo, r.topleft)
    for i, img in enumerate(imagenes):
        surface.blit(img, (r.x + 12, r.y + 7 + i * f.get_linesize()))


ATAJOS = (
    ('Enter', 'Ejecutar búsqueda'), ('Espacio', 'Animar recorrido'),
    ('Q', 'Agregar obstáculo'), ('P', 'Generación automática'), ('X', 'Limpiar obstáculos'),
    ('G / 4', 'Vista binaria'), ('V', 'Posiciones válidas'), ('H', 'Hitbox de los pies'),
    ('B', 'Zonas de bloqueo'), ('R', 'Centrar el mapa'), ('N', 'Nueva semilla'),
    ('C', 'Comparar algoritmos'), ('I', 'Informe'), ('F1', 'Mostrar / ocultar atajos'),
    ('Esc', 'Salir'),
)


def panel_atajos(surface, vista):
    r = pygame.Rect(0, 0, 400, 64 + 27 * len(ATAJOS))
    r.center = vista.center
    fondo = pygame.Surface(r.size, pygame.SRCALPHA)
    pygame.draw.rect(fondo, (10, 20, 18, 240), fondo.get_rect(), border_radius=16)
    pygame.draw.rect(fondo, (*BORDER, 255), fondo.get_rect(), 1, border_radius=16)
    surface.blit(fondo, r.topleft)
    text(surface, 'Atajos de teclado', (r.x + 24, r.y + 18), ACCENT, 15, True)
    for i, (tecla, accion) in enumerate(ATAJOS):
        y = r.y + 56 + i * 27
        k = pygame.Rect(r.x + 24, y, 74, 21)
        box(surface, k, CARD, 6)
        text_centrado(surface, tecla, k, TEXT, 12, True)
        text(surface, accion, (r.x + 112, y + 1), TEXT, 13)


def tooltip(surface, pos, titulo, atajo=None, detalle=None, motivo=None):
    f1, f2 = font(13, True), font(12)
    lineas = [(titulo + (f'   [{atajo}]' if atajo else ''), f1, TEXT)]
    if detalle:
        lineas.append((detalle, f2, MUTED))
    if motivo:
        lineas.append((motivo, f2, AMBER))
    ancho = max(f.size(t)[0] for t, f, _ in lineas) + 22
    r = pygame.Rect(0, 0, ancho, 14 + 20 * len(lineas))
    r.topright = (pos[0] - 12, pos[1] + 8)
    r.clamp_ip(surface.get_rect().inflate(-8, -8))
    box(surface, r, (10, 20, 18), 8, ACCENT)
    for i, (t, f, c) in enumerate(lineas):
        surface.blit(f.render(t, True, c), (r.x + 11, r.y + 8 + i * 20))


# ---------------------------------------------------------------- barra lateral
ETIQUETAS_ALGORITMO = {
    'BFS Bidireccional': ('Óptimo', ACCENT, 'Dos frentes que se encuentran. Ruta mínima garantizada.'),
    'A* + ALT': ('Óptimo', ACCENT, 'Heurística con landmarks. Ruta mínima y menos nodos.'),
    'Greedy + ALT': ('Rápido', AMBER, 'Respuesta veloz, sin garantía de ruta mínima.'),
}

AYUDA_BOTONES = {
    'config': ('Configuración', None, 'Ritmo de obstáculos, detección y semilla.'),
    'ejecutar': ('Ejecutar búsqueda', 'Enter', 'Calcula la ruta con el algoritmo elegido.'),
    'animar': ('Animar recorrido', 'Espacio', 'El NPC recorre la ruta con la cámara siguiéndolo.'),
    'reiniciar': ('Reiniciar', None, 'Limpia puntos, ruta y obstáculos.'),
    'auto': ('Generación automática', 'P', 'Hace aparecer obstáculos mientras el NPC camina.'),
    'agregar': ('Agregar obstáculo', 'Q', 'Coloca un obstáculo sobre la ruta pendiente.'),
    'limpiar': ('Limpiar obstáculos', 'X', 'Retira todos los obstáculos dinámicos.'),
    'v_binaria': ('Vista binaria', 'G', 'Transitable (verde) y bloqueado (rojo).'),
    'v_validas': ('Posiciones válidas', 'V', 'Nodos del grafo; naranja = bloqueo dinámico.'),
    'v_hitbox': ('Hitbox de los pies', 'H', 'Muestra el rectángulo de colisión de 15 × 7.'),
    'v_zonas': ('Zonas de bloqueo', 'B', 'Zona que invalida cada obstáculo con la hitbox.'),
    'subgrafo': ('Subgrafo', None, 'Nodos y conexiones de una región del mapa.'),
    'comparar': ('Comparar algoritmos', 'C', 'Ejecuta los tres sobre el mismo escenario.'),
    'informe': ('Informe', 'I', 'Resultados, historial y exportación CSV.'),
}


class BarraLateral:
    """Panel derecho: flujo, algoritmo, acciones, obstaculos, vistas y metricas."""
    ANCHO = 320
    PAD = 16

    def __init__(self, x, alto, estado, accion, habilitado, razon):
        self.x, self.alto = x, alto
        self.estado, self.accion, self.habilitado, self.razon = estado, accion, habilitado, razon
        self.scroll = 0
        self.lienzo = None
        self.rects = {}
        self.pulsado = None
        self.sobre = None
        self.t_sobre = 0
        self._disponer()

    # ------------------------------------------------ geometria (una sola vez)
    def _disponer(self):
        x, w = self.x + self.PAD, self.ANCHO - 2 * self.PAD
        R, r = self.rects, pygame.Rect
        R['config'] = r(self.x + self.ANCHO - self.PAD - 36, 16, 36, 36)
        self.estado_rect = r(x, 64, w, 80)
        self.flujo_y = 156
        for i in range(3):
            R[f'alg:{i}'] = r(x, 252 + i * 38, w, 34)
        R['ejecutar'] = r(x, 376, w, 42)
        R['animar'] = r(x, 426, 188, 36)
        R['reiniciar'] = r(x + 196, 426, w - 196, 36)
        R['auto'] = r(x, 496, w, 36)
        R['agregar'] = r(x, 540, (w - 8) // 2, 34)
        R['limpiar'] = r(x + (w - 8) // 2 + 8, 540, (w - 8) // 2, 34)
        for i, n in enumerate(('v_binaria', 'v_validas', 'v_hitbox', 'v_zonas')):
            R[n] = r(x + i * ((w - 18) // 4 + 6), 628, (w - 18) // 4, 28)
        for i, n in enumerate(('subgrafo', 'comparar', 'informe')):
            R[n] = r(x + i * ((w - 12) // 3 + 6), 684, (w - 12) // 3, 34)
        self.tarjetas = [r(x + c * (w // 2 + 4), 760 + f * 46, w // 2 - 4, 40)
                         for c in range(2) for f in range(3)]

    # ------------------------------------------------ interaccion
    def redimensionar(self, x, alto):
        self.x, self.alto = x, alto
        self.pulsado = None
        self.lienzo = None
        self._disponer()
        self.desplazar(0)

    def desplazar(self, delta):
        self.scroll = max(0, min(max(0, 908 - self.alto), self.scroll + delta))
        self.pulsado = None
        self.sobre = None

    def nombre_en(self, pos):
        if not (self.x <= pos[0] < self.x + self.ANCHO and 0 <= pos[1] < self.alto):
            return None
        return self._nombre_contenido((pos[0], pos[1] + self.scroll))

    def _nombre_contenido(self, pos):
        for n, rect in self.rects.items():
            if rect.collidepoint(pos):
                return n
        return None

    def contiene(self, pos):
        return pos[0] >= self.x

    def mano(self, pos):
        n = self.nombre_en(pos)
        return bool(n) and self.habilitado(n)

    def presionar(self, pos):
        n = self.nombre_en(pos)
        self.pulsado = n if n and self.habilitado(n) else None

    def soltar(self, pos):
        n, self.pulsado = self.pulsado, None
        if n and self.nombre_en(pos) == n and self.habilitado(n):
            self.accion(n)
            return n
        return None

    # ------------------------------------------------ dibujo
    def _boton(self, s, n, label, estilo='sec', clave=None, mouse=(0, 0)):
        rect = self.rects[n]
        ok = self.habilitado(n)
        sobre = ok and rect.collidepoint(mouse)
        pres = ok and self.pulsado == n
        if estilo == 'prim' and ok:
            color = ACCENT_PRESS if pres else ACCENT_HOVER if sobre else ACCENT
            ink, borde = INK, None
        else:
            color = CARD_OFF if not ok else CARD_PRESS if pres else CARD_HOVER if sobre else CARD
            ink, borde = (TEXT if ok else DIM), (BORDER if not sobre else ACCENT)
        box(s, rect, color, 10, borde)
        text_centrado(s, label, rect, ink, 14, True)
        if clave:
            f = font(10, True)
            k = f.render(clave, True, INK if estilo == 'prim' and ok else MUTED)
            kr = k.get_rect(midright=(rect.right - 12, rect.centery)).inflate(10, 5)
            fondo = pygame.Surface(kr.size, pygame.SRCALPHA)
            pygame.draw.rect(fondo, (0, 0, 0, 38), fondo.get_rect(), border_radius=5)
            s.blit(fondo, kr.topleft)
            s.blit(k, k.get_rect(center=kr.center))

    def dibujar(self, s, mouse, ahora):
        # Blit 1:1: desplazar el contenido sin reescalar fuentes ni controles.
        tam = (self.x + self.ANCHO, max(908, self.alto))
        if self.lienzo is None or self.lienzo.get_size() != tam:
            self.lienzo = pygame.Surface(tam).convert()
        self.lienzo.fill(PANEL)
        self._dibujar_contenido(self.lienzo, (mouse[0], mouse[1] + self.scroll), ahora)
        s.blit(self.lienzo, (self.x, 0), (self.x, self.scroll, self.ANCHO, self.alto))
        if self.alto < 908:
            alto_barra = max(24, self.alto * self.alto // 908)
            y = round(self.scroll * (self.alto - alto_barra) / (908 - self.alto))
            pygame.draw.rect(s, BORDER, (self.x + self.ANCHO - 6, 0, 4, self.alto), border_radius=2)
            pygame.draw.rect(s, ACCENT, (self.x + self.ANCHO - 6, y, 4, alto_barra), border_radius=2)

        self._dibujar_ayuda(s, mouse, ahora)

    def _dibujar_contenido(self, s, mouse, ahora):
        e = self.estado()
        x, w = self.x + self.PAD, self.ANCHO - 2 * self.PAD
        pygame.draw.rect(s, PANEL, (self.x, 0, self.ANCHO, self.alto))
        pygame.draw.line(s, BORDER, (self.x, 0), (self.x, self.alto))
        # encabezado
        marca_logo(s, x, 18)
        text(s, 'NPC PathFinder', (x + 38, 14), TEXT, 18, True)
        text(s, 'Navegación en bosque', (x + 38, 38), MUTED, 11)
        rc = self.rects['config']
        boton_configuracion(s, rc, hover=rc.collidepoint(mouse), pressed=self.pulsado == 'config')
        # estado
        er = self.estado_rect
        box(s, er, CARD, 12)
        color = {'espera': MUTED, 'listo': ACCENT, 'completado': ACCENT, 'recorriendo': ACCENT,
                 'preparando': AMBER, 'replanificando': AMBER, 'buscando': BLUE,
                 'comparando': BLUE, 'sin_ruta': DANGER}.get(e['estado_clave'], MUTED)
        pygame.draw.circle(s, color, (er.x + 18, er.y + 20), 5)
        text(s, e['estado_texto'], (er.x + 32, er.y + 10), color, 14, True, width=er.w - 44)
        for i, linea in enumerate(ajustar(e['mensaje'], 12, er.w - 28, max_lineas=3)):
            text(s, linea, (er.x + 14, er.y + 34 + i * 15), MUTED, 12)
        # flujo
        etiqueta_seccion(s, x, self.flujo_y, 'Flujo')
        nombres = ('Puntos', 'Búsqueda', 'Recorrido')
        centros = [x + 40 + i * (w - 80) // 2 for i in range(3)]
        cy = self.flujo_y + 34
        for i in range(2):
            hecho = e['pasos'][i] == 'hecho'
            pygame.draw.line(s, ACCENT if hecho else BORDER, (centros[i] + 16, cy), (centros[i + 1] - 16, cy), 2)
        for i, (c, n) in enumerate(zip(centros, nombres)):
            st = e['pasos'][i]
            if st == 'hecho':
                pygame.draw.circle(s, ACCENT, (c, cy), 12)
                pygame.draw.lines(s, INK, False, [(c - 5, cy), (c - 1, cy + 4), (c + 6, cy - 4)], 2)
            elif st == 'activo':
                pygame.draw.circle(s, BG, (c, cy), 12)
                pygame.draw.circle(s, ACCENT, (c, cy), 12, 2)
                text_centrado(s, str(i + 1), pygame.Rect(c - 12, cy - 12, 24, 24), ACCENT, 13, True)
            else:
                pygame.draw.circle(s, BORDER, (c, cy), 12, 1)
                text_centrado(s, str(i + 1), pygame.Rect(c - 12, cy - 12, 24, 24), DIM, 13)
            text_centrado(s, n, pygame.Rect(c - 40, cy + 15, 80, 18), TEXT if st != 'pendiente' else DIM, 11, st == 'activo')
        # algoritmo
        etiqueta_seccion(s, x, 232, 'Algoritmo')
        for i, nombre in enumerate(e['algoritmos']):
            n, rect = f'alg:{i}', self.rects[f'alg:{i}']
            ok = self.habilitado(n)
            sel = nombre == e['alg_sel']
            sobre = ok and rect.collidepoint(mouse)
            fondo = (44, 67, 54) if sel else CARD_HOVER if sobre else CARD if ok else CARD_OFF
            box(s, rect, fondo, 10, ACCENT if sel else BORDER)
            pygame.draw.circle(s, ACCENT if sel else (BORDER if ok else CARD), (rect.x + 18, rect.centery), 7, 0 if sel else 1)
            if sel:
                pygame.draw.circle(s, INK, (rect.x + 18, rect.centery), 3)
            text(s, nombre, (rect.x + 36, rect.y + 8), TEXT if ok or sel else DIM, 14, sel, width=rect.w - 110)
            tag = ETIQUETAS_ALGORITMO.get(nombre)
            if tag:
                pastilla(s, pygame.Rect(rect.right - 70, rect.y + 7, 58, 20), tag[0], tag[1] if ok or sel else DIM, 10)
        # acciones principales
        self._boton(s, 'ejecutar', 'Ejecutar búsqueda', 'prim', 'Enter', mouse)
        self._boton(s, 'animar', 'Animar recorrido', 'sec', None, mouse)
        self._boton(s, 'reiniciar', 'Reiniciar', 'sec', None, mouse)
        # obstaculos
        etiqueta_seccion(s, x, 478, 'Obstáculos dinámicos')
        ra = self.rects['auto']
        sobre = ra.collidepoint(mouse)
        box(s, ra, CARD_PRESS if self.pulsado == 'auto' else CARD_HOVER if sobre else CARD, 10, ACCENT if sobre else BORDER)
        text(s, 'Generación automática', (ra.x + 14, ra.y + 9), TEXT, 14)
        interruptor(s, ra, e['auto'])
        self._boton(s, 'agregar', '+ Agregar', 'sec', 'Q', mouse)
        self._boton(s, 'limpiar', 'Limpiar', 'sec', 'X', mouse)
        text(s, f"Activos {e['activos']}   ·   Generados {e['generados']}   ·   Replanificaciones {e['replans']}",
             (x, 584), MUTED, 11, width=w)
        # vistas
        etiqueta_seccion(s, x, 610, 'Vista del mapa')
        for n, label, clave in (('v_binaria', 'Binaria', 'binaria'), ('v_validas', 'Válidas', 'validas'),
                                ('v_hitbox', 'Hitbox', 'hitbox'), ('v_zonas', 'Zonas', 'zonas')):
            rect, on = self.rects[n], e['vistas'][clave]
            sobre = rect.collidepoint(mouse)
            box(s, rect, (44, 67, 54) if on else CARD_HOVER if sobre else CARD, 14, ACCENT if on or sobre else BORDER)
            text_centrado(s, label, rect, ACCENT if on else TEXT, 12, on)
        # herramientas
        etiqueta_seccion(s, x, 666, 'Herramientas')
        self._boton(s, 'subgrafo', 'Subgrafo', 'sec', None, mouse)
        self._boton(s, 'comparar', 'Comparar', 'sec', None, mouse)
        self._boton(s, 'informe', 'Informe', 'sec', None, mouse)
        # metricas
        etiqueta_seccion(s, x, 738, e['titulo_busqueda'])
        etiqueta_seccion(s, x + w // 2 + 4, 738, e['titulo_navegacion'])
        valores = e['metricas_busqueda'] + e['metricas_navegacion']
        for rect, (label, valor) in zip(self.tarjetas, valores):
            box(s, rect, CARD, 9)
            text(s, label, (rect.x + 10, rect.y + 4), MUTED, 10, width=rect.w - 16)
            text(s, valor, (rect.x + 10, rect.y + 17), TEXT, 16, True, width=rect.w - 16)
    def _dibujar_ayuda(self, s, mouse, ahora):
        # La ayuda pertenece a la ventana, no al lienzo recortado del panel.
        e = self.estado()
        n = self.nombre_en(mouse)
        if n != self.sobre:
            self.sobre, self.t_sobre = n, ahora
        if n and ahora - self.t_sobre > 450:
            if n.startswith('alg:'):
                nombre = e['algoritmos'][int(n[4:])]
                tip = ETIQUETAS_ALGORITMO.get(nombre, ('', None, ''))[2]
                datos = (nombre, None, tip)
            else:
                datos = AYUDA_BOTONES.get(n)
            if datos:
                motivo = None if self.habilitado(n) else self.razon(n)
                tooltip(s, (self.rects[n].left, self.rects[n].bottom - self.scroll), datos[0], datos[1], datos[2], motivo)


# ---------------------------------------------------------------- ventana de configuracion
class Configuracion:
    OPCIONES_TAMANO = (('Pequeno', 'Pequeño'), ('Mediano', 'Mediano'), ('Grande', 'Grande'), ('Mixto', 'Mixto'))
    OPCIONES_SIN_RUTA = (('retirar', 'Retirar obstáculo'), ('detener', 'Detener recorrido'))

    def __init__(self, estado, accion, habilitado, cambiar):
        self.estado, self.accion, self.habilitado, self.cambiar = estado, accion, habilitado, cambiar
        self.ventana = pygame.Window('NPC PathFinder | Configuración', size=(760, 700))
        self.controles = {
            'Obstaculos auto': pygame.Rect(28, 126, 340, 44),
            'Zonas bloqueo': pygame.Rect(390, 126, 340, 44),
            'Limpiar obstaculos': pygame.Rect(390, 184, 340, 40),
        }
        self.sliders = {
            'cfg_cada_pasos': (pygame.Rect(240, 294, 420, 6), 50, 1000, 50, 'Frecuencia (pasos)'),
            'cfg_maximo': (pygame.Rect(240, 352, 420, 6), 1, 30, 1, 'Máximo de obstáculos'),
            'cfg_radio_deteccion': (pygame.Rect(240, 410, 420, 6), 5, 100, 5, 'Detección (pasos)'),
        }
        self.segmentos = {
            'cfg_tamano': (pygame.Rect(240, 468, 490, 40), self.OPCIONES_TAMANO, 'Tamaño'),
            'cfg_sin_ruta': (pygame.Rect(240, 524, 490, 40), self.OPCIONES_SIN_RUTA, 'Si no hay camino'),
        }
        self.semilla = pygame.Rect(240, 592, 260, 40)
        self.aplicar = pygame.Rect(520, 592, 140, 40)
        self.editando = False
        self.buffer = str(estado()['cfg_semilla'])
        self.arrastre = None
        self.ultimo = 0
        self.dibujar()

    def _celdas(self, rect, n):
        ancho = rect.w / n
        return [pygame.Rect(round(rect.x + i * ancho), rect.y, round(ancho) - 2, rect.h) for i in range(n)]

    def dibujar(self):
        s = self.ventana.get_surface(); e = self.estado()
        mouse = pygame.mouse.get_pos()
        s.fill(BG)
        text(s, 'Configuración', (28, 24), size=26, bold=True)
        text(s, 'Ajusta el escenario. Los obstáculos aparecen siempre sobre la ruta.', (28, 63), MUTED)
        text(s, 'OBSTÁCULOS DINÁMICOS', (28, 99), ACCENT, 12, True)
        for key, rect in self.controles.items():
            label = {'Obstaculos auto': 'Generación automática', 'Zonas bloqueo': 'Mostrar zonas de bloqueo',
                     'Limpiar obstaculos': 'Limpiar obstáculos'}[key]
            on = e['aparicion_auto'] if key == 'Obstaculos auto' else e['mostrar_zonas_bloqueo'] if key == 'Zonas bloqueo' else None
            if on is None:
                button(s, rect, label, self.habilitado(key))
            else:
                box(s, rect)
                text(s, label, (rect.x + 12, rect.y + 12), size=14)
                interruptor(s, rect, on)
        text(s, 'En el mapa, pulsa Q para agregar', (28, 185), ACCENT, 14, True)
        text(s, 'un obstáculo durante el recorrido.', (28, 207), MUTED, 13)
        text(s, 'RITMO Y DETECCIÓN', (28, 253), ACCENT, 12, True)
        for key, (r, lo, hi, step, label) in self.sliders.items():
            value = e[key]; x = r.x + round((value - lo) / (hi - lo) * r.w)
            text(s, label, (28, r.y - 9), size=14)
            pygame.draw.rect(s, BORDER, r, border_radius=3)
            pygame.draw.rect(s, ACCENT, (r.x, r.y, max(1, x - r.x), r.h), border_radius=3)
            pygame.draw.circle(s, BG, (x, r.centery), 10)
            pygame.draw.circle(s, ACCENT, (x, r.centery), 8)
            text(s, value, (680, r.y - 9), ACCENT, 15, True)
        text(s, 'COMPORTAMIENTO', (28, 445), ACCENT, 12, True)
        for key, (r, opciones, label) in self.segmentos.items():
            text(s, label, (28, r.y + 10), size=14)
            for (valor, texto), celda in zip(opciones, self._celdas(r, len(opciones))):
                sel = e[key] == valor
                box(s, celda, (44, 67, 54) if sel else CARD_HOVER if celda.collidepoint(mouse) else CARD, 9,
                    ACCENT if sel else BORDER)
                text_centrado(s, texto, celda, ACCENT if sel else TEXT, 13, sel)
        text(s, 'Semilla aleatoria', (28, 603), size=14)
        box(s, self.semilla)
        if self.editando:
            pygame.draw.rect(s, ACCENT, self.semilla, 2, border_radius=9)
        text(s, self.buffer if self.editando else e['cfg_semilla'], (252, 602), width=235)
        button(s, self.aplicar, 'Aplicar', hover=self.aplicar.collidepoint(mouse))
        text(s, 'ESC cierra esta ventana. La aplicación continúa funcionando.', (28, 662), MUTED, 13)
        self.ventana.flip()

    def mover_slider(self, key, x):
        r, lo, hi, step, _ = self.sliders[key]
        value = lo + round(max(0, min(1, (x - r.x) / r.w)) * (hi - lo) / step) * step
        self.cambiar(key, max(lo, min(hi, value)))

    def evento(self, event):
        if event.type == pygame.WINDOWCLOSE or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            self.ventana.destroy(); return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.editando = self.semilla.collidepoint(event.pos)
            if self.editando:
                self.buffer = str(self.estado()['cfg_semilla'])
            elif self.aplicar.collidepoint(event.pos) and self.buffer.isdigit():
                self.cambiar('cfg_semilla', int(self.buffer))
            for key, rect in self.controles.items():
                if rect.collidepoint(event.pos) and self.habilitado(key):
                    self.accion(key)
            for key, (r, opciones, _) in self.segmentos.items():
                for (valor, _), celda in zip(opciones, self._celdas(r, len(opciones))):
                    if celda.collidepoint(event.pos):
                        self.cambiar(key, valor)
            for key, (r, *_) in self.sliders.items():
                if r.inflate(20, 30).collidepoint(event.pos):
                    self.arrastre = key; self.mover_slider(key, event.pos[0])
        if event.type == pygame.MOUSEMOTION and self.arrastre:
            self.mover_slider(self.arrastre, event.pos[0])
        if event.type in (pygame.MOUSEBUTTONUP, pygame.WINDOWFOCUSLOST):
            self.arrastre = None
        if event.type == pygame.KEYDOWN and self.editando:
            if event.key == pygame.K_BACKSPACE:
                self.buffer = self.buffer[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.buffer.isdigit():
                self.cambiar('cfg_semilla', int(self.buffer)); self.editando = False
            elif getattr(event, 'unicode', '').isdigit() and len(self.buffer) < 12:
                self.buffer += event.unicode
        self.dibujar(); return True

    def refrescar(self):
        now = pygame.time.get_ticks()
        if now - self.ultimo > 150:
            self.ultimo = now; self.dibujar()