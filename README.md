# notarial-htr

Reconocimiento de texto manuscrito (HTR) para registros notariales y eclesiásticos en
español de los siglos XVII y XVIII, pensado para legajos fotografiados en archivo y para
que sumar una colección nueva sea escribir un archivo de configuración, no código nuevo.

La primera colección son las **informaciones matrimoniales de Ancasti (Catamarca),
1794-1799**: 227 fotografías de expedientes con declaraciones de testigos, pedimentos y
certificaciones de amonestaciones.

## Enfoque

El reconocimiento lo hace un modelo propio, no un LLM: segmentación por renglón y una
red convolucional + recurrente entrenada con CTC (en la línea del trabajo de Harald
Scheidl), ajustada sobre la mano de cada legajo con transcripciones corregidas a mano.
Los LLM entran solo al final, sobre tramos marcados como dudosos, con salida estructurada
y reglas explícitas: elegir entre lecturas alternativas del modelo o del léxico, nunca
reescribir, nunca modernizar la ortografía. Cada propuesta queda registrada y la acepta o
la rechaza una persona.

Etapas (detalle y estado en [docs/plan.md](docs/plan.md)):

1. **Ingesta**: extracción de las imágenes originales del PDF, sin recomprimir, con manifiesto y hash por página.
2. **Preproceso**: enderezado cuando la estimación es confiable, páginas en blanco y dobles páginas.
3. **Segmentación**: regiones y líneas base (Kraken), descartando el texto de la página enfrentada.
4. **Reconocimiento**: CNN + BiLSTM + CTC, ajustado por rondas de corrección.
5. **Decodificación con léxico**: beam search restringido a palabras plausibles de la época y a un nomenclátor de apellidos y lugares.
6. **Confianza**: probabilidad por carácter y por palabra, calibrada, para revisar y para buscar.
7. **Ajustes con LLM**: acotados, auditables y opcionales.
8. **Exportación**: PAGE XML, texto diplomático y normalizado, registros JSON e índice de búsqueda.

Las reglas de transcripción están en [docs/normas-de-transcripcion.md](docs/normas-de-transcripcion.md).

## Uso

Atajos multiplataforma en `tasks.py` (el `Makefile` delega ahí):

```bash
python tasks.py setup                # .venv con torch CPU, Kraken y dependencias de desarrollo
python tasks.py status               # avance de cada etapa, también con una corrida en curso
python tasks.py status --watch 10    # refresca cada 10 s (Ctrl+C para salir)
python tasks.py segment --pages 1-10
python tasks.py models               # baja el modelo base McCATMuS y verifica su hash
python tasks.py recognize            # transcripción automática con confianza por carácter
python tasks.py correct              # editor de correcciones en el navegador
python tasks.py correct --lan        # además desde el celular (misma Wi-Fi, con clave y QR)
python tasks.py evaluate             # CER/WER contra lo corregido
python tasks.py check-gt             # renglones a revisar contra las normas
python tasks.py train --kaggle       # exporta correcciones y arma el paquete para GPU en Kaggle
```

Las correcciones se guardan en `ground_truth/<colección>/` y sí van al repositorio: son
el resultado del trabajo humano y no se pueden regenerar.

Los mismos pasos con el CLI directo:

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # en Linux/macOS: .venv/bin/pip

htr ingest configs/ancasti-1794.yaml       # PDF -> data/ancasti-1794/raw
htr preprocess configs/ancasti-1794.yaml   # raw -> data/ancasti-1794/clean
htr preprocess configs/ancasti-1794.yaml --pages 10-20

# Segmentación (extra opcional; torch CPU primero para no bajar la versión con CUDA)
.venv/Scripts/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/pip install -e ".[layout]"
htr segment configs/ancasti-1794.yaml      # clean -> data/ancasti-1794/layout (PAGE XML)
htr refine configs/ancasti-1794.yaml       # reaplica los filtros sin volver a correr Kraken
htr overlay configs/ancasti-1794.yaml      # vistas de control en data/ancasti-1794/overlay
htr viewer configs/ancasti-1794.yaml --open  # vista HTML por capas: qué detectó cada regla

pytest
```

Las imágenes, modelos y salidas quedan en `data/`, `models/` y `outputs/`, fuera del
repositorio: se regeneran desde el PDF fuente.

## Historia

El proyecto arrancó en agosto de 2025 con la digitalización de los legajos, coordinada por
Gerardo, y una primera versión del pipeline. Ese código se perdió junto con la computadora en
la que estaba. En octubre de 2026 recuperé el documento y retomé el trabajo, rehaciendo el
pipeline con lo que aprendí y con lo que cambió en el área desde entonces.

Los commits anteriores a octubre de 2026 reconstruyen el historial perdido: siguen el orden
y las fechas aproximadas del trabajo, pero no contienen el código de ese momento. El código
actual se escribió desde octubre de 2026.

Parte del código se escribió con asistencia de IA (Claude/Copilot), revisada y probada por mí junto a usuarios e historiadores.
