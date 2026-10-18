"""Editor local de transcripciones: recorte de cada renglón junto a la lectura del modelo.

`htr correct` levanta un servidor en 127.0.0.1 (solo esta máquina) y abre el navegador.
Las correcciones se guardan en `ground_truth/<colección>/pXXXX.json`, dentro del repo:
son el insumo más valioso del proyecto y van versionadas, a diferencia de `data/`.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

from .manifest import read_jsonl

_PAGE_ID = re.compile(r"^p\d{4}[ab]?$")
_PAD = 10
_STATUSES = ("pendiente", "en_curso", "corregida")


class Store:
    """Acceso a imágenes, predicciones y correcciones de una colección."""

    def __init__(self, clean_dir: Path, layout_dir: Path, text_dir: Path, gt_dir: Path,
                 title: str, test_pages: frozenset[str] = frozenset()):
        self.clean_dir, self.layout_dir, self.text_dir, self.gt_dir = (
            clean_dir, layout_dir, text_dir, gt_dir)
        self.title = title
        self.test_pages = test_pages
        self.corrector: str | None = None
        self._lock = threading.Lock()

    # --- lectura ---------------------------------------------------------------
    # Puntos de acceso a los datos: el editor no sabe si lee las carpetas del proyecto o un
    # espacio de trabajo exportado (ver workspace.py), solo usa estos cuatro métodos.
    def _page_index(self) -> list[dict]:
        layout = {r["page_id"]: r for r in read_jsonl(self.layout_dir / "manifest.jsonl")}
        text_manifest = self.text_dir / "manifest.jsonl"
        text = {r["page_id"]: r for r in read_jsonl(text_manifest)} if text_manifest.exists() else {}
        return [{**text[pid], "layout_suspect": lay.get("layout_suspect", False)}
                for pid, lay in layout.items() if pid in text]

    def _prediction(self, pid: str) -> dict:
        return json.loads((self.text_dir / f"{pid}.json").read_text(encoding="utf-8"))

    def _boundaries(self, pid: str) -> dict[str, list]:
        debug = json.loads((self.layout_dir / "debug" / f"{pid}.json").read_text(encoding="utf-8"))
        return {line["id"]: line["boundary"] for line in debug["lines"]}

    def _image_path(self, pid: str) -> Path:
        rec = next(r for r in read_jsonl(self.layout_dir / "manifest.jsonl") if r["page_id"] == pid)
        return self.clean_dir / rec["image"]

    def pages(self) -> list[dict]:
        out = []
        for rec in self._page_index():
            pid = rec["page_id"]
            gt = self.load_gt(pid)
            out.append({
                "page_id": pid,
                "lines": rec["lines"],
                "mean_conf": rec["mean_conf"],
                "low_conf_lines": rec["low_conf_lines"],
                "layout_suspect": rec.get("layout_suspect", False),
                "test": pid in self.test_pages,
                "status": gt["status"] if gt else "pendiente",
                "edited": sum(line.get("edited", False) for line in gt["lines"]) if gt else 0,
            })
        return out

    def page(self, pid: str) -> dict:
        pred = self._prediction(pid)
        boundaries = self._boundaries(pid)
        gt = self.load_gt(pid)
        gt_lines = {line["id"]: line for line in gt["lines"]} if gt else {}
        lines = []
        for line in pred["lines"]:
            saved = gt_lines.get(line["id"], {})
            lines.append({
                "id": line["id"],
                "prediction": line["text"],
                "char_conf": line["char_conf"],
                "mean_conf": line["mean_conf"],
                "text": saved.get("text", line["text"]),
                "doubtful": saved.get("doubtful", False),
                "not_text": saved.get("not_text", False),
                # Las páginas corregidas antes de existir este campo cuentan como revisadas
                "reviewed": saved.get("reviewed", bool(gt) and gt["status"] == "corregida"),
                "edited": saved.get("edited", False),
                "has_crop": line["id"] in boundaries,
            })
        return {"page_id": pid, "model": pred["model"], "status": gt["status"] if gt else "pendiente",
                "test": pid in self.test_pages, "lines": lines}

    def scores(self, pid: str | None = None) -> dict:
        """CER/WER de los conjuntos (solo páginas corregidas) y, si se pide, de una página."""
        from .evaluate import evaluate, score_page

        def as_dict(s):
            return {"cer": s.cer, "wer": s.wer, "lines": s.lines, "chars": s.chars,
                    "pages": len(s.pages)}

        sets = evaluate(self.text_dir, self.gt_dir, set(self.test_pages))
        out = {"test": as_dict(sets["evaluación"]), "train": as_dict(sets["entrenamiento"]),
               "test_total": len(self.test_pages)}
        if pid and (gt := self.load_gt(pid)) and (page := score_page(self.text_dir, gt)):
            out["page"] = {**as_dict(page), "status": gt["status"]}
        return out

    def load_gt(self, pid: str) -> dict | None:
        path = self.gt_dir / f"{pid}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    @lru_cache(maxsize=8)  # noqa: B019 - el Store vive lo que dura el servidor
    def _image(self, pid: str) -> np.ndarray:
        return cv2.imread(str(self._image_path(pid)), cv2.IMREAD_GRAYSCALE)

    def crop(self, pid: str, line_id: str) -> bytes | None:
        boundary = self._boundaries(pid).get(line_id)
        if boundary is None:
            return None
        img = self._image(pid)
        poly = np.array(boundary, np.int32)
        x, y, w, h = cv2.boundingRect(poly)
        x0, y0 = max(0, x - _PAD), max(0, y - _PAD)
        x1, y1 = min(img.shape[1], x + w + _PAD), min(img.shape[0], y + h + _PAD)
        crop = img[y0:y1, x0:x1].copy()
        # Lo que queda fuera del contorno del renglón se aclara, para que se vea qué tomó el modelo
        mask = np.zeros_like(crop)
        cv2.fillPoly(mask, [poly - [x0, y0]], 255)
        crop = np.where(mask > 0, crop, (crop * 0.35 + 255 * 0.65).astype(np.uint8))
        ok, png = cv2.imencode(".png", crop)
        return png.tobytes() if ok else None

    # --- escritura -------------------------------------------------------------
    def save(self, pid: str, payload: dict) -> dict:
        page = self.page(pid)
        known = {line["id"]: line for line in page["lines"]}
        status = payload.get("status", "en_curso")
        if status not in _STATUSES:
            raise ValueError(f"estado inválido: {status}")
        lines = []
        for item in payload["lines"]:
            if item["id"] not in known:
                raise ValueError(f"renglón desconocido: {item['id']}")
            text = str(item["text"]).replace("\r", "").replace("\n", " ")
            lines.append({
                "id": item["id"],
                "text": text,
                "doubtful": bool(item.get("doubtful", False)),
                # Pliegue, mancha o resto de otra página: fuera del entrenamiento y la medición
                "not_text": bool(item.get("not_text", False)),
                # El editor de escritorio no manda este campo: se conserva lo que había, y
                # «Marcar corregida» da por revisados todos los renglones
                "reviewed": status == "corregida" or bool(
                    item.get("reviewed", known[item["id"]]["reviewed"])),
                "edited": text != known[item["id"]]["prediction"],
                "prediction": known[item["id"]]["prediction"],
            })
        data = {"page_id": pid, "status": status, "model": page["model"],
                "updated_at": datetime.now(UTC).isoformat(timespec="seconds"), "lines": lines}
        if self.corrector:
            data["corrector"] = self.corrector
        with self._lock:
            self.gt_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.gt_dir / f"{pid}.json.tmp"
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.gt_dir / f"{pid}.json")
        return {"ok": True, "status": status, "edited": sum(x["edited"] for x in lines)}


def lan_ip() -> str:
    """IP de esta máquina en la red local (no manda paquetes: UDP sin conexión real)."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def make_handler(store: Store, token: str | None = None,
                 lan_url: str | None = None) -> type[BaseHTTPRequestHandler]:
    """`token`: si está, todo pedido que no venga de esta máquina debe traerlo (en la URL la
    primera vez, después en una cookie). Sin token el servidor solo escucha en 127.0.0.1."""
    import hmac

    from .correct_ui import editor_html, index_html
    from .mobile_ui import mobile_html

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silencio en la consola
            return

        def _local(self) -> bool:
            return self.client_address[0] in ("127.0.0.1", "::1")

        def _authorized(self) -> bool:
            if token is None or self._local():
                return True
            query = self.path.partition("?")[2]
            given = dict(p.partition("=")[::2] for p in query.split("&") if p).get("t", "")
            cookie = self.headers.get("Cookie", "")
            cookies = dict(c.strip().partition("=")[::2] for c in cookie.split(";") if c.strip())
            return any(hmac.compare_digest(v, token) for v in (given, cookies.get("htr_t", "")) if v)

        def _deny(self) -> None:
            self._send(HTTPStatus.FORBIDDEN, "Falta la clave: abrí el enlace completo que muestra "
                       "la computadora.".encode(), "text/plain; charset=utf-8")

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            if token and "t=" in self.path and not self._local():
                self.send_header("Set-Cookie", f"htr_t={token}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: int = 200) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _pid(self, raw: str) -> str | None:
            return raw if _PAGE_ID.match(raw) and (store.text_dir / f"{raw}.json").exists() else None

        def do_GET(self):
            if not self._authorized():
                return self._deny()
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if parts == ["m"]:
                return self._send(200, mobile_html(store.title).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if parts == ["api", "lan"]:
                # Solo la propia computadora ve el enlace con la clave (para el QR)
                return self._json({"url": lan_url if self._local() else None})
            if not parts:
                return self._send(200, index_html(store.title).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if parts == ["api", "pages"]:
                return self._json(store.pages())
            if parts == ["api", "scores"]:
                return self._json(store.scores())
            if len(parts) == 3 and parts[:2] == ["api", "scores"] and (pid := self._pid(parts[2])):
                return self._json(store.scores(pid))
            if len(parts) == 2 and parts[0] == "p" and (pid := self._pid(parts[1])):
                return self._send(200, editor_html(pid, store.title).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if len(parts) == 3 and parts[:2] == ["api", "page"] and (pid := self._pid(parts[2])):
                return self._json(store.page(pid))
            if len(parts) == 3 and parts[0] == "crop" and (pid := self._pid(parts[1])):
                png = store.crop(pid, parts[2].removesuffix(".png"))
                if png:
                    return self._send(200, png, "image/png")
            self._send(HTTPStatus.NOT_FOUND, b"no encontrado", "text/plain; charset=utf-8")

        def do_POST(self):
            if not self._authorized():
                return self._deny()
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if len(parts) == 3 and parts[:2] == ["api", "page"] and (pid := self._pid(parts[2])):
                length = int(self.headers.get("Content-Length", 0))
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    return self._json(store.save(pid, payload))
                except (ValueError, KeyError) as exc:
                    return self._json({"ok": False, "error": str(exc)}, 400)
            self._send(HTTPStatus.NOT_FOUND, b"no encontrado", "text/plain; charset=utf-8")

    return Handler


def serve(store: Store, port: int, open_browser: bool = True, lan: bool = False) -> None:
    """Con `lan`, escucha en la red local para usarlo desde el celular, protegido por una
    clave aleatoria nueva en cada arranque. Las imágenes no salen de esta red."""
    import secrets

    token = secrets.token_urlsafe(16) if lan else None
    lan_url = f"http://{lan_ip()}:{port}/m?t={token}" if lan else None
    server = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port),
                                 make_handler(store, token, lan_url))
    url = f"http://127.0.0.1:{port}/"
    print(f"Editor de transcripciones en {url}  (Ctrl+C para cerrar)")
    if lan_url:
        print(f"Desde el celular (misma Wi-Fi): {lan_url}")
        print("La clave cambia cada vez que se arranca; no compartas el enlace.")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
