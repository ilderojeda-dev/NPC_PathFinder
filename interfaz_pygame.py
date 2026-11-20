"""Presentacion Pygame: tema y configuracion. Sin logica de busqueda."""
import pygame
import math

BG = (14, 24, 23)
PANEL = (20, 34, 31)
CARD = (29, 46, 41)
BORDER = (49, 71, 61)
TEXT = (236, 241, 226)
MUTED = (155, 176, 161)
ACCENT = (176, 219, 133)
INK = (24, 43, 28)
_fonts = {}


def font(size=15, bold=False):
    key = size, bold
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont('Segoe UI', size, bold=bold)
    return _fonts[key]


def text(surface, value, pos, color=TEXT, size=15, bold=False, width=None):
    value = str(value)
    f = font(size, bold)
    if width:
        while value and f.size(value)[0] > width:
            value = value[:-2].rstrip('.') + '...' if not value.endswith('...') else value[:-4] + '...'
            if len(value) <= 3:
                break
    surface.blit(f.render(value, True, color), pos)


def box(surface, rect, color=CARD, radius=12):
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    pygame.draw.rect(surface, BORDER, rect, 1, border_radius=radius)


def button(surface, rect, label, enabled=True, primary=False, active=False, hover=False):
    color = ACCENT if primary and enabled else ((44, 67, 54) if active or hover else CARD)
    if not enabled:
        color = (24, 35, 32)
    box(surface, rect, color, 9)
    f = font(14, True)
    ink = INK if primary and enabled else TEXT if enabled else (95, 115, 101)
    image = f.render(label, True, ink)
    surface.blit(image, image.get_rect(center=rect.center))


def boton_configuracion(surface, rect, hover=False):
    """Engranaje dibujado sin depender de fuentes con simbolos especiales."""
    button(surface, rect, "", hover=hover)
    cx, cy = rect.center
    puntos = []
    for i in range(32):
        angulo = i * math.tau / 32
        radio = 13 if i % 4 in (1, 2) else 10
        puntos.append((round(cx + math.cos(angulo)*radio), round(cy + math.sin(angulo)*radio)))
    pygame.draw.polygon(surface, ACCENT if hover else TEXT, puntos)
    pygame.draw.circle(surface, (44, 67, 54) if hover else CARD, (cx, cy), 5)
    if hover:
        tooltip = pygame.Rect(rect.right-130, rect.y-31, 130, 25)
        box(surface, tooltip, BG, 6)
        text(surface, "Configuracion", (tooltip.x+10, tooltip.y+4), size=12)


class Configuracion:
    def __init__(self, estado, accion, habilitado, cambiar):
        self.estado, self.accion, self.habilitado, self.cambiar = estado, accion, habilitado, cambiar
        self.ventana = pygame.Window('NPC PathFinder | Configuracion', size=(760, 660))
        self.controles = {
            'Obstaculos auto': pygame.Rect(28, 126, 340, 44),
            'Zonas bloqueo': pygame.Rect(390, 126, 340, 44),
            'Limpiar obstaculos': pygame.Rect(390, 184, 340, 40),
            'Tamano': pygame.Rect(28, 474, 340, 42),
            'Sin ruta': pygame.Rect(390, 474, 340, 42),
        }
        self.sliders = {
            'cfg_cada_pasos': (pygame.Rect(240, 294, 420, 6), 50, 1000, 50, 'Frecuencia (pasos)'),
            'cfg_maximo': (pygame.Rect(240, 352, 420, 6), 1, 30, 1, 'Maximo de obstaculos'),
            'cfg_radio_deteccion': (pygame.Rect(240, 410, 420, 6), 5, 100, 5, 'Deteccion (pasos)'),
        }
        self.semilla = pygame.Rect(240, 550, 260, 40)
        self.aplicar = pygame.Rect(520, 550, 140, 40)
        self.editando = False
        self.buffer = str(estado()['cfg_semilla'])
        self.arrastre = None
        self.ultimo = 0
        self.dibujar()

    def dibujar(self):
        s = self.ventana.get_surface(); e = self.estado()
        s.fill(BG)
        text(s, 'Configuracion', (28, 24), size=26, bold=True)
        text(s, 'Ajusta el escenario. Los obstaculos aparecen siempre sobre la ruta.', (28, 63), MUTED)
        text(s, 'OBSTACULOS DINAMICOS', (28, 99), ACCENT, 12, True)
        for key, rect in self.controles.items():
            label = {'Obstaculos auto': 'Generacion automatica', 'Zonas bloqueo': 'Mostrar zonas de bloqueo',
                     'Tamano': 'Tamano: ' + e['cfg_tamano'], 'Sin ruta': 'Sin camino: ' + e['cfg_sin_ruta']}.get(key, key)
            on = e['aparicion_auto'] if key == 'Obstaculos auto' else e['mostrar_zonas_bloqueo'] if key == 'Zonas bloqueo' else None
            if on is None:
                button(s, rect, label, self.habilitado(key))
            else:
                box(s, rect)
                text(s, label, (rect.x+12,rect.y+12),size=14)
                track = pygame.Rect(rect.right-58,rect.y+12,42,22)
                pygame.draw.rect(s, ACCENT if on else BORDER, track, border_radius=11)
                pygame.draw.circle(s, INK if on else MUTED,(track.right-11 if on else track.x+11,track.centery),8)
        text(s, 'En el mapa, pulsa Q para agregar', (28, 185), ACCENT, 14, True)
        text(s, 'un obstaculo durante el recorrido.', (28, 207), MUTED, 13)
        text(s, 'RITMO Y DETECCION', (28, 253), ACCENT, 12, True)
        for key,(r,lo,hi,step,label) in self.sliders.items():
            value=e[key]; x=r.x+round((value-lo)/(hi-lo)*r.w)
            text(s,label,(28,r.y-9),size=14)
            pygame.draw.rect(s,BORDER,r,border_radius=3)
            pygame.draw.rect(s,ACCENT,(r.x,r.y,max(1,x-r.x),r.h),border_radius=3)
            pygame.draw.circle(s,ACCENT,(x,r.centery),8)
            text(s,value,(680,r.y-9),ACCENT,15,True)
        text(s,'COMPORTAMIENTO',(28,445),ACCENT,12,True)
        text(s,'Semilla aleatoria',(28,561),size=14)
        box(s,self.semilla)
        if self.editando:pygame.draw.rect(s,ACCENT,self.semilla,2,border_radius=9)
        text(s,self.buffer if self.editando else e['cfg_semilla'],(252,560),width=235)
        button(s,self.aplicar,'Aplicar')
        text(s,'ESC cierra esta ventana. La aplicacion continua funcionando.',(28,625),MUTED,13)
        self.ventana.flip()

    def mover_slider(self,key,x):
        r,lo,hi,step,_=self.sliders[key]
        value=lo+round(max(0,min(1,(x-r.x)/r.w))*(hi-lo)/step)*step
        self.cambiar(key,max(lo,min(hi,value)))

    def evento(self,event):
        if event.type==pygame.WINDOWCLOSE or (event.type==pygame.KEYDOWN and event.key==pygame.K_ESCAPE):
            self.ventana.destroy();return False
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            self.editando=self.semilla.collidepoint(event.pos)
            if self.editando:self.buffer=str(self.estado()['cfg_semilla'])
            elif self.aplicar.collidepoint(event.pos) and self.buffer.isdigit():self.cambiar('cfg_semilla',int(self.buffer))
            for key,rect in self.controles.items():
                if rect.collidepoint(event.pos) and self.habilitado(key):self.accion(key)
            for key,(r,*_) in self.sliders.items():
                if r.inflate(20,30).collidepoint(event.pos):
                    self.arrastre=key;self.mover_slider(key,event.pos[0])
        if event.type==pygame.MOUSEMOTION and self.arrastre:self.mover_slider(self.arrastre,event.pos[0])
        if event.type in (pygame.MOUSEBUTTONUP,pygame.WINDOWFOCUSLOST):self.arrastre=None
        if event.type==pygame.KEYDOWN and self.editando:
            if event.key==pygame.K_BACKSPACE:self.buffer=self.buffer[:-1]
            elif event.key in (pygame.K_RETURN,pygame.K_KP_ENTER) and self.buffer.isdigit():
                self.cambiar('cfg_semilla',int(self.buffer));self.editando=False
            elif getattr(event,'unicode','').isdigit() and len(self.buffer)<12:self.buffer+=event.unicode
        self.dibujar();return True

    def refrescar(self):
        now=pygame.time.get_ticks()
        if now-self.ultimo>150:self.ultimo=now;self.dibujar()
