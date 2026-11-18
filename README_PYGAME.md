# NPC PathFinder: visor Pygame

Usar Python 3.12 (entorno comprobado). Desde la carpeta del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe visor_pygame.py
```

Si `py` no está disponible, usar la ruta al ejecutable de Python 3.12 para crear
el entorno. El Python predeterminado detectado durante el desarrollo era 3.14;
no se comprobó Pygame 2.6.1 con esa versión.

## Controles

- Rueda del ratón: acercar/alejar alrededor del cursor.
- Arrastrar con botón izquierdo, central o derecho: desplazar la cámara.
- Flechas o WASD: desplazar; R: volver al mapa completo; Esc: cerrar.
- Pasar el cursor por una celda: consultar fila, columna, símbolo y transitabilidad.

El visor abre el mapa completo. Las dimensiones lógicas son 512 filas por 512
columnas, no 512 píxeles de ventana. Cada celda tiene una tesela de 8x8 píxeles;
la cámara adapta su escala sin modificar el dataset. Las coordenadas del grafo
son `(fila, columna)`, y la pantalla usa `x=columna`, `y=fila`, con origen arriba
a la izquierda. Los marcadores mantienen inicio `(100, 200)` y objetivo `(420, 300)`.

## Separación de responsabilidades

- `logica_pathfinding.py`: lectura, matriz, grafo, BFS y A*, trasladados sin cambiar
  sus implementaciones.
- `terrenos.py`: texturas deterministas compartidas. No controla colisiones.
- `visor_pygame.py`: cámara, entradas y renderizado; no ejecuta búsquedas.
- `NPC_PathFinder.py`: conserva el flujo de BFS/A* y las exportaciones Matplotlib.
  Puede importarse sin abrir ventanas ni ejecutar búsquedas.

Para los informes ejecutar `.\.venv\Scripts\python.exe NPC_PathFinder.py`.
Las imágenes se guardan en el directorio de ejecución, como antes.

## Fidelidad y recursos

El mapa contiene `.` (99 759), `T` (62 568), `W` (8 683) y `@` (91 134).
No contiene `O`, `S`, `G` ni símbolos desconocidos. Solo `.` es transitable en
el modelo actual. Bosque, agua y exterior continúan bloqueados. `G` y `S`, si
se usan otros mapas, seguirían bloqueados por la lógica actual: las texturas
no corrigen ni sustituyen las reglas de navegación.

Se reutiliza pixel art procedural del proyecto, sin descargar recursos externos.
No se inventan caminos: el dataset no tiene un símbolo separado para senderos.
La imagen original se construye una vez; para el zoom se escala únicamente
el recorte visible con `pygame.transform.scale`, sin suavizado. Al alejarse se
pierde detalle visual por resolución, pero no desaparecen celdas de los datos.
No hay NPC móvil ni simulación de colisiones: el estado consultado procede de
la misma matriz de transitabilidad usada por los algoritmos, nunca de colores.
