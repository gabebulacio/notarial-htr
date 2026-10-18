# Normas de transcripción

Sin una norma fija no hay forma de medir errores: "correcto" significa "según estas
reglas". Las transcripciones de entrenamiento y las de salida siguen este documento. Si
una regla cambia, cambia acá primero y se anota en el registro de cambios al final.

## Dos capas

Cada renglón se guarda en dos capas que se derivan una de otra:

- **Diplomática**: lo que está escrito, como está escrito. Es la que aprende el modelo.
- **Normalizada**: abreviaturas desarrolladas y puntuación mínima, para lectura y
  búsqueda. Se genera desde la diplomática con reglas y se revisa a mano; no se usa para
  entrenar.

## Capa diplomática

| Fenómeno | Regla | Ejemplo |
|---|---|---|
| Ortografía | Se respeta tal cual: b/v, c/z/s, h, y/i, u/v, q/c | `quatro`, `bida`, `hoydo`, `cazamiento` |
| Mayúsculas | Como en el original, aunque sean irregulares | `Parroquia`, `parroquia` |
| Abreviaturas | Se copian las letras escritas; las voladas van entre `^` | `q^e`, `dh^o`, `Nro^`, `an̄s` |
| Signos de abreviación | Lineta o tilde general: `̄` combinante sobre la letra | `an̄s`, `ꝗ` si aparece así |
| Unión y separación | Como en el renglón; no se separan palabras unidas | `enla`, `delo`, `dixo` |
| Puntuación | La del original | `,` `.` `=` |
| Guion de fin de renglón | Se copia el signo que use el escribano (`-`, `=`) | `Casa=` / `miento` |
| Letras dudosas | Se transcriben y se marca el renglón como dudoso en los metadatos | |
| Ilegible | `[...]` por tramo ilegible; `[..3..]` si se estima la cantidad de letras | |
| Tachado | `[tach: texto]` | |
| Entre renglones | `[int: texto]` en el lugar donde se inserta | |
| Rúbricas y firmas | La firma se transcribe; la rúbrica sola se marca `[rúbrica]` | `Damaso Piedrabuena [rúbrica]` |
| Texto de la página enfrentada | No se transcribe; se descarta en la segmentación | |
| Renglón que no es texto | Pliegue, mancha o resto de otra página que la segmentación tomó por renglón: se marca «no es texto» en el editor (queda fuera del entrenamiento y de la medición) | |

## Capa normalizada

- Desarrollo de abreviaturas entre corchetes: `q[u]e`, `d[ic]ho`, `N[uest]ro`, `a[ño]s`.
- Se mantiene la ortografía de época (`quatro`, `bida`); no se moderniza.
- Se separan palabras unidas solo cuando es evidente: `en la`, `de lo`.
- Las marcas de tachado, interlineado e ilegibles se conservan.

## Nombres propios

Los nombres de personas y lugares nunca se corrigen hacia la forma moderna ni se
"completan" por contexto. Si la lectura es dudosa, se transcribe lo que se ve y el renglón
queda marcado. El nomenclátor de apellidos y lugares sirve para proponer lecturas, no para
imponerlas.

## Registro de cambios

- 2026-10: primera versión.
- 2026-10: se confirma la capa diplomática con voladas (`^`) y puntuación del original;
  se agrega la marca «no es texto». `htr check-gt` señala renglones a revisar.
