from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from .config import load_config
from .ingest import extract_pdf_images
from .preprocess import preprocess_collection

# La consola de Windows usa cp1252 por defecto y rompe los acentos
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

app = typer.Typer(help="Pipeline de HTR para registros notariales y eclesiásticos.",
                  no_args_is_help=True)


def _parse_pages(spec: str | None) -> set[str] | None:
    """`1-5,9` -> {p0001..p0005, p0009}."""
    if not spec:
        return None
    pages: set[str] = set()
    for chunk in spec.split(","):
        a, _, b = chunk.partition("-")
        for n in range(int(a), int(b or a) + 1):
            pages.add(f"p{n:04d}")
    return pages


@app.command()
def ingest(config: Path,
           pdf: Annotated[Path | None, typer.Option(help="Pisa source.pdf")] = None):
    """Extrae las imágenes originales del PDF a data/<colección>/raw."""
    cfg = load_config(config)
    records = extract_pdf_images(pdf or cfg.source_pdf, cfg.raw_dir)
    rendered = sum(r["rendered"] for r in records)
    typer.echo(f"{len(records)} páginas -> {cfg.raw_dir} ({rendered} rasterizadas)")


@app.command()
def preprocess(config: Path,
               pages: Annotated[str | None, typer.Option(help="p. ej. 1-10,15")] = None):
    """Endereza y normaliza las páginas de raw/ hacia clean/."""
    cfg = load_config(config)
    records = preprocess_collection(cfg.raw_dir, cfg.clean_dir, cfg.preprocess,
                                    _parse_pages(pages))
    kinds = Counter(r["kind"] for r in records)
    typer.echo(f"{len(records)} imágenes -> {cfg.clean_dir} " + str(dict(kinds)))


@app.command()
def segment(config: Path,
            pages: Annotated[str | None, typer.Option(help="p. ej. 1-10,15")] = None,
            device: Annotated[str, typer.Option(help="cpu, cuda:0, ...")] = "cpu"):
    """Segmenta regiones y renglones con Kraken y aplica los filtros propios."""
    from .layout import segment_collection  # requiere el extra [layout]

    cfg = load_config(config)
    records = segment_collection(cfg.clean_dir, cfg.layout_dir, cfg.layout,
                                 _parse_pages(pages), device=device)
    _report(records, cfg.layout_dir)


@app.command()
def refine(config: Path,
           pages: Annotated[str | None, typer.Option(help="p. ej. 1-10,15")] = None):
    """Reaplica los filtros sobre la salida guardada de Kraken (sin volver a segmentar)."""
    from .layout import refine_collection

    cfg = load_config(config)
    _report(refine_collection(cfg.clean_dir, cfg.layout_dir, cfg.layout, _parse_pages(pages)),
            cfg.layout_dir)


def _report(records: list[dict], layout_dir: Path) -> None:
    total = Counter()
    for r in records:
        total.update({k: r[k] for k in ("lines_kraken", "lines_facing_page", "lines_duplicate",
                                        "lines_merged", "lines")})
    suspect = [r["page_id"] for r in records if r["layout_suspect"]]
    typer.echo(f"{len(records)} páginas -> {layout_dir} {dict(total)}")
    if suspect:
        typer.echo(f"Segmentación a revisar a mano ({len(suspect)}): {', '.join(suspect)}")


@app.command()
def recognize(config: Path,
              pages: Annotated[str | None, typer.Option(help="p. ej. 1-10,15")] = None,
              device: Annotated[str, typer.Option(help="cpu, cuda:0, ...")] = "cpu"):
    """Transcribe cada renglón segmentado con el modelo de la configuración."""
    from .recognize import recognize_collection

    cfg = load_config(config)
    records = recognize_collection(cfg.clean_dir, cfg.layout_dir, cfg.text_dir, cfg.recognition,
                                   _parse_pages(pages), device=device)
    lines = sum(r["lines"] for r in records)
    low = sum(r["low_conf_lines"] for r in records)
    typer.echo(f"{len(records)} páginas, {lines} renglones -> {cfg.text_dir} "
               f"({low} renglones con confianza < {cfg.recognition.low_conf})")


@app.command()
def correct(config: Path,
            port: Annotated[int, typer.Option(help="Puerto local")] = 8765,
            no_browser: Annotated[bool, typer.Option("--no-browser")] = False,
            lan: Annotated[bool, typer.Option("--lan", help="Abrir en la Wi-Fi para el celular")] = False):
    """Editor de transcripciones en el navegador (solo accesible desde esta máquina)."""
    from .correct import Store, serve

    cfg = load_config(config)
    store = Store(cfg.clean_dir, cfg.layout_dir, cfg.text_dir, cfg.ground_truth_dir, cfg.title,
                  frozenset(cfg.test_pages))
    serve(store, port, open_browser=not no_browser, lan=lan)


@app.command()
def evaluate(config: Path,
             per_page: Annotated[bool, typer.Option("--per-page")] = False):
    """CER/WER de la transcripción actual contra las páginas corregidas."""
    from .evaluate import evaluate as run_eval

    cfg = load_config(config)
    scores = run_eval(cfg.text_dir, cfg.ground_truth_dir, set(cfg.test_pages))

    def fmt(name, s):
        if not s.lines:
            return f"  {name:<14} sin páginas corregidas"
        return (f"  {name:<14} CER {s.cer:6.2%}  WER {s.wer:6.2%}  "
                f"({s.lines} renglones, {s.chars} caracteres)")

    typer.echo(f"Páginas de evaluación configuradas: {len(cfg.test_pages)}")
    for name in ("evaluación", "entrenamiento"):
        typer.echo(fmt(name, scores[name]))
    if per_page:
        for name, s in scores.items():
            if name not in ("evaluación", "entrenamiento"):
                typer.echo(fmt(name, s))


@app.command()
def train(config: Path,
          version: Annotated[str, typer.Option(help="Nombre del modelo, p. ej. v1")] = "v1",
          run: Annotated[bool, typer.Option("--run", help="Entrenar acá (CPU: horas)")] = False,
          epochs: Annotated[int | None, typer.Option(help="Tope de épocas (prueba rápida)")] = None,
          kaggle: Annotated[bool, typer.Option("--kaggle", help="Armar zip + cuaderno")] = False,
          device: Annotated[str, typer.Option(help="cpu, cuda:0, ...")] = "cpu"):
    """Exporta las correcciones para `ketos train` y, si se pide, entrena o arma el paquete."""
    import subprocess

    from .train import export_training_set, kaggle_bundle, ketos_command

    cfg = load_config(config)
    out = cfg.data_dir / "train" / version
    ts = export_training_set(cfg.clean_dir, cfg.layout_dir, cfg.ground_truth_dir, out,
                             set(cfg.test_pages))
    typer.echo(f"{len(ts.pages)} páginas, {ts.lines} renglones, {ts.chars} caracteres -> {out}")
    for reason, pids in ts.skipped.items():
        if pids:
            typer.echo(f"  fuera ({reason}): {', '.join(pids)}")
    if not ts.pages:
        raise typer.Exit(1)
    base = Path(cfg.recognition.model).resolve()
    model_dir = (Path("models") / cfg.collection_id / version).resolve()
    if kaggle:
        zip_path = Path("outputs") / "kaggle" / f"{cfg.collection_id}-{version}.zip"
        nb = kaggle_bundle(ts, base, zip_path)
        typer.echo(f"Kaggle: subir {zip_path} como dataset y abrir {nb}")
    cmd = ketos_command("train.txt", str(base), str(model_dir), device=device)
    if epochs:
        cmd[cmd.index("early")] = "fixed"
        cmd += ["-N", str(epochs)]
    typer.echo("Comando: " + " ".join(cmd))
    if run:
        ketos = Path(sys.executable).with_name("ketos")
        cmd[0] = str(ketos)
        raise typer.Exit(subprocess.run(cmd, cwd=out, check=False).returncode)


@app.command("check-gt")
def check_gt(config: Path,
             summary: Annotated[bool, typer.Option("--summary", help="Solo conteos por página")] = False):
    """Señala renglones corregidos para revisar contra las normas de transcripción."""
    from collections import defaultdict

    from .gtcheck import check_collection
    from .manifest import read_jsonl

    cfg = load_config(config)
    suspect = {r["page_id"] for r in read_jsonl(cfg.layout_dir / "manifest.jsonl")
               if r.get("layout_suspect")}
    findings = check_collection(cfg.ground_truth_dir, suspect)
    by_page = defaultdict(list)
    for f in findings:
        by_page[f.page_id].append(f)
    for pid, items in by_page.items():
        kinds = Counter(f.kind for f in items)
        typer.echo(f"{pid}: " + ", ".join(f"{k} {n}" for k, n in kinds.most_common()))
        if not summary:
            for f in items:
                where = f"renglón {f.line}" if f.line else "página"
                typer.echo(f"    {where}: {f.detail}")
    typer.echo(f"{len(findings)} avisos en {len(by_page)} páginas")


@app.command()
def status(config: Path,
           watch: Annotated[int, typer.Option(help="Refrescar cada N segundos (0 = una vez)")] = 0,
           as_json: Annotated[bool, typer.Option("--json", help="Salida en JSON")] = False):
    """Muestra el avance de cada etapa; funciona con una corrida en curso."""
    import time

    import click

    from .status import collection_status, render, to_json

    cfg = load_config(config)
    while True:
        st = collection_status(cfg)
        if as_json:
            typer.echo(to_json(st))
        else:
            if watch:
                click.clear()
            typer.echo(render(st))
        if not watch:
            return
        try:
            time.sleep(watch)
        except KeyboardInterrupt:
            return


@app.command()
def viewer(config: Path,
           pages: Annotated[str | None, typer.Option(help="p. ej. 1-10,15")] = None,
           open_browser: Annotated[bool, typer.Option("--open", help="Abrir en el navegador")] = False):
    """Genera la vista de control HTML con lo que detectó cada regla, por página."""
    from .viewer import build_viewer

    cfg = load_config(config)
    index = build_viewer(cfg.data_dir, cfg.title, _parse_pages(pages))
    typer.echo(f"vista de control -> {index}")
    if open_browser:
        import webbrowser
        webbrowser.open(index.resolve().as_uri())


@app.command()
def overlay(config: Path,
            pages: Annotated[str | None, typer.Option(help="p. ej. 1-10,15")] = None):
    """Dibuja la segmentación sobre cada página en data/<colección>/overlay."""
    from .overlay import draw_collection

    cfg = load_config(config)
    out = cfg.data_dir / "overlay"
    n = draw_collection(cfg.clean_dir, cfg.layout_dir, out, _parse_pages(pages))
    typer.echo(f"{n} vistas -> {out}")
