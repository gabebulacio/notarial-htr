# Plan

Objetivo: transcripción diplomática casi perfecta de cada legajo, con el mínimo trabajo
humano posible y reutilizable en legajos nuevos de la misma época y tipo documental.
"Casi perfecta" significa revisada: el modelo llega a un CER bajo y una persona revisa los
tramos de baja confianza.

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Repo, configuración por colección, normas de transcripción | hecho |
| 1 | Ingesta del PDF y preproceso de imagen | hecho |
| 2 | Segmentación de regiones y líneas base (Kraken), filtro de página enfrentada, márgenes y rúbricas | en curso |
| 3 | Modelo base histórico (Kraken 7.x / McCATMuS) y ajuste a la mano del legajo | en curso |
| 4 | Rondas de corrección: 10, 20, 40 páginas, elegidas por baja confianza; conjunto de evaluación fijo | pendiente |
| 5 | Decodificación con léxico de época y nomenclátor (CTC word beam search) | pendiente |
| 6 | Confianza por palabra, calibrada sobre el conjunto de evaluación | pendiente |
| 7 | Ajustes con LLM acotados y extracción de registros (contrayentes, padres, testigos, fechas) | pendiente |
| 8 | Evaluación (CER/WER por etapa) y exportación (PAGE XML, TEI, JSON, índice SQLite) | pendiente |

## Hitos

Cada hito es un paso lógico que se puede revisar y probar por separado, y termina en un
commit. Los de la fase 0-1 ya están escritos; el resto se va cerrando en orden.

| # | Hito | Fase | Estado |
|---|---|---|---|
| H01 | Estructura del proyecto, configuración por colección y manifiestos | 0 | listo, sin commit |
| H02 | Ingesta del PDF y preproceso de imágenes con CLI y tests | 1 | listo, sin commit |
| H03 | Normas de transcripción, plan y README | 0 | listo, sin commit |
| H04 | Kraken como dependencia opcional y comando `htr segment` con el modelo base | 2 | listo, sin commit |
| H05 | Salida PAGE XML por página: original de Kraken y versión filtrada | 2 | listo, sin commit |
| H06 | Vista de control: superposición en imagen y visor HTML por capas con la decisión de cada regla | 2 | listo, sin commit |
| H07 | Filtro de página enfrentada, renglones duplicados y partidos; páginas sospechosas | 2 | primera versión |
| H07b | Detección del borde físico del papel; comando `htr refine` para reaplicar reglas sin Kraken | 2 | primera versión |
| H08 | Marginalia y rúbricas como regiones propias | 2 | |
| H09 | Reconocimiento con modelo base histórico (`htr recognize`, McCATMuS) | 3 | listo, sin commit |
| H10 | Editor local de correcciones (`htr correct`), guardado en `ground_truth/` | 4 | listo, sin commit |
| H11 | Conjunto de evaluación fijo (12 páginas) y métricas CER/WER (`htr evaluate`) | 4 | listo, sin commit |
| H12 | Ajuste fino: exportación a PAGE, `htr train` local y paquete para Kaggle | 3 | listo, sin commit |
| H13 | Primera ronda de corrección (10 páginas) y modelo ajustado v1 | 4 | |
| H14 | Selección de páginas por baja confianza para la ronda siguiente | 4 | |
| H15 | Rondas 2 y 3 (20 y 40 páginas), modelos v2 y v3 | 4 | |
| H16 | Léxico de época y nomenclátor de apellidos y lugares | 5 | |
| H17 | Decodificación CTC word beam search con el léxico | 5 | |
| H18 | Confianza por palabra y calibración | 6 | |
| H19 | Ajustes acotados con LLM, registro auditable y presupuesto | 7 | |
| H20 | Extracción de registros (contrayentes, padres, testigos, fechas) | 7 | |
| H21 | Exportación PAGE/TEI/JSON e índice de búsqueda SQLite | 8 | |
| H22 | Informe de evaluación por etapa | 8 | |
| H23 | Segunda colección como prueba de escalabilidad | 8 | |

## Notas de la fase 1

- Las imágenes son fotos de celular del libro abierto: entra la página enfrentada, el
  canto y a veces la etiqueta del lomo. Los renglones se curvan por la perspectiva.
- Por eso el enderezado global solo se aplica cuando la estimación es confiable (mejora
  clara frente a 0° y dentro del rango). En la corrida completa: 169 de 227 páginas
  confiables, 58 sin rotar. La geometría fina queda para la segmentación por renglón.
- No se detectaron páginas en blanco ni dobles páginas en esta colección; los detectores
  quedan para legajos futuros.

## Notas de la fase 2

- El CLAHE de la fase 1 empeoraba la segmentación (realza la textura del papel): quedó
  apagado por defecto. Con la imagen sin realzar, p0114 pasó de 42 a 38 renglones
  detectados por Kraken, con menos cortes y sin ruido en el borde superior.
- Aplanar el fondo (dividir por el fondo difuminado) saca las manchas de humedad pero
  deja los pliegues, y Kraken los toma por renglones (p0026: 197). Esas páginas se marcan
  `layout_suspect` y van a revisión manual de la segmentación.
- Reglas sobre la salida de Kraken: descartar restos cortos en la franja de borde,
  quitar renglones encimados sobre otro más largo y unir renglones partidos a la misma
  altura. En las muestras revisadas quedan errores chicos (un renglón duplicado en el
  hueco entre dos, un resto del borde superior, la etiqueta del lomo) que debería
  resolver la detección del borde del papel.

- Criterio de página sospechosa: al principio se usó el interlineado y marcaba 29 de las
  primeras 68 páginas, casi todas bien segmentadas (páginas densas, listas de aranceles).
  Se cambió por la proporción de renglones muy cortos (>= 0.5): marca 4 de 68 (p0021,
  p0026, p0062, p0065), todas con segmentación realmente mala.
- Borde del papel: segmentos casi verticales (Canny + Hough) fuera del bloque de texto,
  con salto de brillo entre ambos lados. Sin esa condición tomaba reglas de tinta y
  pliegues por bordes y cortaba la columna de importes (p0063) o texto real (p0023).
  Además solo se descartan renglones cortos del otro lado del borde. En p0001-p0068 se
  encuentra al menos un borde en 50 páginas y se descartan 310 renglones por borde y 83
  por franja.
- `htr refine` reaplica las reglas sobre la salida guardada de Kraken: 68 páginas en
  ~30 s contra ~35 min de volver a segmentar.

## Notas de la fase 3

- Modelo base: McCATMuS (Chagué, CC-BY-4.0, Zenodo 13788177), entrenado sobre 22
  conjuntos de los siglos XVI-XXI, con español entre otras lenguas. Precisión declarada
  92,8 % en su propia validación. Predice en NFD; el proyecto normaliza a NFC.
- `kraken list` falla en Windows por la codificación (cp1252) y `kraken get` no baja los
  archivos ("invalid path"); el modelo se baja directo de Zenodo con `tasks.py models`,
  que verifica el sha256.
- Sin ajuste, la lectura es reconocible pero lejos de usable (p. ej. "Certifico en q^to
  puedo" sale "Cttifes en g^t pues"). El CER real se mide recién con páginas corregidas.

- Línea de base sobre las primeras correcciones: CER 32 % (evaluación, 1 página) y 33 %
  (entrenamiento, 168 renglones). WER 75-89 %.
- Prueba de entrenamiento: 1 época en CPU sobre 85 renglones tarda ~3,5 min; el flujo
  ketos + McCATMuS + PAGE propio funciona. Para entrenar en serio hacen falta ~400-500
  renglones corregidos según las normas; en GPU (Kaggle) se corre `htr train --kaggle`.

## Reglas para la fase 7 (LLM)

- Entrada: solo tramos marcados, con el recorte de imagen, las N mejores lecturas del
  modelo y las entradas del léxico.
- Salida: JSON; cada corrección elige una de esas lecturas o una entrada del léxico.
- Prohibido: reescribir libremente, inventar nombres, modernizar ortografía.
- Tope de distancia de edición por corrección y presupuesto diario de gasto.
- Todo queda en un registro auditable y lo acepta o rechaza una persona.
- Modelo por defecto: Claude Haiku, por costo; clave en `ANTHROPIC_API_KEY`.
