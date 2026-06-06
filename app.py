"""JavaGen — aplicação web (Flask) que gera classes Java/Spring Boot a partir de .sql.

Fluxo do POST /generate:
  1. lê o SQL (upload ou textarea) e os campos do formulário (todo o GenContext);
  2. parseia o SQL no dialeto escolhido;
  3. LIMPA a pasta de output (antes);
  4. gera os arquivos em memória e os materializa em _output/;
  5. empacota tudo num .zip;
  6. LIMPA a pasta de output (depois, sempre — em finally);
  7. devolve o .zip para download + aviso de sucesso na tela.
"""
from __future__ import annotations

import io

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from config import (
    BASE_DIR,
    DEFAULT_BASE_PACKAGE,
    DEFAULT_DIALECT,
    DEFAULT_SYSTEM_NAME,
    MAX_UPLOAD_BYTES,
    OUTPUT_DIR,
    SUPPORTED_DIALECTS,
)
from generator.base import GenContext
from generator.orchestrator import ProjectGenerator
from parser.sql_parser import SqlParseError, parse_sql
from utils.fileio import clean_dir, write_files
from utils.naming import is_valid_package
from utils.zipper import build_zip

app = Flask(__name__)
app.secret_key = "javagen-local"
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _read_sql(req) -> str:
    """Lê o SQL do upload (prioritário) ou do textarea."""
    f = req.files.get("sql_file")
    if f and f.filename:
        return f.read().decode("utf-8", errors="replace")
    return req.form.get("sql_text", "")


def _checkbox(req, name: str) -> bool:
    """Checkbox HTML: presente => marcado."""
    return name in req.form


def _build_context(req) -> GenContext:
    """Monta o GenContext a partir de TODOS os campos do formulário."""
    dialect = req.form.get("dialect", DEFAULT_DIALECT).strip()
    if dialect not in SUPPORTED_DIALECTS:
        dialect = DEFAULT_DIALECT
    rest_base = (req.form.get("rest_base_path", "/api") or "/api").strip()
    if not rest_base.startswith("/"):
        rest_base = "/" + rest_base
    return GenContext(
        system_name=(req.form.get("system_name", DEFAULT_SYSTEM_NAME).strip() or DEFAULT_SYSTEM_NAME),
        base_package=(req.form.get("base_package", DEFAULT_BASE_PACKAGE).strip() or DEFAULT_BASE_PACKAGE),
        dialect=dialect,
        use_lombok=_checkbox(req, "use_lombok"),
        gen_inverse_rel=_checkbox(req, "gen_inverse_rel"),
        gen_enums=_checkbox(req, "gen_enums"),
        gen_openapi=_checkbox(req, "gen_openapi"),
        audit_user=_checkbox(req, "audit_user"),
        soft_delete=_checkbox(req, "soft_delete"),
        rest_base_path=rest_base,
    )


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    """Formulário principal."""
    return render_template(
        "index.html",
        dialects=SUPPORTED_DIALECTS,
        defaults={
            "system_name": DEFAULT_SYSTEM_NAME,
            "base_package": DEFAULT_BASE_PACKAGE,
            "dialect": DEFAULT_DIALECT,
            "rest_base_path": "/api",
        },
    )


@app.route("/sample")
def sample():
    """Conteúdo do SQL de exemplo (botão 'Carregar exemplo')."""
    return app.send_static_file("sample.sql")


@app.route("/preview", methods=["POST"])
def preview():
    """Analisa o SQL e devolve as tabelas/colunas detectadas (AJAX)."""
    sql = _read_sql(request)
    dialect = request.form.get("dialect", DEFAULT_DIALECT)
    try:
        schema = parse_sql(sql, dialect, consolidate_alter=_checkbox(request, "consolidate_alter"))
    except SqlParseError as e:
        return jsonify(ok=False, error=str(e)), 400
    except Exception as e:  # pragma: no cover - robustez
        return jsonify(ok=False, error=f"Falha ao analisar o SQL: {e}"), 400

    tables = []
    for t in schema.tables:
        tables.append({
            "name": t.name,
            "class": t.class_name,
            "columns": [
                {
                    "name": c.name,
                    "type": c.raw_sql_type,
                    "java": c.enum_type_name or c.java_type,
                    "pk": c.is_pk,
                    "fk": (c.fk.target_entity if c.is_foreign_key and c.fk else None),
                    "nullable": c.nullable,
                }
                for c in t.columns
            ],
            "indexes": [{"name": i.name, "cols": i.columns, "unique": i.unique} for i in t.indexes],
        })
    return jsonify(ok=True, tables=tables, ignored=schema.ignored,
                   consolidated_alters=schema.consolidated_alters)


@app.route("/generate", methods=["POST"])
def generate():
    """Gera o projeto e devolve o .zip (limpando o output antes e depois)."""
    sql = _read_sql(request)
    if not sql.strip():
        return jsonify(ok=False, error="Informe um SQL ou envie um arquivo .sql."), 400

    ctx = _build_context(request)
    if not is_valid_package(ctx.base_package):
        return jsonify(ok=False, error=f"Pacote base inválido: {ctx.base_package}"), 400

    try:
        schema = parse_sql(sql, ctx.dialect, consolidate_alter=_checkbox(request, "consolidate_alter"))
    except SqlParseError as e:
        return jsonify(ok=False, error=f"SQL inválido: {e}"), 400
    except Exception as e:  # pragma: no cover
        return jsonify(ok=False, error=f"Falha ao analisar o SQL: {e}"), 400

    files = ProjectGenerator(ctx, schema).generate()

    # Limpa ANTES, materializa, zipa e limpa DEPOIS (sempre).
    clean_dir(OUTPUT_DIR)
    try:
        write_files(OUTPUT_DIR, files)
        zip_buf = build_zip(files)
    finally:
        clean_dir(OUTPUT_DIR)

    download_name = f"{ctx.system_name.lower()}-spring.zip"
    resp = send_file(
        io.BytesIO(zip_buf.getvalue()),
        mimetype="application/zip",
        as_attachment=True,
        download_name=download_name,
    )
    # Cabeçalhos lidos pelo JS para montar o aviso de sucesso na tela.
    resp.headers["X-Gen-Tables"] = str(len(schema.tables))
    resp.headers["X-Gen-Files"] = str(len(files))
    resp.headers["X-Gen-Filename"] = download_name
    # Resumo dos comandos ignorados (ex.: "INSERT:3, ALTER TABLE:1") para o aviso na tela.
    resp.headers["X-Gen-Ignored"] = ", ".join(f"{k}:{v}" for k, v in schema.ignored.items())
    resp.headers["X-Gen-Consolidated"] = str(schema.consolidated_alters)
    return resp


@app.errorhandler(413)
def too_large(_e):
    return jsonify(ok=False, error="Arquivo muito grande (limite de 2 MB)."), 413


if __name__ == "__main__":
    # Abre o navegador automaticamente após subir.
    import threading
    import webbrowser

    def _open():
        webbrowser.open("http://127.0.0.1:5000")

    threading.Timer(1.0, _open).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
