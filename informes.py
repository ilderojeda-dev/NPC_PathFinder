"""Presentacion de informes, historiales y exportacion CSV."""

import csv
import pygame
import interfaz_pygame as ui

class VentanaInforme:
    """Informe individual seleccionable o comparacion estatica independiente."""

    def __init__(self, app, comparacion=False):
        self.app = app
        self.ventana = pygame.Window('Informes NPC PathFinder', size=(1120, 760))
        self.comparacion = comparacion
        self.indice = max(0, len(self.app.historial_sesiones) - 1)
        self.indice_comparacion = max(0, len(self.app.historial_comparaciones) - 1)
        self.scroll = 0
        self.aviso = ''
        self.ultimo = pygame.time.get_ticks()
        self.dibujar()

    def comparacion_seleccionada(self):
        return self.app.historial_comparaciones[self.indice_comparacion] if self.app.historial_comparaciones else None

    def navegacion_habilitada(self, direccion):
        historial = self.app.historial_comparaciones if self.comparacion else self.app.historial_sesiones
        indice = self.indice_comparacion if self.comparacion else self.indice
        return bool(historial) and 0 <= indice + direccion < len(historial)

    def navegar(self, direccion):
        if not self.navegacion_habilitada(direccion):
            return
        if self.comparacion:
            self.indice_comparacion += direccion
        else:
            self.indice += direccion
            self.scroll = 0
        self.aviso = ''
    FILAS_VISIBLES = 20

    @staticmethod
    def formato(valor):
        if isinstance(valor, bool):
            return str(valor)
        if isinstance(valor, int):
            return f'{valor:,}'
        if isinstance(valor, float):
            return f'{valor:.6f}'
        return ui.acentuar(valor)

    def dibujar(self):
        sup = self.ventana.get_surface()
        sup.fill(ui.BG)
        mouse = pygame.mouse.get_pos()
        ui.text(sup, 'Resultados', (26, 18), size=27, bold=True)
        ui.text(sup, 'NPC PATHFINDER / ANÁLISIS', (26, 55), ui.MUTED, 11, True)
        self.acciones_ui = {pygame.K_i: pygame.Rect(435, 24, 150, 36),
            pygame.K_c: pygame.Rect(595, 24, 150, 36),
            pygame.K_s: pygame.Rect(755, 24, 140, 36),
            pygame.K_LEFT: pygame.Rect(915, 24, 80, 36),
            pygame.K_RIGHT: pygame.Rect(1005, 24, 80, 36)}
        for key, rect in self.acciones_ui.items():
            label = {pygame.K_i: 'Individual',
                pygame.K_c: 'Comparación',
                pygame.K_s: 'Exportar CSV',
                pygame.K_LEFT: 'Anterior',
                pygame.K_RIGHT: 'Siguiente'}[key]
            habilitado = self.navegacion_habilitada(-1) if key == pygame.K_LEFT else self.navegacion_habilitada(1) if key == pygame.K_RIGHT else True
            ui.button(sup,
                rect,
                label,
                enabled=habilitado,
                primary=key == pygame.K_s,
                active=key == pygame.K_c and self.comparacion or (key == pygame.K_i and (not self.comparacion)),
                hover=habilitado and rect.collidepoint(mouse))
        if self.comparacion:
            self.dibujar_comparacion(sup)
        else:
            self.dibujar_individual(sup)
        self.iniciar_comparacion_rect = pygame.Rect(866, 679, 220, 38)
        if self.comparacion:
            ui.button(sup,
                self.iniciar_comparacion_rect,
                'Iniciar comparación',
                enabled=self.app.boton_habilitado('Comparar busquedas'),
                primary=True,
                hover=self.iniciar_comparacion_rect.collidepoint(mouse))
        ui.text(sup,
            ui.acentuar(self.aviso) or 'S: exportar   /   Esc: cerrar esta ventana',
            (26, 729),
            ui.MUTED,
            13,
            width=1060)
        self.ventana.flip()

    def dibujar_comparacion(self, sup):
        registro = self.comparacion_seleccionada() or {}
        ui.text(sup,
            f"COMPARACIÓN {registro.get('id', '--')}  /  {ui.acentuar(registro.get('estado', 'Sin ejecutar'))}",
            (26, 100),
            ui.ACCENT,
            13,
            True)
        ui.text(sup,
            f"Inicio {registro.get('inicio')}   -   Destino {registro.get('destino')}",
            (26, 129),
            ui.MUTED)
        xs = (42, 280, 540, 800)
        ui.box(sup, pygame.Rect(26, 175, 1060, 44))
        for x, t in zip(xs, ('ALGORITMO', 'TIEMPO DE BÚSQUEDA', 'NODOS EXPLORADOS', 'NODOS DE LA RUTA')):
            ui.text(sup, t, (x, 190), ui.MUTED, 12, True)
        resultados = registro.get('resultados', [])
        con_tiempo = [r for r in resultados if r.get('nodos_ruta') is not None]
        mejor_t = min((r['tiempo'] for r in con_tiempo), default=None)
        mejor_n = min((r['expandidos'] for r in con_tiempo), default=None)
        mejor_l = min((r['nodos_ruta'] for r in con_tiempo), default=None)
        max_t = max((r['tiempo'] for r in resultados), default=1) or 1e-09
        max_n = max((r['expandidos'] for r in resultados), default=1) or 1
        for i, r in enumerate(resultados):
            y = 231 + i * 68
            ui.box(sup, pygame.Rect(26, y, 1060, 58))
            ui.text(sup, r['algoritmo'], (xs[0], y + 12), size=18, bold=True)
            ui.text(sup, f"{r['tiempo']:.6f} s", (xs[1], y + 12), size=18, bold=True)
            ui.text(sup, f"{r['expandidos']:,}", (xs[2], y + 12), size=18, bold=True)
            ui.text(sup,
                'Sin ruta' if r['nodos_ruta'] is None else f"{r['nodos_ruta']:,}",
                (xs[3], y + 12),
                size=18,
                bold=True)
            for x, frac, mejor in ((xs[1], r['tiempo'] / max_t, mejor_t is not None and len(con_tiempo) > 1 and (r['tiempo'] == mejor_t)),
                (xs[2], r['expandidos'] / max_n, mejor_n is not None and len(con_tiempo) > 1 and (r['expandidos'] == mejor_n))):
                pygame.draw.rect(sup, ui.BORDER, (x, y + 43, 200, 5), border_radius=3)
                pygame.draw.rect(sup,
                    ui.ACCENT if mejor else (90, 126, 104),
                    (x, y + 43, max(6, int(200 * frac)), 5),
                    border_radius=3)
            if mejor_l is not None and len(con_tiempo) > 1 and (r['nodos_ruta'] == mejor_l) and any((o['nodos_ruta'] not in (None,
                mejor_l) for o in resultados)):
                ui.pastilla(sup, pygame.Rect(xs[3] + 84, y + 14, 96, 20), 'Ruta más corta', ui.ACCENT, 10)
            if mejor_t is not None and len(con_tiempo) > 1 and (r['tiempo'] == mejor_t) and (r['nodos_ruta'] is not None):
                ui.pastilla(sup, pygame.Rect(xs[1] + 128, y + 14, 78, 20), 'Más rápido', ui.ACCENT, 10)
            if mejor_n is not None and len(con_tiempo) > 1 and (r['expandidos'] == mejor_n) and (r['nodos_ruta'] is not None):
                ui.pastilla(sup, pygame.Rect(xs[2] + 128, y + 14, 84, 20), 'Menos nodos', ui.ACCENT, 10)
        ui.text(sup,
            'Explorados = expansiones. En BFS Bidireccional se suman ambos extremos.',
            (26, 610),
            ui.MUTED,
            13)
        ui.text(sup,
            f"ALT: preparación compartida {registro.get('preparacion_alt_s', 0):.3f} s, excluida de las búsquedas.",
            (26, 637),
            ui.MUTED,
            13)

    def dibujar_individual(self, sup):
        ses = self.app.historial_sesiones[self.indice] if self.app.historial_sesiones else None
        if ses is None:
            ui.box(sup, pygame.Rect(26, 100, 1060, 120))
            ui.text(sup, 'Todavía no hay ejecuciones.', (56, 132), ui.TEXT, 18, True)
            ui.text(sup,
                'Ejecuta una búsqueda en la ventana principal y vuelve aquí para ver el resultado.',
                (56, 164),
                ui.MUTED,
                14)
            return
        ini = ses['inicial']
        tarjetas = (('Algoritmo', ses['algoritmo']),
            ('Búsqueda inicial', '--' if ini is None else f"{ini['tiempo']:.4f} s"),
            ('Nodos expandidos', '--' if ini is None else f"{ini['expandidos']:,}"),
            ('Rutas creadas', str(len(ses['rutas']))))
        for i, (etiqueta, valor) in enumerate(tarjetas):
            r = pygame.Rect(26 + i * 268, 88, 256, 58)
            ui.box(sup, r, ui.CARD, 10)
            ui.text(sup, etiqueta, (r.x + 14, r.y + 7), ui.MUTED, 11)
            ui.text(sup, valor, (r.x + 14, r.y + 25), ui.TEXT, 18, True, width=r.w - 28)
        filas = self.app.informes.filas_informe(ses)
        visibles = self.FILAS_VISIBLES
        self.scroll = min(self.scroll, max(0, len(filas) - visibles))
        for i, (nombre, valor) in enumerate(filas[self.scroll:self.scroll + visibles]):
            y = 162 + i * 25
            seccion = nombre[:2] in ('A.', 'B.', 'C.', 'D.')
            if seccion:
                pygame.draw.rect(sup, ui.CARD, (26, y - 2, 1048, 24), border_radius=5)
            elif i % 2 == 0:
                pygame.draw.rect(sup, (18, 30, 27), (26, y - 2, 1048, 24), border_radius=3)
            ui.text(sup, ui.acentuar(nombre), (38, y), ui.ACCENT if seccion else ui.MUTED, 14, seccion)
            if isinstance(valor, tuple):
                nodos, tiempo = valor
                ui.text(sup, self.formato(nodos), (540, y), ui.TEXT, 13, True, width=300)
                ui.text(sup,
                    f'{tiempo:.6f} s' if isinstance(tiempo, float) else ui.acentuar(tiempo),
                    (865, y),
                    ui.TEXT,
                    13,
                    True,
                    width=205)
            else:
                ui.text(sup, self.formato(valor), (610, y), size=14, bold=True, width=450)
        if len(filas) > visibles:
            pista = pygame.Rect(1082, 160, 6, visibles * 25 - 4)
            pygame.draw.rect(sup, ui.BORDER, pista, border_radius=3)
            alto = max(24, int(pista.h * visibles / len(filas)))
            y0 = pista.y + int((pista.h - alto) * self.scroll / max(1, len(filas) - visibles))
            pygame.draw.rect(sup, ui.ACCENT, (pista.x, y0, pista.w, alto), border_radius=3)
        ui.text(sup,
            'Rueda del mouse: desplazarse   /   Anterior · Siguiente: cambiar de ejecución',
            (26, 690),
            ui.MUTED,
            13)

    def refrescar(self):
        if pygame.time.get_ticks() - self.ultimo > 500:
            self.ultimo = pygame.time.get_ticks()
            self.dibujar()

    def evento(self, evento):
        if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
            if self.comparacion and self.iniciar_comparacion_rect.collidepoint(evento.pos):
                if self.app.boton_habilitado('Comparar busquedas'):
                    self.app.comparacion.iniciar_comparacion()
                    self.comparacion = True
                    self.aviso = ''
                self.dibujar()
                return True
            for key, rect in getattr(self, 'acciones_ui', {}).items():
                if rect.collidepoint(evento.pos):
                    evento = pygame.event.Event(pygame.KEYDOWN, key=key)
                    break
        if evento.type == pygame.WINDOWCLOSE or (evento.type == pygame.KEYDOWN and evento.key == pygame.K_ESCAPE):
            self.ventana.destroy()
            return False
        if evento.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - evento.y * 3)
        if evento.type == pygame.KEYDOWN:
            if evento.key == pygame.K_c:
                self.comparacion = True
            elif evento.key == pygame.K_i:
                self.comparacion = False
            elif evento.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self.navegar(1 if evento.key == pygame.K_RIGHT else -1)
            elif evento.key == pygame.K_s:
                self.app.estadisticas_registro.actualizar_reloj_recorrido()
                ses = self.app.historial_sesiones[self.indice] if self.app.historial_sesiones else None
                self.aviso = self.app.informes.exportar_informe_csv(ses,
                    self.comparacion,
                    self.comparacion_seleccionada())
        self.dibujar()
        return True

class Informes:
    """Servicio con referencia a la aplicacion; no copia matrices ni mantiene globals."""

    def __init__(self, app):
        self.app = app

    def ms(self, t):
        return '--' if t is None else f'{t * 1000:.1f} ms'

    def filas_informe(self, ses):
        if ses is None:
            return [('Sin ejecuciones individuales', '')]
        ini = ses['inicial']
        valor = lambda clave: '--' if ini is None else ini[clave]
        filas = [('Ejecucion', str(ses['id'])),
            ('Algoritmo', ses['algoritmo']),
            ('Inicio / destino', f"{ses['inicio']} / {ses['destino']}"),
            ('A. Busqueda inicial', ''),
            ('Tiempo de busqueda inicial (s)', valor('tiempo')),
            ('Nodos descubiertos', valor('descubiertos')),
            ('Nodos expandidos', valor('expandidos')),
            ('Longitud inicial (movimientos)', valor('longitud')),
            ('B. Obstaculos dinamicos', ''),
            ('Total generados', ses['obstaculos']),
            ('Rocas', ses['tipos']['roca']),
            ('Arboles (arbustos del catalogo)', ses['tipos']['arbusto']),
            ('Palos (troncos del catalogo)', ses['tipos']['tronco']),
            ('C. Historial de rutas', '')]
        if 'ALT' in ses['algoritmo']:
            filas.insert(8,
                ('Preparacion ALT compartida (s, fuera de busqueda)', self.app.motor_pathfinding.alt.tiempo))
        filas.append(('Ruta', ('Nodos recorridos / nodos totales', 'Tiempo de busqueda')))
        for i, ruta in enumerate(ses['rutas']):
            nombre = 'Ruta inicial' if i == 0 else f'Ruta {i + 1}'
            filas.append((nombre,
                (f"{self.app.estadisticas_registro.nodos_recorridos_ruta(ruta)} / {ruta['nodos_totales']}", ruta['tiempo_busqueda'])))
        filas += [('Cantidad total de rutas creadas', len(ses['rutas'])),
            ('D. Recorrido completo', ''),
            ('Tiempo total de recorrido (s, incluye pausas)', ses['t_total']),
            ('Tiempo en movimiento (s)', ses['t_movimiento']),
            ('Tiempo detenido (s)', ses['t_detenido']),
            ('Pasos recorridos', ses['pasos']),
            ('Resultado final / estado actual', ses['resultado'])]
        return filas

    def exportar_informe_csv(self, ses=None, comparacion=False, registro_comparacion=None):
        if comparacion:
            registro = registro_comparacion if registro_comparacion is not None else self.app.contexto_comparacion
            if not registro:
                return 'No hay una comparacion seleccionada'
            ruta = self.app.CARPETA_DATOS / f"comparacion_busquedas_{self.app.IDENTIFICADOR_APERTURA}_{registro['id']}.csv"
            with open(ruta, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['algoritmo',
                    'tiempo_busqueda_s',
                    'nodos_explorados',
                    'nodos_ruta',
                    'estado',
                    'inicio',
                    'destino',
                    'criterio_nodos',
                    'preparacion_alt_s'])
                for r in registro['resultados']:
                    w.writerow([r['algoritmo'],
                        r['tiempo'],
                        r['expandidos'],
                        r['nodos_ruta'],
                        r['estado'],
                        registro['inicio'],
                        registro['destino'],
                        r['criterio_nodos'],
                        r['preparacion_alt_s']])
            return ruta.name
        if ses is None:
            return 'No hay una ejecucion seleccionada'
        ruta = self.app.CARPETA_DATOS / f"informe_individual_{self.app.IDENTIFICADOR_APERTURA}_{ses['id']}_{ses['algoritmo'].replace('*', 'star')}.csv"
        with open(ruta, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['metrica', 'valor', 'tiempo_busqueda_s'])
            for nombre, valor in self.filas_informe(ses):
                if isinstance(valor, tuple):
                    nodos, tiempo = valor
                    w.writerow([nombre, nodos, f'{tiempo:.6f}' if isinstance(tiempo, float) else tiempo])
                else:
                    w.writerow([nombre, valor, ''])
        return ruta.name

    def abrir_informe(self, comparacion=False):
        if self.app.informe_ventana is None:
            self.app.informe_ventana = VentanaInforme(self.app, comparacion)
        else:
            self.app.informe_ventana.comparacion = comparacion
            self.app.informe_ventana.scroll = 0
            self.app.informe_ventana.ventana.focus()
            self.app.informe_ventana.dibujar()
